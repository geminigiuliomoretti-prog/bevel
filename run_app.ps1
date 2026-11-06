# ==============================================================================
# WHOOP 4.0 / 5.0 REVERSE-ENGINEERED CLIENT - ONE-CLICK LAUNCH SCRIPT
# Microsoft Surface Pro / Windows 11 Desktop (Pure Dart, Zero Cloud, SQLite WAL)
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$Release,
    [switch]$Android
)

$ErrorActionPreference = "Stop"
$BevelRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WhoopAppDir = Join-Path $BevelRoot "whoop_app"
$LocalDbPath = Join-Path $BevelRoot "data\whoop_local.db"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host " WHOOP LOCAL CLIENT - 100% REVERSE-ENGINEERED (ZERO CLOUD)" -ForegroundColor Cyan
Write-Host " Target Hardware: WHOOP B (FD:49:44:66:1D:92, FW 50.41.1.0)" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

# 1. Check SQLite Database
if (Test-Path $LocalDbPath) {
    $dbSize = (Get-Item $LocalDbPath).Length / 1MB
    Write-Host "[OK] SQLite Database located: $LocalDbPath ($([Math]::Round($dbSize, 2)) MB)" -ForegroundColor Green
} else {
    Write-Host "[WARN] SQLite Database not found at $LocalDbPath! Initializing default..." -ForegroundColor Yellow
}

# 2. Locate Flutter SDK
$FlutterBin = "C:\flutter\bin\flutter.bat"
if (-not (Test-Path $FlutterBin)) {
    $flutterCmd = Get-Command "flutter" -ErrorAction SilentlyContinue
    if ($flutterCmd) {
        $FlutterBin = $flutterCmd.Source
    } else {
        Write-Error "Flutter SDK not found at C:\flutter\bin\flutter.bat or in system PATH."
        exit 1
    }
}
Write-Host "[OK] Flutter SDK: $FlutterBin" -ForegroundColor Green

# 3. Determine target device
Set-Location $WhoopAppDir

if ($Android) {
    Write-Host "`n[START] Launching Whoop App on Android Device..." -ForegroundColor Cyan
    & $FlutterBin run -d android
} else {
    Write-Host "`n[START] Launching Whoop App on Windows 11 Desktop (Direct BLE & SQLite WAL)..." -ForegroundColor Cyan
    if ($Release) {
        & $FlutterBin run -d windows --release
    } else {
        & $FlutterBin run -d windows
    }
}
