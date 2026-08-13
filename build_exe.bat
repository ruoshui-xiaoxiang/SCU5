@echo off
chcp 65001 >nul
title SCU5 桌面版打包工具

cd /d "%~dp0"

echo ================================================
echo   SCU5 桌面版打包 (PyWebView + FastAPI)
echo ================================================
echo.

REM ─── Python 路径探测 ───
set "TRAE_PY=C:\Users\若水\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe"
set "PY_EXE="
if exist "%TRAE_PY%" set "PY_EXE=%TRAE_PY%"
if "%PY_EXE%"=="" (
    where python >nul 2>&1
    if not errorlevel 1 set "PY_EXE=python"
)
if "%PY_EXE%"=="" (
    echo [ERROR] 未找到 Python
    pause
    exit /b 1
)

echo   Python : %PY_EXE%
echo.

REM ─── 检查 PyInstaller ───
"%PY_EXE%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] PyInstaller 未安装，正在安装...
    "%PY_EXE%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller 安装失败
        pause
        exit /b 1
    )
)

REM ─── 清理旧文件 ───
echo [INFO] 清理旧构建产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__
if exist SCU5.spec del /q SCU5.spec

REM ─── 打包 ───
echo.
echo [INFO] 开始打包（onedir 模式，无黑框）...
echo.

"%PY_EXE%" -m PyInstaller --noconfirm --onedir --noconsole ^
    --name "SCU5" ^
    --hidden-import=webview ^
    --hidden-import=webview.platforms.winforms ^
    --hidden-import=uvicorn ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.loops.asyncio ^
    --hidden-import=uvicorn.protocols ^
    --hidden-import=uvicorn.protocols.http ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.protocols.http.h11_impl ^
    --hidden-import=uvicorn.protocols.websockets ^
    --hidden-import=uvicorn.protocols.websockets.auto ^
    --hidden-import=uvicorn.lifespan ^
    --hidden-import=uvicorn.lifespan.on ^
    --hidden-import=fastapi ^
    --hidden-import=starlette ^
    --hidden-import=pydantic ^
    --hidden-import=h11 ^
    --hidden-import=anyio ^
    --hidden-import=sniffio ^
    --hidden-import=httpx ^
    --hidden-import=sklearn ^
    --hidden-import=sklearn.feature_extraction ^
    --hidden-import=sklearn.metrics.pairwise ^
    --hidden-import=numpy ^
    --hidden-import=sentence_transformers ^
    --exclude-module=tkinter ^
    --exclude-module=matplotlib ^
    --exclude-module=PyQt5 ^
    --exclude-module=PyQt6 ^
    --exclude-module=PySide2 ^
    --exclude-module=PySide6 ^
    --collect-data webview ^
    --collect-data sentence_transformers ^
    app.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败
    pause
    exit /b 1
)

REM ─── 复制资源到 dist/SCU5/ ───
echo.
echo [INFO] 复制 web 静态资源...
if not exist "dist\SCU5\web" mkdir "dist\SCU5\web"
xcopy /y /e /i "web\*" "dist\SCU5\web\" >nul

echo [INFO] 复制 docs 文档...
if not exist "dist\SCU5\docs" mkdir "dist\SCU5\docs"
xcopy /y /e /i "docs\*" "dist\SCU5\docs\" >nul

echo [INFO] 复制 domain_plugins 配置...
if not exist "dist\SCU5\domain_plugins" mkdir "dist\SCU5\domain_plugins"
xcopy /y /e /i "domain_plugins\*" "dist\SCU5\domain_plugins\" >nul

echo [INFO] 复制 config 配置...
if not exist "dist\SCU5\config" mkdir "dist\SCU5\config"
xcopy /y /e /i "config\*" "dist\SCU5\config\" >nul

echo [INFO] 复制 d_layer 清单...
if not exist "dist\SCU5\d_layer" mkdir "dist\SCU5\d_layer"
copy /y "d_layer\MANIFEST.json" "dist\SCU5\d_layer\" >nul

echo.
echo ================================================
echo   打包完成！
echo   输出目录: dist\SCU5\
echo   主程序:   dist\SCU5\SCU5.exe
echo ================================================
echo.
echo   使用方法：
echo     1. 直接双击 dist\SCU5\SCU5.exe 启动
echo     2. 或将整个 dist\SCU5\ 文件夹分发
echo.
pause
