@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 goto launcher
where python >nul 2>nul
if not errorlevel 1 goto python
echo Python 3.10 or newer is required. Get it from https://www.python.org/downloads/
echo Install Python, then double-click START.cmd again. No miner was started.
pause
exit /b 1
:launcher
py -3 "%~dp0mainnet_kit.py"
goto finished
:python
python "%~dp0mainnet_kit.py"
:finished
echo.
echo Mainnet Kit closed. Press any key to close this window.
pause >nul
