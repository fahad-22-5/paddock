"""Which operating system PadDock runs on, and the few helpers that differ between them.

Feature modules come in a Windows and a macOS flavour (see server/modules/__init__.py);
everything else is shared.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
NAME = "windows" if IS_WINDOWS else "macos" if IS_MAC else sys.platform
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# How the UI should talk about things that differ per system.
WORDS = {
    "tray": "menu bar icon" if IS_MAC else "tray icon",
    "launcher_menu": "Launchpad" if IS_MAC else "Start menu",
    "meta_key": "cmd" if IS_MAC else "win",
}


def user_data_root() -> Path:
    """Where an installed app keeps per-user settings."""
    if IS_MAC:
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("APPDATA", Path.home()))


def open_path(target: str | os.PathLike) -> None:
    """Open a file, folder or URL with its default app."""
    if IS_WINDOWS:
        os.startfile(target)  # noqa: S606 - the user's own file
    elif IS_MAC:
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def applescript_quote(text: str) -> str:
    """Quote a string for embedding in AppleScript."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def osascript(script: str, timeout: float = 10) -> str:
    """Run AppleScript and return its output (macOS only). Raises RuntimeError on failure."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"osascript failed ({r.returncode})")
    return r.stdout.strip()


def message_box(text: str, error: bool = False, title: str = "PadDock") -> None:
    """Show a simple dialog (used by the background app, which has no console)."""
    if IS_WINDOWS:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
    elif IS_MAC:
        icon = "stop" if error else "note"
        try:
            osascript(f'display dialog {applescript_quote(text)} with title {applescript_quote(title)} '
                      f'buttons {{"OK"}} default button "OK" with icon {icon}', timeout=600)
        except Exception:
            pass
    else:
        print(text, file=sys.stderr)
