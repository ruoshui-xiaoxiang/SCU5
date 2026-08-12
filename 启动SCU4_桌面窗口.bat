@echo off
cd /d "%~dp0"
title SCU4 WebView
setlocal

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
echo   SCU4 Desktop (WebView)
echo   Python : %PY_EXE%
echo ============================================================
echo.

set "PYTHONUTF8=1"
"%PY_EXE%" app.py

if errorlevel 1 (
    echo.
    echo [ERROR] Startup failed
    pause
)
