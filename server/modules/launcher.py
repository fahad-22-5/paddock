"""App launcher: runs actions of type exe, url, folder and shell, as defined in config.json.

    "chrome":  {"type": "exe",    "label": "Chrome", "path": "C:/Program Files/Google/Chrome/Application/chrome.exe", "args": "--new-window"}
    "github":  {"type": "url",    "label": "GitHub", "url": "https://github.com"}
    "dl":      {"type": "folder", "label": "Downloads", "path": "%USERPROFILE%/Downloads"}
    "flush":   {"type": "shell",  "label": "Flush DNS", "command": "ipconfig /flushdns", "window": false}

Options: "admin": true runs an exe elevated (Windows asks for consent on the PC),
"cwd" sets the working directory, "icon" can be an emoji or a path to .ico/.png/.exe.
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
from ctypes import wintypes

from .base import ActionError, Module

shell32 = ctypes.WinDLL("shell32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
shell32.ShellExecuteW.restype = wintypes.HINSTANCE
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
SW_SHOWNORMAL = 1
ASFW_ANY = 0xFFFFFFFF

SHELL_ERRORS = {2: "File not found", 3: "Path not found", 5: "Access denied", 8: "Out of memory",
                26: "Sharing violation", 27: "File association incomplete", 31: "No app is associated with this file", 32: "DLL not found"}


def shell_execute(target: str, params: str = "", cwd: str | None = None, verb: str = "open") -> None:
    # Let the app we start take the foreground; we're a background process.
    user32.AllowSetForegroundWindow(ASFW_ANY)
    rc = shell32.ShellExecuteW(None, verb, target, params or None, cwd, SW_SHOWNORMAL)
    rc = int(rc or 0)
    if rc <= 32:
        if verb == "runas" and rc == 5:
            raise ActionError("Cancelled on the PC.")
        raise ActionError(f"Couldn't open {os.path.basename(target) or target}: {SHELL_ERRORS.get(rc, f'error {rc}')}")


def _args(a) -> str:
    if isinstance(a, list):
        return subprocess.list2cmdline([str(x) for x in a])
    return str(a or "")


class LauncherModule(Module):
    name = "launcher"

    async def start(self) -> None:
        self.ctx.executors.update(exe=self.run_exe, url=self.run_url, folder=self.run_folder, shell=self.run_shell,
                                  app=self.run_app)

    async def run_app(self, a: dict) -> None:
        """An app from the Start menu (desktop or Store app), started the way Start does it."""
        appid = str(a.get("appid", ""))
        if not appid or '"' in appid:
            raise ActionError("This app shortcut has no app id.")
        await asyncio.to_thread(shell_execute, f"shell:AppsFolder\\{appid}")

    async def run_exe(self, a: dict) -> None:
        path = os.path.expandvars(str(a.get("path", "")))
        if not path:
            raise ActionError("This shortcut has no path in config.json.")
        if os.path.isabs(path) and not os.path.exists(path):
            raise ActionError(f"Not found on the PC: {path}")
        cwd = os.path.expandvars(a["cwd"]) if a.get("cwd") else (os.path.dirname(path) if os.path.isabs(path) else None)
        await asyncio.to_thread(shell_execute, path, _args(a.get("args")), cwd, "runas" if a.get("admin") else "open")

    async def run_url(self, a: dict) -> None:
        url = str(a.get("url", ""))
        if not url:
            raise ActionError("This link has no URL.")
        if a.get("origin") == "ipad" and not url.lower().startswith(("http://", "https://")):
            raise ActionError("Links made on a device must start with http:// or https://")
        await asyncio.to_thread(shell_execute, url)

    async def run_folder(self, a: dict) -> None:
        path = os.path.expandvars(str(a.get("path", "")))
        if not os.path.isdir(path):
            raise ActionError(f"Folder not found: {path}")
        await asyncio.to_thread(shell_execute, path, "", None, "explore")

    async def run_shell(self, a: dict) -> None:
        cmd = a.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise ActionError("This command is empty in config.json.")
        flags = subprocess.CREATE_NEW_CONSOLE if a.get("window") else subprocess.CREATE_NO_WINDOW
        cwd = os.path.expandvars(a["cwd"]) if a.get("cwd") else None
        try:
            subprocess.Popen(cmd, shell=True, cwd=cwd, creationflags=flags | subprocess.CREATE_NEW_PROCESS_GROUP,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            raise ActionError(f"Couldn't run the command: {e.strerror}")
