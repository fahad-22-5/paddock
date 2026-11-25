"""PadDock installer (built into PadDock-Setup-<version>.exe by tools/build.py).

Installs per user, with no admin rights:
  * program files  -> %LOCALAPPDATA%\\Programs\\PadDock  (or a folder you choose)
  * Start menu shortcut, optional desktop shortcut, optional start at login
  * an entry in Settings → Apps → Installed apps (uninstall from there)
  * optionally imports settings, pairings and the certificate from a source checkout,
    so an already-paired device keeps working

Command line (for testing or scripted installs):
  PadDock-Setup.exe --silent [--dir PATH] [--no-autostart] [--no-desktop] [--no-launch]
                    [--no-startmenu] [--no-register] [--import DIR | --no-import]
"""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import winreg
import zipfile
from pathlib import Path

from server import __version__
from server.autostart import make_shortcut, startup_dir
from server.uninstall import UNINSTALL_KEY, desktop_shortcut, start_menu_shortcut

APP_NAME = "PadDock"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PAYLOAD = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "PadDock.zip"
DEFAULT_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / APP_NAME
USER_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME


SOURCE_HINT = Path(os.environ.get("APPDATA", Path.home())) / "PadDock-source-folder.txt"


def has_settings(d: Path) -> bool:
    return (d / "data" / "devices.json").exists() or (d / "data" / "certs" / "ca.crt").exists() or (d / "config.json").exists()


def has_pairings(d: Path) -> bool:
    try:
        import json

        return bool(json.loads((d / "data" / "devices.json").read_text("utf-8")))
    except (OSError, ValueError):
        return False


def find_existing_setup() -> Path | None:
    """A PadDock source folder with settings to import: the one the source version last ran
    from (it leaves a note in %APPDATA%), or one near this setup file (e.g. project/dist/)."""
    candidates = []
    try:
        candidates.append(Path(SOURCE_HINT.read_text("utf-8").strip()))
    except OSError:
        pass
    here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    candidates += [here, *list(here.parents)[:3]]
    for d in candidates:
        if d != USER_DIR and d.is_dir() and has_settings(d):
            return d
    return None


def paddock_running() -> bool:
    """Is any PadDock (installed app or start.bat) answering on this PC?"""
    import json

    port = 8766
    for cfg in (USER_DIR / "config.json",):
        try:
            port = int(json.loads(cfg.read_text("utf-8"))["server"]["setup_port"])
        except Exception:
            pass
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/console/", timeout=1.5)
        return True
    except Exception:
        return False


