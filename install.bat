@echo off
cd /d "%~dp0"

echo === OCR Screenshot Tool - Install ===
echo.

where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python launcher "py" not found.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating venv with Python 3.12 ...
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Need Python 3.12.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Venv already exists, skipped.
)

echo [2/3] Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency install failed.
    pause
    exit /b 1
)

echo [3/3] Import check (offline) ...
".venv\Scripts\python.exe" -c "import jietu.ocr_engine, jietu.capture, jietu.main, run; print('imports OK')"
if errorlevel 1 (
    echo [ERROR] Import check failed. Dependencies may be broken.
    pause
    exit /b 1
)

echo.
echo === Done. Double-click the Chinese-named starter batch file to start. ===
pause
