@echo off
echo [SYSTEM] Initializing new project environment...

:: 1. Create the venv if it doesn't exist
if not exist .venv (
    echo [SYSTEM] Creating .venv...
    py -m venv .venv
)

:: 2. Upgrade pip and install requirements
echo [SYSTEM] Installing dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
if exist requirements.txt (
    .venv\Scripts\pip install -r requirements.txt
)

echo.
echo [SUCCESS] Environment ready!
echo You can now open this folder in VS Code or launch via scripts_menu.py
pause