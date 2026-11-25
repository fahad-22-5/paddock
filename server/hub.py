"""WebSocket hub: connected clients, topic subscriptions and the message protocol.

Client -> server (every message after `auth` carries the token as "t"):
    {"type": "auth", "token": "..."}
    {"type": "sub",   "t": "...", "topics": ["system", "media"]}
    {"type": "unsub", "t": "...", "topics": ["system"]}
    {"type": "call",  "t": "...", "id": 7, "mod": "volume", "act": "set_master", "args": {...}}
        ("id" is optional; calls without one get no reply, which the touchpad uses)
    {"type": "ping",  "t": "..."}

Server -> client:
    {"type": "hello", "device": {...}, "server": {...}}
    {"type": "event", "topic": "system", "data": {...}}
    {"type": "result", "id": 7, "ok": true, "data": ...}  /  {"type": "result", "id": 7, "ok": false, "error": "..."}
    {"type": "pong"}
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger("paddock.hub")

ALWAYS_SUBSCRIBED = {"config"}


class Client:
    def __init__(self, ws, device) -> None:
        self.ws = ws
        self.device = device
        self.topics: set[str] = set(ALWAYS_SUBSCRIBED)
        self.queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=1000)
        self.closed = False

    def send(self, msg: dict) -> None:
        if self.closed:
            return
        try:
            self.queue.put_nowait(json.dumps(msg, separators=(",", ":"), default=str))
        except asyncio.QueueFull:
            log.warning("Client %s is not reading; dropping it", self.device.name)
            self.close()

    def close(self, code: int = 1011) -> None:
        """Close the socket after flushing what is queued. 4401 = token no longer valid."""
        self.closed = True
        self.close_code = code
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

    async def sender(self) -> None:
        while True:
            text = await self.queue.get()
            if text is None:
                await self.ws.close(code=getattr(self, "close_code", 1000))
                return
            await self.ws.send_text(text)


class Hub:
    def __init__(self) -> None:
        self.clients: set[Client] = set()
        self._last: dict[str, Any] = {}
        self._wakeups: dict[str, asyncio.Event] = defaultdict(asyncio.Event)

    # ---- clients -------------------------------------------------------
    def add(self, client: Client) -> None:
        self.clients.add(client)

    def remove(self, client: Client) -> None:
        self.clients.discard(client)
        client.closed = True

    def drop_device(self, device_id: str) -> None:
        """Disconnect every socket of a revoked device."""
        for c in list(self.clients):
            if c.device.id == device_id:
                c.close(4401)

    # ---- topics --------------------------------------------------------
    def subscribe(self, client: Client, topics: list[str]) -> None:
        for topic in topics:
            if not isinstance(topic, str) or len(topic) > 40:
                continue
            client.topics.add(topic)
            self._wakeups[topic].set()
            if topic in self._last:
                client.send({"type": "event", "topic": topic, "data": self._last[topic]})

    def unsubscribe(self, client: Client, topics: list[str]) -> None:
        for topic in topics:
            if topic not in ALWAYS_SUBSCRIBED:
                client.topics.discard(topic)

    def subscribers(self, topic: str) -> int:
        return sum(1 for c in self.clients if topic in c.topics)

    async def wait_for_subscribers(self, topic: str) -> None:
        """Return as soon as at least one client listens to `topic`."""
        while not self.subscribers(topic):
            ev = self._wakeups[topic]
            ev.clear()
            await ev.wait()

    def publish(self, topic: str, data: Any, cache: bool = True) -> None:
        if cache:
            self._last[topic] = data
        msg = {"type": "event", "topic": topic, "data": data}
        for c in list(self.clients):
            if topic in c.topics:
                c.send(msg)

    def last(self, topic: str) -> Any:
        return self._last.get(topic)

    def forget(self, topic: str) -> None:
        self._last.pop(topic, None)
