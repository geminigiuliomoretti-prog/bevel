@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Initializing...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip install -r requirements.txt
)

set PYTHONPATH=.
.venv\Scripts\python.exe main.py %*
pause
