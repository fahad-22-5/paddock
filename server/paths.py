"""Filesystem locations.

Two layouts:
  * From source (run.py / start.bat): everything lives in the project folder, as before.
  * Installed app (PadDock.exe, built with PyInstaller): the program files are read-only
    resources next to the exe, and your settings/data go to %APPDATA%\\PadDock.
PADDOCK_HOME (environment variable) overrides where settings and data are kept.
"""
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))  # bundled resources
    INSTALL_DIR = Path(sys.executable).resolve().parent
    USER_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PadDock"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    INSTALL_DIR = APP_DIR
    USER_DIR = APP_DIR

if os.environ.get("PADDOCK_HOME"):
    USER_DIR = Path(os.environ["PADDOCK_HOME"]).resolve()

ROOT = APP_DIR  # kept for older imports
WEB_DIR = APP_DIR / "web"
EXAMPLE_CONFIG_PATH = APP_DIR / "config.example.json"
CONFIG_PATH = USER_DIR / "config.json"
DATA_DIR = USER_DIR / "data"

DEVICES_PATH = DATA_DIR / "devices.json"
NOTES_PATH = DATA_DIR / "notes.md"
CERT_DIR = DATA_DIR / "certs"
ICON_CACHE_DIR = DATA_DIR / "icons"
LOG_PATH = DATA_DIR / "paddock.log"
# Written when running from source; the installer reads it to offer importing settings.
SOURCE_HINT = Path(os.environ.get("APPDATA", Path.home())) / "PadDock-source-folder.txt"


def ensure_dirs() -> None:
    for d in (USER_DIR, DATA_DIR, CERT_DIR, ICON_CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
