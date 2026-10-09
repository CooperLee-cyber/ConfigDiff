@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm ConfigDiff.spec
if errorlevel 1 exit /b 1
copy /Y "dist\ConfigDiff.exe" "ConfigDiff.exe" >nul
if errorlevel 1 exit /b 1
echo Built: dist\ConfigDiff.exe
echo Built: ConfigDiff.exe
