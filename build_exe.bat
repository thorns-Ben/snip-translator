@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv is missing. Create it before building.
    exit /b 1
)

call ".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo ERROR: failed to install build dependencies.
    exit /b 1
)

call ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean jietu.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\截图识字\*' -DestinationPath 'dist\截图识字.zip' -Force"
if errorlevel 1 (
    echo ERROR: release ZIP creation failed.
    exit /b 1
)

echo Build complete: dist\截图识字
echo Release ZIP: dist\截图识字.zip
exit /b 0
