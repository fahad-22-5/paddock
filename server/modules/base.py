"""Base class for feature modules.

A module is a class with a `name`. It can:
  * expose actions the device calls:       @action  async def set_master(self, args, client): ...
  * publish live data on topics:         self.hub.publish("volume", {...})
  * poll only while someone is watching: self.spawn(self.poll("system", 1.0, self.sample))
  * register action executors:           self.ctx.executors["exe"] = self.run_exe
  * add HTTP routes:                     def router(self) -> APIRouter

Add the class to MODULES in modules/__init__.py and it is wired up automatically.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from fastapi import APIRouter

    from ..config import ConfigStore
    from ..hub import Client, Hub
    from ..security import DeviceStore, Pairing


class ActionError(Exception):
    """An error whose message is safe and useful to show on the device."""


@dataclass
class Context:
    hub: "Hub"
    config: "ConfigStore"
    devices: "DeviceStore"
    pairing: "Pairing"
    # action type ("exe", "keys", ...) -> async fn(action_dict) ; filled in by modules
    executors: dict[str, Callable[[dict], Awaitable[Any]]] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)


def action(fn=None, *, name: str | None = None):
    """Mark a method as callable from the device."""

    def deco(f):
        f._paddock_action = name or f.__name__
        return f

    return deco(fn) if fn else deco


class Module:
    name: str = ""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.hub = ctx.hub
        self.config = ctx.config
        self.log = logging.getLogger(f"paddock.{self.name}")
        self._tasks: list[asyncio.Task] = []
        self.actions: dict[str, Callable] = {}
        for _, member in inspect.getmembers(self, predicate=inspect.ismethod):
            act = getattr(member, "_paddock_action", None)
            if act:
                self.actions[act] = member

    # ---- lifecycle -----------------------------------------------------
    async def start(self) -> None:
        """Override to start background work (call super().start() is not required)."""

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def router(self) -> "APIRouter | None":
        return None

    # ---- helpers -------------------------------------------------------
    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro, name=f"{self.name}:{getattr(coro, '__name__', 'task')}")
        self._tasks.append(task)
        return task

    async def poll(self, topic: str, interval: float, sample: Callable[[], Awaitable[Any]],
                   only_changes: bool = True) -> None:
        """Call `sample` every `interval` seconds while anyone subscribes to `topic`."""
        last = object()
        while True:
            if not self.hub.subscribers(topic):
                await self.hub.wait_for_subscribers(topic)
                last = object()  # resend everything after a quiet period
            try:
                data = await sample()
                if data is not None and (not only_changes or data != last):
                    self.hub.publish(topic, data)
                    last = data
            except asyncio.CancelledError:
                raise
            except Exception:
                self.log.exception("sampling %s failed", topic)
                await asyncio.sleep(5)
            await asyncio.sleep(interval)


class ComThread:
    """A single worker thread with COM initialised, for pycaw and other COM calls."""

    def __init__(self, name: str) -> None:
        def init():
            import comtypes

            # Same apartment as the rest of PadDock (see server/__init__.py). Importing
            # comtypes on this thread may already have initialised it, which is fine.
            try:
                comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            except OSError:
                pass

        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name, initializer=init)

    async def run(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self._pool, fn, *args)
