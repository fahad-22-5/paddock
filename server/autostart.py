"""Start PadDock at login with a shortcut in your Startup folder (no admin rights needed).

Installed app: the shortcut runs PadDock.exe. From source: the venv's pythonw.exe with
run.py --tray. You can also delete it by hand: Win+R, shell:startup, remove PadDock.lnk.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .paths import APP_DIR, FROZEN, INSTALL_DIR

SHORTCUT_NAME = "PadDock.lnk"


def startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def is_enabled() -> bool:
    return shortcut_path().exists()


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def make_shortcut(lnk: Path, target: Path, args: str = "", workdir: Path | None = None,
                  icon: Path | None = None, description: str = "PadDock") -> Path:
    """Create a Windows .lnk shortcut (via the WScript.Shell COM object in PowerShell)."""
    lnk.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(str(lnk)) + ");"
        "$s.TargetPath=" + _ps_quote(str(target)) + ";"
        "$s.Arguments=" + _ps_quote(args) + ";"
        "$s.WorkingDirectory=" + _ps_quote(str(workdir or target.parent)) + ";"
        + ("$s.IconLocation=" + _ps_quote(str(icon)) + ";" if icon else "")
        + "$s.Description=" + _ps_quote(description) + ";"
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return lnk


def launch_command() -> tuple[Path, str, Path, Path]:
    """(target, arguments, working folder, icon) that start PadDock in the background."""
    if FROZEN:
        exe = INSTALL_DIR / "PadDock.exe"
        return exe, "--tray", INSTALL_DIR, exe
    pyw = Path(sys.executable).with_name("pythonw.exe")
    target = pyw if pyw.exists() else Path(sys.executable)
    return target, f'"{APP_DIR / "run.py"}" --tray', APP_DIR, APP_DIR / "web" / "icons" / "paddock.ico"


def enable() -> Path:
    target, args, workdir, icon = launch_command()
    return make_shortcut(shortcut_path(), target, args, workdir, icon, "PadDock dock server")


def disable() -> bool:
    try:
        shortcut_path().unlink()
        return True
    except FileNotFoundError:
        return False
