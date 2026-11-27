#!/bin/bash
# Build PadDock.app (+ .dmg and .zip) into dist/ (run ./setup.sh once first).
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "Run ./setup.sh first."; exit 1; fi
.venv/bin/python -m pip install --quiet -r requirements-build.txt
.venv/bin/python tools/build.py
echo "Done. The app is in the dist folder."
