#!/bin/bash
# PadDock setup for macOS: creates .venv, installs dependencies, creates config.json.
set -e
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "PadDock needs Python 3.10 or newer. Install it with:  brew install python   (https://brew.sh)"
  echo "or from https://www.python.org/downloads/macos/ , then run ./setup.sh again."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating virtual environment in .venv with $($PY --version) ..."
  "$PY" -m venv .venv
fi
echo "Installing dependencies ..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f config.json ]; then
  cp config.example.macos.json config.json
  echo "Created config.json from config.example.macos.json"
fi

cat <<'MSG'

============================================================
 PadDock is installed.
   ./start.sh        run in this Terminal window (shows the pairing code)
   ./start-tray.sh   run in the background with a menu bar icon
   ./console.sh      open the management console

 macOS will ask for a few permissions the first time:
   * "Accept incoming network connections?"  -> Allow
   * Accessibility (keyboard shortcuts, touchpad, lock screen):
       System Settings > Privacy & Security > Accessibility -> allow Terminal / Python
   * "PadDock wants to control Spotify / Music"  -> OK (now playing)
 For now playing from every app (browsers too):  brew install media-control
============================================================
MSG

read -r -p "Start PadDock automatically when you log in? [y/N] " yn
if [[ "$yn" =~ ^[Yy] ]]; then .venv/bin/python run.py --install-autostart; fi
read -r -p "Start PadDock now? [Y/n] " yn
if [[ ! "$yn" =~ ^[Nn] ]]; then exec ./start.sh; fi
