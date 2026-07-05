@echo off
setlocal
rem Double-click this file to start Red Dust Control Center with a visible console
rem for log output while the app runs. Uses Red Dust Control Center\.venv

set "APP_DIR=%~dp0..\Red Dust Control Center"
set "VENV_PY=%APP_DIR%\.venv\Scripts\python.exe"

cd /d "%APP_DIR%" || (
  echo Could not find application folder next to Scripts.
  pause
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo Virtual environment not found at:
  echo   %VENV_PY%
  echo.
  echo Run "Setup venv win.bat" in Scripts once, then try again.
  pause
  exit /b 1
)

"%VENV_PY%" main.py
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
  echo.
  echo Exited with error code %EXITCODE%.
  pause
)

exit /b %EXITCODE%
