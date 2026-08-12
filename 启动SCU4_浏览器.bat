@echo off
cd /d "%~dp0"
title SCU4
setlocal

set "PORT=8300"
set "URL=http://127.0.0.1:%PORT%/"
set "TRAE_PY=C:\Users\若水\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe"
set "PY_EXE="

if exist "%TRAE_PY%" set "PY_EXE=%TRAE_PY%"
if "%PY_EXE%"=="" (
    where python >nul 2>&1
    if not errorlevel 1 set "PY_EXE=python"
)
if "%PY_EXE%"=="" (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

echo ============================================================
echo   SCU4 Smart Computing Unit
echo ============================================================
echo   Python : %PY_EXE%
echo   URL    : %URL%
echo ============================================================
echo.

netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [INFO] Port %PORT% in use, opening browser...
    start "" "%URL%"
    timeout /t 3 >nul
    exit /b 0
)

echo [INFO] Starting backend + browser helper...
echo.
set "PYTHONUTF8=1"
start "" /B "%PY_EXE%" open_browser.py
"%PY_EXE%" server.py

echo.
echo [INFO] Backend exited (code %errorlevel%)
pause
