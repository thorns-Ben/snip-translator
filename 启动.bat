@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERROR] venv not found. Run install.bat first.
    echo.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -B run.py
exit /b 0
