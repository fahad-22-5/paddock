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


def _key_table():
    from pynput.keyboard import Key, KeyCode

    t = {
        "ctrl": Key.ctrl, "control": Key.ctrl, "shift": Key.shift, "alt": Key.alt, "altgr": Key.alt_gr,
        "win": Key.cmd, "cmd": Key.cmd, "super": Key.cmd, "meta": Key.cmd, "windows": Key.cmd,
        "enter": Key.enter, "return": Key.enter, "esc": Key.esc, "escape": Key.esc, "tab": Key.tab, "space": Key.space,
        "backspace": Key.backspace, "delete": Key.delete, "del": Key.delete, "insert": Key.insert, "ins": Key.insert,
        "home": Key.home, "end": Key.end, "pageup": Key.page_up, "pgup": Key.page_up, "pagedown": Key.page_down, "pgdn": Key.page_down,
        "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
        "capslock": Key.caps_lock, "numlock": Key.num_lock, "scrolllock": Key.scroll_lock, "pause": Key.pause,
        "printscreen": Key.print_screen, "prtsc": Key.print_screen, "menu": Key.menu,
        "media_play_pause": Key.media_play_pause, "playpause": Key.media_play_pause, "media_next": Key.media_next,
        "media_previous": Key.media_previous, "media_prev": Key.media_previous,
        "volume_up": Key.media_volume_up, "volume_down": Key.media_volume_down, "volume_mute": Key.media_volume_mute,
        "media_volume_up": Key.media_volume_up, "media_volume_down": Key.media_volume_down, "media_volume_mute": Key.media_volume_mute,
        "plus": KeyCode.from_char("+"), "minus": KeyCode.from_char("-"),
    }
    if sys.platform == "win32":
        for n in range(1, 25):
            t[f"f{n}"] = KeyCode.from_vk(0x70 + n - 1)
    else:
        for n in range(1, 21):
            if hasattr(Key, f"f{n}"):
                t[f"f{n}"] = getattr(Key, f"f{n}")
        t.update(option=Key.alt, opt=Key.alt, command=Key.cmd)
    return t


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
