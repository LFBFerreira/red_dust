@echo off
setlocal
rem One-time setup: creates Red Dust Control Center\.venv and installs dependencies
rem from requirements_windows.txt. Safe to run again to refresh pip or reinstall.

set "APP_DIR=%~dp0..\Red Dust Control Center"
set "VENV_PY=%APP_DIR%\.venv\Scripts\python.exe"

cd /d "%APP_DIR%" || (
  echo Could not find application folder next to Scripts.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH. Install from python.org and try again.
  pause
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
  )
)

echo Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo pip upgrade failed.
  pause
  exit /b 1
)

echo Installing packages from requirements_windows.txt...
"%VENV_PY%" -m pip install -r requirements_windows.txt
if errorlevel 1 (
  echo pip install failed.
  pause
  exit /b 1
)

echo.
echo Done. You can use "Launch RDCC win.cmd" to start the app.
pause
