"""Macros: keyboard shortcuts and text snippets sent to the PC with pynput.

    "teams-mute": {"type": "keys",  "label": "Mute Teams", "keys": "ctrl+shift+m"}
    "snip":       {"type": "keys",  "label": "Snip", "keys": "win+shift+s"}
    "sig":        {"type": "text",  "label": "Signature", "text": "Best regards,\\nMe"}
    "run-np":     {"type": "steps", "label": "Notepad", "steps": [{"keys": "win+r"}, {"delay": 0.4}, {"text": "notepad"}, {"keys": "enter"}]}

`keys` may hold several combos separated by spaces ("ctrl+k ctrl+c").
Note: Windows never lets programs fake Ctrl+Alt+Delete, and keys can't reach windows
running as administrator unless PadDock runs as administrator too.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time

from .base import ActionError, Module, action

_kb = None
_lock = threading.Lock()


def keyboard():
    global _kb
    if _kb is None:
        from pynput.keyboard import Controller

        _kb = Controller()
    return _kb


# Names you can use in shortcuts -> pynput Key attribute. Some keys only exist on some
# systems (a Mac has no Insert, Print Screen, Pause, Num Lock, Scroll Lock or Menu key), so
# names whose key isn't available here are simply left out.
KEY_NAMES = {
    "ctrl": "ctrl", "control": "ctrl", "shift": "shift", "alt": "alt", "option": "alt", "opt": "alt",
    "altgr": "alt_gr",
    "win": "cmd", "cmd": "cmd", "command": "cmd", "super": "cmd", "meta": "cmd", "windows": "cmd",
    "enter": "enter", "return": "enter", "esc": "esc", "escape": "esc", "tab": "tab", "space": "space",
    "backspace": "backspace", "delete": "delete", "del": "delete", "insert": "insert", "ins": "insert",
    "home": "home", "end": "end", "pageup": "page_up", "pgup": "page_up", "pagedown": "page_down", "pgdn": "page_down",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "capslock": "caps_lock", "numlock": "num_lock", "scrolllock": "scroll_lock", "pause": "pause",
    "printscreen": "print_screen", "prtsc": "print_screen", "menu": "menu",
    "media_play_pause": "media_play_pause", "playpause": "media_play_pause", "media_next": "media_next",
    "media_previous": "media_previous", "media_prev": "media_previous",
    "volume_up": "media_volume_up", "volume_down": "media_volume_down", "volume_mute": "media_volume_mute",
    "media_volume_up": "media_volume_up", "media_volume_down": "media_volume_down", "media_volume_mute": "media_volume_mute",
}


def _key_table():
    from pynput.keyboard import Key, KeyCode

    t = {name: getattr(Key, attr) for name, attr in KEY_NAMES.items() if hasattr(Key, attr)}
    t.update(plus=KeyCode.from_char("+"), minus=KeyCode.from_char("-"))
    if sys.platform == "win32":
        for n in range(1, 25):
            t[f"f{n}"] = KeyCode.from_vk(0x70 + n - 1)
    else:
        for n in range(1, 21):
            if hasattr(Key, f"f{n}"):
                t[f"f{n}"] = getattr(Key, f"f{n}")
    return t


def unavailable_key(name: str) -> bool:
    """A known key name that this system's keyboard doesn't have (e.g. insert on a Mac)."""
    return name in KEY_NAMES and name not in (_TABLE or {})


_TABLE = None


def parse_combo(combo: str):
    """'ctrl+shift+m' -> [Key.ctrl, Key.shift, KeyCode(vk=M)]"""
    from pynput.keyboard import KeyCode

    global _TABLE
    _TABLE = _TABLE or _key_table()
    keys = []
    parts = combo.strip().lower().split("+")
    if combo.strip().endswith("++"):  # "ctrl++" means ctrl and the plus key
        parts = parts[:-2] + ["plus"]
    for p in parts:
        p = p.strip()
        if not p:
            raise ActionError(f"Empty key in “{combo}”.")
        if p in _TABLE:
            keys.append(_TABLE[p])
        elif len(p) == 1 and (p.isalpha() and p.isascii() or p.isdigit()):
            # Windows: virtual-key codes are layout-independent. macOS uses characters.
            keys.append(KeyCode.from_vk(ord(p.upper())) if sys.platform == "win32" else KeyCode.from_char(p))
        elif len(p) == 1:
            keys.append(KeyCode.from_char(p))
        elif p in KEY_NAMES:
            raise ActionError(f"This computer's keyboard has no “{p}” key.")
        else:
            raise ActionError(f"Unknown key “{p}”.")
    return keys


def parse_keys(spec: str):
    if not isinstance(spec, str) or not spec.strip() or len(spec) > 200:
        raise ActionError("Enter a shortcut like ctrl+shift+m.")
    if spec.replace(" ", "").lower() in ("ctrl+alt+delete", "ctrl+alt+del"):
        raise ActionError("Windows doesn't allow programs to press Ctrl+Alt+Delete.")
    return [parse_combo(c) for c in spec.split()]


def press_keys(spec: str) -> None:
    combos = parse_keys(spec)
    kb = keyboard()
    with _lock:
        for i, keys in enumerate(combos):
            if i:
                time.sleep(0.04)
            pressed = []
            try:
                for k in keys:
                    kb.press(k)
                    pressed.append(k)
                    time.sleep(0.01)
            finally:
                for k in reversed(pressed):
                    kb.release(k)


def type_text(text: str) -> None:
    with _lock:
        keyboard().type(text)


class MacrosModule(Module):
    name = "macros"

    async def start(self) -> None:
        self.ctx.executors.update(keys=self.run_keys, text=self.run_text, steps=self.run_steps)

    async def run_keys(self, a: dict) -> None:
        await asyncio.to_thread(press_keys, a.get("keys", ""))

    async def run_text(self, a: dict) -> None:
        text = a.get("text")
        if not isinstance(text, str) or not text:
            raise ActionError("This snippet is empty.")
        await asyncio.to_thread(type_text, text)

    async def run_steps(self, a: dict) -> None:
        steps = a.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ActionError("This macro has no steps.")
        for st in steps[:100]:
            if "keys" in st:
                await asyncio.to_thread(press_keys, st["keys"])
            elif "text" in st:
                await asyncio.to_thread(type_text, str(st["text"]))
            elif "delay" in st:
                await asyncio.sleep(min(10.0, max(0.0, float(st["delay"]))))
            else:
                raise ActionError("Each step needs keys, text or delay.")

    # Live typing from the touchpad page's keyboard field.
    @action
    async def type(self, args, client):
        text = args.get("text")
        if not isinstance(text, str) or not text or len(text) > 5000:
            raise ActionError("Nothing to type.")
        await asyncio.to_thread(type_text, text)
        return True

    @action
    async def key(self, args, client):
        name = str(args.get("key", "")).lower()
        allowed = {"enter", "backspace", "tab", "esc", "delete", "up", "down", "left", "right", "home", "end",
                   "pageup", "pagedown", "space", "win", "media_play_pause", "volume_up", "volume_down", "volume_mute"}
        if name not in allowed:
            raise ActionError("That key isn't allowed here.")
        await asyncio.to_thread(press_keys, name)
        return True
