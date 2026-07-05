@echo off
rem Export portable RDCC bundle -> export\red_dust.zip
rem See README.md for installation on Windows, macOS, and Raspberry Pi.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scripts\Export RDCC.ps1"
if errorlevel 1 pause
