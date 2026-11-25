"""Power actions: lock, sleep, restart, shut down (the device asks for confirmation first).
Restart and shut down wait 15 seconds, so you can still cancel from the device."""
from __future__ import annotations

import asyncio
import ctypes
import subprocess

from .base import ActionError, Module, action

DELAY = 15


def _shutdown(*args: str) -> None:
    r = subprocess.run(["shutdown", *args], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode not in (0, 1116):  # 1116 = no shutdown in progress (for /a)
        raise ActionError((r.stderr or r.stdout).strip() or f"shutdown failed ({r.returncode})")


class PowerModule(Module):
    name = "power"

    async def start(self) -> None:
        self.pending: str | None = None

    def _publish(self) -> None:
        self.hub.publish("power", {"pending": self.pending, "delay": DELAY})

    @action
    async def lock(self, args, client):
        if not ctypes.windll.user32.LockWorkStation():
            raise ActionError("Couldn't lock the PC.")
        return True

    @action
    async def sleep(self, args, client):
        async def later():
            await asyncio.sleep(1.0)  # let the reply reach the device first
            # SetSuspendState(hibernate=False, force=False, disableWakeEvents=False)
            ctypes.WinDLL("powrprof").SetSuspendState(False, False, False)

        asyncio.create_task(later())
        return True

    @action
    async def restart(self, args, client):
        await asyncio.to_thread(_shutdown, "/r", "/t", str(DELAY), "/c", "Restart requested from PadDock")
        self.pending = "restart"
        self._publish()
        return {"delay": DELAY}

    @action
    async def shutdown(self, args, client):
        await asyncio.to_thread(_shutdown, "/s", "/t", str(DELAY), "/c", "Shut down requested from PadDock")
        self.pending = "shutdown"
        self._publish()
        return {"delay": DELAY}

    @action
    async def cancel(self, args, client):
        await asyncio.to_thread(_shutdown, "/a")
        self.pending = None
        self._publish()
        return True
