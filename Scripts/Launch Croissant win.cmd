@echo off
setlocal
rem Double-click this file to start Croissant Control Center with a visible console.
rem Uses Red Dust Control Center\.venv

set "APP_DIR=%~dp0..\Croissant Control Center"
set "VENV_PY=%~dp0..\Red Dust Control Center\.venv\Scripts\python.exe"

cd /d "%APP_DIR%" || (
  echo Could not find Croissant Control Center next to Scripts.
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
