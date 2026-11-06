@echo off
cd /d "%~dp0"
set PY=%~dp0.venv\Scripts\python.exe

if not exist "%PY%" (
    echo [ERROR] venv not found. Run install.bat first.
    pause
    exit /b 1
)

set FAILED=0
for %%T in (test_programmer.py test_ocr_underscore.py selftest.py apptest.py test_lossless.py test_autostart.py test_settings.py) do (
    echo.
    echo ===== %%T =====
    "%PY%" -B "%~dp0tests\%%T"
    if errorlevel 1 set FAILED=1
)

echo.
if "%FAILED%"=="1" (
    echo [FAILED] some tests did not pass
    exit /b 1
)
echo [OK] all tests passed
