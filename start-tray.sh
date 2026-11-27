#!/bin/bash
# Run PadDock in the background with a menu bar icon (click it for the console and pairing code).
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "PadDock is not installed yet. Run ./setup.sh first."; exit 1; fi
nohup .venv/bin/python run.py --tray "$@" >/dev/null 2>&1 &
echo "PadDock is running in the menu bar."
