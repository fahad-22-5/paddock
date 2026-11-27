#!/bin/bash
# Run PadDock in this Terminal window (shows the URL, pairing code and QR code).
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "PadDock is not installed yet. Run ./setup.sh first."; exit 1; fi
exec .venv/bin/python run.py "$@"