class Installer:
    def __init__(self, target: Path, autostart: bool, desktop: bool, startmenu: bool, register: bool,
                 import_from: Path | None, launch: bool, log=print):
        self.target, self.autostart, self.desktop = target, autostart, desktop
        self.startmenu, self.register, self.import_from, self.launch = startmenu, register, import_from, launch
        self.log = log

    @property
    def exe(self) -> Path:
        return self.target / "PadDock.exe"

    def run(self) -> str | None:
        """Install. Returns a note for the user, if any."""
        self.log("Closing a running PadDock (if any)…")
        subprocess.run(["taskkill", "/F", "/IM", "PadDock.exe"], capture_output=True, creationflags=NO_WINDOW)

        self.log("Copying program files…")
        internal = self.target / "_internal"
        if internal.exists():
            shutil.rmtree(internal, ignore_errors=True)  # clean upgrade
        self.target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(PAYLOAD) as z:
            z.extractall(self.target)

        if self.import_from:
            self.log("Importing your settings and pairings…")
            self._import(self.import_from)

        if self.startmenu:
            self.log("Adding the Start menu shortcut…")
            make_shortcut(start_menu_shortcut(), self.exe, "", self.target, self.exe, "PadDock touch dock")
        if self.desktop:
            make_shortcut(desktop_shortcut(), self.exe, "", self.target, self.exe, "PadDock touch dock")
        if self.autostart:
            self.log("Starting PadDock at login…")
            make_shortcut(startup_dir() / "PadDock.lnk", self.exe, "--tray", self.target, self.exe, "PadDock dock server")
        if self.register:
            self.log("Registering with Windows…")
            self._register()

        note = None
        if self.launch:
            if paddock_running():
                note = ("Another PadDock is still running (probably start.bat). Close that window, "
                        "then start PadDock from the Start menu.")
            else:
                self.log("Starting PadDock…")
                subprocess.Popen([str(self.exe)], cwd=self.target, creationflags=subprocess.DETACHED_PROCESS, close_fds=True)
        self.log("Done.")
        return note

    def _import(self, src: Path) -> None:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        if (USER_DIR / "config.json").exists() or (USER_DIR / "data").exists():
            backup = USER_DIR.with_name(f"PadDock-backup-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.copytree(USER_DIR, backup, dirs_exist_ok=True)
            self.log(f"Previous settings backed up to {backup}")
        if (src / "config.json").exists():
            shutil.copy2(src / "config.json", USER_DIR / "config.json")
        if (src / "data" / "certs").is_dir():
            shutil.rmtree(USER_DIR / "data" / "certs", ignore_errors=True)  # use the certificate the device trusts
        if (src / "data").is_dir():
            shutil.copytree(src / "data", USER_DIR / "data", dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.log", "*.out.log", "setup-test"))

    def _register(self) -> None:
        size_kb = sum(f.stat().st_size for f in self.target.rglob("*") if f.is_file()) // 1024
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            for name, value in {
                "DisplayName": APP_NAME, "DisplayVersion": __version__, "Publisher": APP_NAME,
                "DisplayIcon": f"{self.exe},0", "InstallLocation": str(self.target),
                "UninstallString": f'"{self.exe}" --uninstall',
                "Comments": "Touch dock and control panel for your PC, on your tablet or phone",
            }.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
            for name, value in {"NoModify": 1, "NoRepair": 1, "EstimatedSize": size_kb}.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)


# ---- window ------------------------------------------------------------------
def gui(existing: Path | None) -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk

    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    bg, fg, sub, accent = "#11141a", "#f3f5f9", "#9aa1b0", "#0a84ff"
    root = tk.Tk()
    root.title(f"Install {APP_NAME}")
    root.configure(bg=bg)
    root.resizable(False, False)
    try:
        root.iconbitmap(str(Path(getattr(sys, "_MEIPASS", ".")) / "paddock.ico"))
    except Exception:
        pass
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TCheckbutton", background=bg, foreground=fg, font=("Segoe UI", 10))
    style.map("TCheckbutton", background=[("active", bg)])
    style.configure("Horizontal.TProgressbar", troughcolor="#222733", background=accent, bordercolor=bg, lightcolor=accent, darkcolor=accent)

    pad = {"padx": 28}
    tk.Label(root, text=f"PadDock {__version__}", bg=bg, fg=fg, font=("Segoe UI Semibold", 20)).pack(anchor="w", pady=(24, 0), **pad)
    tk.Label(root, text="Turn a tablet or phone into a touch dock for this PC.", bg=bg, fg=sub, font=("Segoe UI", 10)).pack(anchor="w", **pad)

    tk.Label(root, text="Install to", bg=bg, fg=sub, font=("Segoe UI", 9)).pack(anchor="w", pady=(18, 2), **pad)
    row = tk.Frame(root, bg=bg)
    row.pack(fill="x", **pad)
    target = tk.StringVar(value=str(DEFAULT_DIR))
    entry = tk.Entry(row, textvariable=target, width=52, bg="#1b1f28", fg=fg, insertbackground=fg, relief="flat", font=("Segoe UI", 10))
    entry.pack(side="left", ipady=6, fill="x", expand=True)

    def browse():
        d = filedialog.askdirectory(initialdir=target.get(), title="Install PadDock to")
        if d:
            target.set(str(Path(d) / APP_NAME) if Path(d).name.lower() != APP_NAME.lower() else d)

    tk.Button(row, text="Browse…", command=browse, bg="#252a35", fg=fg, relief="flat", activebackground="#2e3442",
              activeforeground=fg, font=("Segoe UI", 10), padx=12).pack(side="left", padx=(8, 0), ipady=3)

    opts = tk.Frame(root, bg=bg)
    opts.pack(fill="x", pady=(16, 0), **pad)
    v_auto, v_desk, v_launch = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
    ttk.Checkbutton(opts, text="Start PadDock when I log in (runs in the tray)", variable=v_auto).pack(anchor="w", pady=2)
    ttk.Checkbutton(opts, text="Create a desktop shortcut", variable=v_desk).pack(anchor="w", pady=2)
    ttk.Checkbutton(opts, text="Start PadDock when setup finishes", variable=v_launch).pack(anchor="w", pady=2)

    # Import from a PadDock that ran from source (keeps paired devices and their certificate).
    v_import = tk.BooleanVar(value=existing is not None and not has_pairings(USER_DIR))
    import_dir = tk.StringVar(value=str(existing) if existing else "")
    imp = tk.Frame(root, bg=bg)
    imp.pack(fill="x", pady=(12, 0), **pad)
    ttk.Checkbutton(imp, text="Import settings and paired devices from a PadDock folder:", variable=v_import).pack(anchor="w")
    irow = tk.Frame(imp, bg=bg)
    irow.pack(fill="x", pady=(4, 0))
    tk.Entry(irow, textvariable=import_dir, width=52, bg="#1b1f28", fg=fg, insertbackground=fg, relief="flat",
             font=("Segoe UI", 10)).pack(side="left", ipady=6, fill="x", expand=True)

    def browse_import():
        d = filedialog.askdirectory(initialdir=import_dir.get() or str(Path.home()), title="Your PadDock folder (with config.json and data)")
        if d:
            import_dir.set(d)
            v_import.set(True)

    tk.Button(irow, text="Browse…", command=browse_import, bg="#252a35", fg=fg, relief="flat", activebackground="#2e3442",
              activeforeground=fg, font=("Segoe UI", 10), padx=12).pack(side="left", padx=(8, 0), ipady=3)
    tk.Label(imp, text="Use the folder you ran start.bat from, so paired devices keep working without setting them up again.",
             bg=bg, fg=sub, font=("Segoe UI", 9), wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))

    status = tk.Label(root, text="Settings and pairings are kept in " + str(USER_DIR), bg=bg, fg=sub, font=("Segoe UI", 9), wraplength=520, justify="left")
    status.pack(anchor="w", pady=(16, 6), **pad)
    bar = ttk.Progressbar(root, mode="indeterminate", style="Horizontal.TProgressbar", length=520)

    btns = tk.Frame(root, bg=bg)
    btns.pack(fill="x", pady=(8, 24), **pad)
    install_btn = tk.Button(btns, text="Install", bg=accent, fg="white", relief="flat", activebackground="#3d9bff",
                            activeforeground="white", font=("Segoe UI Semibold", 11), padx=26, pady=6)
    install_btn.pack(side="right")
    cancel_btn = tk.Button(btns, text="Cancel", command=root.destroy, bg="#252a35", fg=fg, relief="flat", activebackground="#2e3442",
                           activeforeground=fg, font=("Segoe UI", 11), padx=18, pady=6)
    cancel_btn.pack(side="right", padx=(0, 10))

    def say(text):
        root.after(0, lambda: status.config(text=text, fg=sub))

    def finished(note, error=None):
        bar.stop()
        bar.pack_forget()
        if error:
            status.config(text=f"Setup failed: {error}", fg="#ff453a")
            install_btn.config(state="normal", text="Try again")
            cancel_btn.config(state="normal")
            return
        status.config(text=note or "PadDock is installed. Find it in the Start menu; it lives in the tray.",
                      fg="#ff9f0a" if note else "#30d158")
        install_btn.config(text="Close", state="normal", command=root.destroy)
        cancel_btn.pack_forget()

    def go():
        install_btn.config(state="disabled")
        cancel_btn.config(state="disabled")
        bar.pack(anchor="w", before=btns, **pad)
        bar.start(12)
        src = Path(import_dir.get().strip()) if v_import.get() and import_dir.get().strip() else None
        if src and not has_settings(src):
            finished(None, f"No PadDock settings found in {src} (it should contain config.json or a data folder).")
            return
        inst = Installer(Path(target.get()), v_auto.get(), v_desk.get(), True, True, src, v_launch.get(), log=say)

        def work():
            try:
                note = inst.run()
                root.after(0, lambda: finished(note))
            except Exception as e:  # show it in the window
                root.after(0, lambda: finished(None, e))

        threading.Thread(target=work, daemon=True).start()

    install_btn.config(command=go)
    root.mainloop()


def main() -> None:
    p = argparse.ArgumentParser(description="Install PadDock")
    p.add_argument("--silent", action="store_true")
    p.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--no-autostart", action="store_true")
    p.add_argument("--no-desktop", action="store_true")
    p.add_argument("--no-launch", action="store_true")
    p.add_argument("--no-startmenu", action="store_true")
    p.add_argument("--no-register", action="store_true")
    p.add_argument("--import", dest="import_dir", type=Path)
    p.add_argument("--no-import", action="store_true")
    a = p.parse_args()
    existing = None if a.no_import else (a.import_dir or find_existing_setup())
    if not a.silent:
        gui(existing)
        return
    if existing and has_pairings(USER_DIR) and not a.import_dir:
        existing = None  # don't overwrite an installed app that already has paired devices
    note = Installer(a.dir, not a.no_autostart, not a.no_desktop, not a.no_startmenu, not a.no_register,
                     existing, not a.no_launch, log=lambda m: None).run()
    if note:
        print(note)


if __name__ == "__main__":
    main()
