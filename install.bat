@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows_install.ps1"
set "W2_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %W2_EXIT%
