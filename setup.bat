@echo off
rem PadDock one-command setup: creates .venv, installs dependencies, creates config.json.
setlocal
cd /d "%~dp0"
title PadDock setup

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during installation, then run setup.bat again.
  pause
  exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo PadDock needs Python 3.10 or newer. You have:
  %PY% --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

echo Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

if not exist "config.json" (
  copy /y "config.example.json" "config.json" >nul
  echo Created config.json from config.example.json
)

echo.
echo ============================================================
echo  PadDock is installed.
echo    start.bat        run with a console window (shows the pairing code)
echo    start-tray.bat   run in the background with a tray icon
echo ============================================================
echo.
choice /c YN /m "Start PadDock automatically when you log in (tray icon)"
if errorlevel 2 goto :run
".venv\Scripts\python.exe" run.py --install-autostart

:run
echo.
choice /c YN /m "Start PadDock now"
if errorlevel 2 goto :eof
call "%~dp0start.bat"
goto :eof

:fail
echo.
echo Setup failed. Scroll up for the error message.
pause
exit /b 1
