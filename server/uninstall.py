"""Uninstaller for the installed app: `PadDock.exe --uninstall`.

Windows runs this from Settings → Apps → Installed apps → PadDock → Uninstall.
Everything was installed per user, so no admin rights are needed.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile

if sys.platform == "win32":
    import winreg
from pathlib import Path

from . import autostart
from .paths import FROZEN, INSTALL_DIR, USER_DIR

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PadDock"
MB_YESNO, MB_ICONQUESTION, MB_ICONINFO, IDYES = 0x04, 0x20, 0x40, 6
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def start_menu_shortcut() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "PadDock.lnk"


def desktop_shortcut() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop" / "PadDock.lnk"


def _ask(text: str) -> bool:
    return ctypes.windll.user32.MessageBoxW(None, text, "Uninstall PadDock", MB_YESNO | MB_ICONQUESTION) == IDYES


def _tell(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, "Uninstall PadDock", MB_ICONINFO)


def uninstall() -> None:
    if not FROZEN or sys.platform != "win32":
        print("Uninstall only applies to the installed Windows app. On a Mac, quit PadDock and move it to the Trash.")
        return
    if not _ask("Remove PadDock from this PC?"):
        return

    # Stop any other running PadDock (the tray app).
    subprocess.run(["taskkill", "/F", "/IM", "PadDock.exe", "/FI", f"PID ne {os.getpid()}"],
                   capture_output=True, creationflags=NO_WINDOW)

    autostart.disable()
    for lnk in (start_menu_shortcut(), desktop_shortcut()):
        try:
            lnk.unlink()
        except FileNotFoundError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass

    if USER_DIR.exists() and _ask(
            "Also delete your PadDock settings?\n\n"
            f"{USER_DIR}\n\n"
            "This removes your layout, shortcuts, notes, paired devices and the certificate. "
            "Choose No to keep them for a later reinstall."):
        shutil.rmtree(USER_DIR, ignore_errors=True)

    _tell("PadDock was removed.")
    # This exe can't delete its own folder while running: let cmd do it a moment later.
    subprocess.Popen(
        f'cmd /c timeout /t 2 /nobreak >nul & rmdir /s /q "{INSTALL_DIR}"',
        cwd=tempfile.gettempdir(), creationflags=NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )
