@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0.venv\Scripts\python.exe" goto missing
"%~dp0.venv\Scripts\python.exe" "%~dp0windows_launcher.py" xlsx "%~1"
set "W2_EXIT=%ERRORLEVEL%"
goto finish
:missing
echo Please run install.bat first.
set "W2_EXIT=2"
:finish
echo.
pause
exit /b %W2_EXIT%
