@echo off
rem Open the PadDock management console (PadDock must be running).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo PadDock is not installed yet. Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py --console
if errorlevel 1 pause
