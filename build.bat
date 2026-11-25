@echo off
rem Build the standalone PadDock app and installer into dist\ (needs setup.bat to have run once).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --quiet -r requirements-build.txt
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" tools\build.py
if errorlevel 1 goto :fail
echo.
echo Done. The installer is in the dist folder.
pause
exit /b 0
:fail
echo Build failed. Scroll up for the error.
pause
exit /b 1
