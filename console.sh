#!/bin/bash
# Open the PadDock management console (PadDock must be running).
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "PadDock is not installed yet. Run ./setup.sh first."; exit 1; fi
exec .venv/bin/python run.py --console
