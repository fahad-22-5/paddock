"""Clipboard on macOS: NSPasteboard (pyobjc), with pbcopy/pbpaste as a fallback."""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from ..base import ActionError, Module, action

MAX_SEND = 1_000_000
PREVIEW_CHARS = 20_000
UTF8_ENV = {**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}


class Pasteboard:
    """General pasteboard access. Uses AppKit when available, else the pb* tools."""

    def __init__(self) -> None:
        try:
            from AppKit import NSPasteboard, NSPasteboardTypeString

            self._pb, self._type = NSPasteboard.generalPasteboard(), NSPasteboardTypeString
        except Exception:
            self._pb = None
        self._last_hash = None
        self._fallback_count = 0

    def change_count(self) -> int:
        if self._pb is not None:
            return int(self._pb.changeCount())
        # Fallback: detect changes by hashing the text.
        h = hashlib.sha1((self.read_text() or "").encode("utf-8", "replace")).hexdigest()
        if h != self._last_hash:
            self._last_hash = h
            self._fallback_count += 1
        return self._fallback_count

    def read_text(self) -> str | None:
        if self._pb is not None:
            s = self._pb.stringForType_(self._type)
            return str(s) if s is not None else None
        r = subprocess.run(["pbpaste"], capture_output=True, env=UTF8_ENV, timeout=5)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 and r.stdout else None

    def write_text(self, text: str) -> None:
        if self._pb is not None:
            self._pb.clearContents()
            if not self._pb.setString_forType_(text, self._type):
                raise ActionError("Couldn't set the Mac clipboard.")
            return
        r = subprocess.run(["pbcopy"], input=text.encode("utf-8"), env=UTF8_ENV, timeout=5)
        if r.returncode != 0:
            raise ActionError("Couldn't set the Mac clipboard.")


class ClipboardModule(Module):
    name = "clipboard"

    async def start(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipboard")
        self._pb = await self._run(Pasteboard)
        self._seq = None
        self.spawn(self.poll("clipboard", 0.8, self.sample))

    async def _run(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(self._pool, fn, *a)

    async def sample(self):
        seq = await self._run(self._pb.change_count)
        if seq == self._seq and self.hub.last("clipboard") is not None:
            return self.hub.last("clipboard")
        self._seq = seq
        text = await self._run(self._pb.read_text)
        if not text:
            return {"text": None, "length": 0, "truncated": False, "changed": time.time()}
        return {"text": text[:PREVIEW_CHARS], "length": len(text), "truncated": len(text) > PREVIEW_CHARS, "changed": time.time()}

    @action
    async def get_full(self, args, client):
        return await self._run(self._pb.read_text)

    @action
    async def set(self, args, client):
        text = args.get("text")
        if not isinstance(text, str) or not text:
            raise ActionError("Nothing to send.")
        if len(text) > MAX_SEND:
            raise ActionError("That text is too long for the clipboard (1,000,000 characters max).")
        await self._run(self._pb.write_text, text)
        return True
