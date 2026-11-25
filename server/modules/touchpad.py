"""Touchpad: move, click, drag and scroll the PC mouse from the device.

Uses SendInput with relative motion, so Windows applies your normal pointer speed and
"Enhance pointer precision". Handlers are synchronous so moves are applied in order."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .base import ActionError, Module, action

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    # KEYBDINPUT / HARDWAREINPUT are smaller than MOUSEINPUT, so this union has the right size.
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_SendInput = ctypes.windll.user32.SendInput
_SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_SendInput.restype = wintypes.UINT


def _send(*events: tuple[int, int, int, int]) -> None:
    arr = (INPUT * len(events))()
    for i, (flags, dx, dy, data) in enumerate(events):
        arr[i].type = INPUT_MOUSE
        arr[i].u.mi = MOUSEINPUT(dx, dy, ctypes.c_uint32(data).value, flags, 0, 0)
    _SendInput(len(events), arr, ctypes.sizeof(INPUT))


def _int(v, lo, hi) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


def _button(args) -> tuple[int, int]:
    b = BUTTONS.get(args.get("button", "left"))
    if not b:
        raise ActionError("Unknown mouse button.")
    return b


class TouchpadModule(Module):
    name = "touchpad"

    @action
    def move(self, args, client):
        dx, dy = _int(args.get("dx"), -3000, 3000), _int(args.get("dy"), -3000, 3000)
        if dx or dy:
            _send((MOUSEEVENTF_MOVE, dx, dy, 0))

    @action
    def click(self, args, client):
        down, up = _button(args)
        n = 2 if args.get("double") else 1
        _send(*[(f, 0, 0, 0) for _ in range(n) for f in (down, up)])

    @action
    def down(self, args, client):
        _send((_button(args)[0], 0, 0, 0))

    @action
    def up(self, args, client):
        _send((_button(args)[1], 0, 0, 0))

    @action
    def scroll(self, args, client):
        """dy/dx in wheel units (120 = one notch). Positive dy scrolls content up."""
        dy, dx = _int(args.get("dy"), -2400, 2400), _int(args.get("dx"), -2400, 2400)
        ev = []
        if dy:
            ev.append((MOUSEEVENTF_WHEEL, 0, 0, dy))
        if dx:
            ev.append((MOUSEEVENTF_HWHEEL, 0, 0, dx))
        if ev:
            _send(*ev)
