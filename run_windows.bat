@echo off
title WiZ Smart Light Launcher
cd /d "%~dp0"

echo ========================================================
echo        WiZ Smart Light Remote - Windows Launcher
echo ========================================================

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Check for dependencies
pip show pillow >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Pillow and Pystray...
    pip install -r requirements.txt
)

pip show pystray >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Pystray...
    pip install pystray
)

:: Launch widget silently without keeping CMD open
echo Starting WiZ Remote Widget...
start "" pythonw widget.pyw
exit
