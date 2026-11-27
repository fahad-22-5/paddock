"""Power actions on macOS: lock, sleep, restart, shut down.

Restart and shut down wait 15 seconds inside PadDock, so you can cancel from the dock,
then ask macOS to restart/shut down normally (apps may ask to save documents)."""
from __future__ import annotations

import asyncio
import subprocess

from ...platform import osascript
from ..base import ActionError, Module, action

DELAY = 15


def _lock_screen() -> None:
    # Ctrl+Cmd+Q is the macOS "Lock Screen" shortcut (needs the Accessibility permission).
    try:
        from ..macros import press_keys

        press_keys("ctrl+cmd+q")
        return
    except Exception:
        pass
    # Fallback: turn the display off; it locks if "Require password immediately" is on.
    subprocess.run(["pmset", "displaysleepnow"], check=False)


class PowerModule(Module):
    name = "power"

    async def start(self) -> None:
        self.pending: str | None = None
        self._task: asyncio.Task | None = None

    def _publish(self) -> None:
        self.hub.publish("power", {"pending": self.pending, "delay": DELAY})

    @action
    async def lock(self, args, client):
        await asyncio.to_thread(_lock_screen)
        return True

    @action
    async def sleep(self, args, client):
        async def later():
            await asyncio.sleep(1.0)  # let the reply reach the device first
            subprocess.run(["pmset", "sleepnow"], check=False)

        asyncio.create_task(later())
        return True

    async def _schedule(self, what: str) -> dict:
        if self._task and not self._task.done():
            self._task.cancel()
        verb = "restart" if what == "restart" else "shut down"

        async def later():
            try:
                await asyncio.sleep(DELAY)
                await asyncio.to_thread(osascript, f'tell application "System Events" to {verb}', 60)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log.error("Couldn't %s: %s", verb, e)
            finally:
                self.pending = None
                self._publish()

        self.pending = what
        self._task = asyncio.create_task(later())
        self._publish()
        return {"delay": DELAY}

    @action
    async def restart(self, args, client):
        return await self._schedule("restart")

    @action
    async def shutdown(self, args, client):
        return await self._schedule("shutdown")

    @action
    async def cancel(self, args, client):
        if self._task and not self._task.done():
            self._task.cancel()
        elif not self.pending:
            raise ActionError("Nothing to cancel.")
        self.pending = None
        self._publish()
        return True
