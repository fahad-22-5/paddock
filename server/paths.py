"""Filesystem locations.

Two layouts:
  * From source (run.py / start.bat / start.sh): everything lives in the project folder.
  * Installed app (PadDock.exe or PadDock.app, built with PyInstaller): the program files
    are read-only resources, and your settings/data go to
      Windows: %APPDATA%\\PadDock
      macOS:   ~/Library/Application Support/PadDock
PADDOCK_HOME (environment variable) overrides where settings and data are kept.
"""
import os
import sys
from pathlib import Path

from .platform import IS_MAC, user_data_root

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))  # bundled resources
    INSTALL_DIR = Path(sys.executable).resolve().parent
    USER_DIR = user_data_root() / "PadDock"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    INSTALL_DIR = APP_DIR
    USER_DIR = APP_DIR

if os.environ.get("PADDOCK_HOME"):
    USER_DIR = Path(os.environ["PADDOCK_HOME"]).expanduser().resolve()

ROOT = APP_DIR  # kept for older imports
WEB_DIR = APP_DIR / "web"
# Default layout and shortcuts differ per system (Windows programs vs Mac apps).
EXAMPLE_CONFIG_PATH = APP_DIR / ("config.example.macos.json" if IS_MAC else "config.example.json")
CONFIG_PATH = USER_DIR / "config.json"
DATA_DIR = USER_DIR / "data"

DEVICES_PATH = DATA_DIR / "devices.json"
NOTES_PATH = DATA_DIR / "notes.md"
CERT_DIR = DATA_DIR / "certs"
ICON_CACHE_DIR = DATA_DIR / "icons"
LOG_PATH = DATA_DIR / "paddock.log"
# Written when running from source; the installer reads it to offer importing settings.
SOURCE_HINT = user_data_root() / "PadDock-source-folder.txt"


def ensure_dirs() -> None:
    for d in (USER_DIR, DATA_DIR, CERT_DIR, ICON_CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
