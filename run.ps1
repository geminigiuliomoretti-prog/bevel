# PowerShell launcher for WHOOP 5.0 BLE Diagnostic Toolkit
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[!] Virtual environment not found. Initializing..." -ForegroundColor Yellow
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip install -r requirements.txt
}

$env:PYTHONPATH = "."
& .venv\Scripts\python.exe main.py @args
