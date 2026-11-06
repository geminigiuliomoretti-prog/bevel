@echo off
setlocal
title WHOOP Local Client - Windows Desktop
echo ====================================================================
echo  WHOOP LOCAL CLIENT - 100%% REVERSE-ENGINEERED (ZERO CLOUD)
echo  Target Hardware: WHOOP B (FD:49:44:66:1D:92, FW 50.41.1.0)
echo ====================================================================

set FLUTTER_BIN=C:\flutter\bin\flutter.bat
if not exist "%FLUTTER_BIN%" (
    where flutter >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Flutter SDK not found! Please check C:\flutter\bin\flutter.bat
        pause
        exit /b 1
    ) else (
        set FLUTTER_BIN=flutter
    )
)

echo [OK] Using Flutter SDK: %FLUTTER_BIN%
cd /d "%~dp0whoop_app"

echo [START] Building and Launching on Windows Desktop...
call "%FLUTTER_BIN%" run -d windows

if errorlevel 1 (
    echo [ERROR] Application failed to launch or exited with errors.
    pause
)
endlocal
