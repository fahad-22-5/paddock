"""App launcher on macOS: runs exe/app/url/folder/shell actions from config.json with `open`.

    "safari":   {"type": "app",    "label": "Safari", "appid": "com.apple.Safari"}          (bundle id)
    "code":     {"type": "app",    "label": "VS Code", "appid": "/Applications/Visual Studio Code.app"}
    "report":   {"type": "exe",    "label": "Report", "path": "~/Documents/report.pdf"}     (any file or .app)
    "dl":       {"type": "folder", "label": "Downloads", "path": "~/Downloads"}
    "flush":    {"type": "shell",  "label": "Flush DNS", "command": "dscacheutil -flushcache", "window": true}
"""
from __future__ import annotations

import asyncio
import os
import shlex
import subprocess

from ...platform import applescript_quote, osascript
from ..base import ActionError, Module

DEVNULL = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def expand(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(str(path)))


def _args(a) -> list[str]:
    if isinstance(a, list):
        return [str(x) for x in a]
    return shlex.split(str(a or ""))


def _open(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise ActionError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip()
                          else f"Couldn't open it ({r.returncode}).")


class LauncherModule(Module):
    name = "launcher"

    async def start(self) -> None:
        self.ctx.executors.update(exe=self.run_exe, app=self.run_app, url=self.run_url,
                                  folder=self.run_folder, shell=self.run_shell)

    async def run_exe(self, a: dict) -> None:
        path = expand(a.get("path", ""))
        if not path:
            raise ActionError("This shortcut has no path in config.json.")
        if not os.path.exists(path):
            raise ActionError(f"Not found on this Mac: {path}")
        args = _args(a.get("args"))
        if path.rstrip("/").endswith(".app"):
            cmd = ["open", "-a", path] + (["--args", *args] if args else [])
        elif os.path.isfile(path) and os.access(path, os.X_OK) and not a.get("admin"):
            # A command-line program or script: start it directly.
            cwd = expand(a["cwd"]) if a.get("cwd") else os.path.dirname(path)
            subprocess.Popen([path, *args], cwd=cwd, start_new_session=True, **DEVNULL)
            return
        else:
            cmd = ["open", path]  # a document: opens in its default app
        if a.get("admin"):
            # Asks for your password on the Mac.
            line = " ".join(shlex.quote(c) for c in ([path, *args] if not path.endswith(".app") else cmd))
            await asyncio.to_thread(osascript, f"do shell script {applescript_quote(line)} with administrator privileges", 300)
            return
        await asyncio.to_thread(_open, cmd)

    async def run_app(self, a: dict) -> None:
        appid = str(a.get("appid", "")).strip()
        if not appid:
            raise ActionError("This app shortcut has no app id.")
        args = _args(a.get("args"))
        target = ["-a", expand(appid)] if appid.startswith(("/", "~")) or appid.endswith(".app") else ["-b", appid]
        await asyncio.to_thread(_open, ["open", *target] + (["--args", *args] if args else []))

    async def run_url(self, a: dict) -> None:
        url = str(a.get("url", ""))
        if not url:
            raise ActionError("This link has no URL.")
        if a.get("origin") == "ipad" and not url.lower().startswith(("http://", "https://")):
            raise ActionError("Links made on a device must start with http:// or https://")
        await asyncio.to_thread(_open, ["open", url])

    async def run_folder(self, a: dict) -> None:
        path = expand(a.get("path", ""))
        if not os.path.isdir(path):
            raise ActionError(f"Folder not found: {path}")
        await asyncio.to_thread(_open, ["open", path])

    async def run_shell(self, a: dict) -> None:
        cmd = a.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise ActionError("This command is empty in config.json.")
        cwd = expand(a["cwd"]) if a.get("cwd") else os.path.expanduser("~")
        if a.get("window"):
            line = f"cd {shlex.quote(cwd)} && {cmd}"
            await asyncio.to_thread(osascript, f'tell application "Terminal"\nactivate\ndo script {applescript_quote(line)}\nend tell')
            return
        try:
            subprocess.Popen(["/bin/zsh", "-lc", cmd], cwd=cwd, start_new_session=True, **DEVNULL)
        except OSError as e:
            raise ActionError(f"Couldn't run the command: {e.strerror}")
