"""Installed Mac apps (for the console's "Add installed app") and native file pickers."""
from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from ...platform import applescript_quote

APP_DIRS = [
    Path("/Applications"), Path("/Applications/Utilities"),
    Path("/System/Applications"), Path("/System/Applications/Utilities"),
    Path.home() / "Applications", Path.home() / "Applications" / "Chrome Apps.localized",
]


def read_app(app: Path) -> dict | None:
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
    except Exception:
        return None
    if info.get("LSUIElement") in (True, "1") or info.get("LSBackgroundOnly") in (True, "1"):
        return None  # helpers and background agents, not apps you launch
    name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or app.stem
    bundle = info.get("CFBundleIdentifier")
    return {"name": str(name), "appid": bundle or str(app), "icon": str(app), "path": str(app)}


def installed_apps() -> list[dict]:
    seen, out = set(), []
    for d in APP_DIRS:
        if not d.is_dir():
            continue
        for app in sorted(d.glob("*.app")):
            a = read_app(app)
            if a and a["appid"] not in seen:
                seen.add(a["appid"])
                out.append(a)
    out.sort(key=lambda a: a["name"].lower())
    return out


def pick(kind: str, initial: str | None = None) -> str | None:
    """A native macOS file/folder chooser via AppleScript. Returns a POSIX path or None."""
    where = ""
    if initial:
        p = os.path.expanduser(initial)
        p = p if os.path.isdir(p) else os.path.dirname(p)
        if os.path.isdir(p):
            where = f" default location (POSIX file {applescript_quote(p)})"
    if kind == "folder":
        chooser = f'choose folder with prompt "Choose a folder for PadDock"{where}'
    elif kind == "icon":
        chooser = f'choose file with prompt "Choose an icon (an app, .icns or .png)"{where}'
    else:
        chooser = f'choose file with prompt "Choose an app or file for PadDock"{where}'
    script = f'''tell application "System Events"
    activate
    set chosen to {chooser}
end tell
return POSIX path of chosen'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return None  # cancelled (error -128) or not allowed
    path = r.stdout.strip()
    return path.rstrip("/") if path.endswith(".app/") else (path or None)
