@echo off
setlocal

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Pixora.ps1"
if errorlevel 1 (
  echo.
  echo Pixora did not start successfully.
  echo.
  echo Make sure Python is installed, then try again.
  echo.
  pause
)
