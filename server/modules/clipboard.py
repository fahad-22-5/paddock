"""Clipboard: show the PC's clipboard text on the device and send text the other way.
Uses the Win32 clipboard API directly (no extra dependency)."""
from __future__ import annotations

import ctypes
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes

from .base import ActionError, Module, action

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MAX_SEND = 1_000_000
PREVIEW_CHARS = 20_000

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL


class _Open:
    """Open the clipboard, retrying briefly because other apps hold it for a moment."""

    def __enter__(self):
        for _ in range(20):
            if user32.OpenClipboard(None):
                return self
            time.sleep(0.03)
        raise ActionError("The PC clipboard is busy. Try again.")

    def __exit__(self, *exc):
        user32.CloseClipboard()


def read_text() -> str | None:
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    with _Open():
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr) if ptr else None
        finally:
            kernel32.GlobalUnlock(handle)


def write_text(text: str) -> None:
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not handle:
        raise ActionError("Out of memory.")
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, size)
    kernel32.GlobalUnlock(handle)
    with _Open():
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)  # ownership only passes on success
            raise ActionError("Couldn't set the PC clipboard.")


class ClipboardModule(Module):
    name = "clipboard"

    async def start(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipboard")
        self._seq = None
        self.spawn(self.poll("clipboard", 0.8, self.sample))

    async def _run(self, fn, *a):
        import asyncio

        return await asyncio.get_running_loop().run_in_executor(self._pool, fn, *a)

    async def sample(self):
        seq = user32.GetClipboardSequenceNumber()
        if seq == self._seq and self.hub.last("clipboard") is not None:
            return self.hub.last("clipboard")
        self._seq = seq
        try:
            text = await self._run(read_text)
        except ActionError:
            self._seq = None  # busy: try again next tick
            return None
        if text is None:
            return {"text": None, "length": 0, "truncated": False, "changed": time.time()}
        return {"text": text[:PREVIEW_CHARS], "length": len(text), "truncated": len(text) > PREVIEW_CHARS, "changed": time.time()}

    @action
    async def get_full(self, args, client):
        """The whole clipboard text (the live topic only carries a preview)."""
        return await self._run(read_text)

    @action
    async def set(self, args, client):
        text = args.get("text")
        if not isinstance(text, str) or not text:
            raise ActionError("Nothing to send.")
        if len(text) > MAX_SEND:
            raise ActionError("That text is too long for the clipboard (1,000,000 characters max).")
        await self._run(write_text, text)
        return True
