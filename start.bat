@echo off
rem Run PadDock with a console window (shows the URL, pairing code and QR code).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo PadDock is not installed yet. Run setup.bat first.
  pause
  exit /b 1
)
title PadDock
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 pause
