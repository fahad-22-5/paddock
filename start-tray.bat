@echo off
rem Run PadDock in the background with a system tray icon (right-click it for the pairing code).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo PadDock is not installed yet. Run setup.bat first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" run.py --tray %*
