#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCU6 桌面版入口（PyWebView + 内嵌 FastAPI）
============================================
架构：单进程
  - 后台线程：运行 uvicorn.Server 加载 server:app
  - 主线程：运行 PyWebView 窗口
  - 关闭窗口 → 主线程退出 → 守护线程自动终止

优势（相比 subprocess 方案）：
  1. 单进程，exe 打包更简单（无需处理子进程 Python 路径）
  2. 无端口冲突管理复杂度（同进程内 thread）
  3. 资源/生命周期统一，关闭即退出
  4. 日志统一写入同一文件

打包：
  pyinstaller --noconfirm --onedir --noconsole --name SCU6 app.py
  详见 build_exe.bat
"""
import os
import sys
import time
import socket
import threading
import traceback
import logging
import urllib.request
from pathlib import Path
from typing import Optional

# ─── 路径与配置 ────────────────────────────────────
# 打包模式（PyInstaller frozen）下，资源在 sys.executable 同级；
# 开发模式下，资源在脚本所在目录。
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

# 切换工作目录到项目根（server.py 的相对路径依赖此设定）
os.chdir(str(BASE_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 强制 UTF-8，避免 Windows GBK 编码崩溃
os.environ.setdefault("PYTHONUTF8", "1")

# SBERT/HuggingFace 离线模式（避免每次加载都连 huggingface.co 验证，国内网络常超时）
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# ─── noconsole 模式下重定向 stderr/stdout ────────────────────
# PyInstaller --noconsole 不分配 console，sys.stderr 不可用，
# 导致 uvicorn/logging 初始化崩溃。frozen 模式下无条件重定向到文件。
if getattr(sys, "frozen", False):
    try:
        _fallback_log = open(str(BASE_DIR / "scu5_stderr.log"), "w", encoding="utf-8")
        sys.stderr = _fallback_log
        sys.stdout = _fallback_log
    except Exception:
        pass

HOST = "127.0.0.1"
PORT = int(os.environ.get("SCU3_PORT", "8300"))
SERVER_URL = f"http://{HOST}:{PORT}"
STARTUP_TIMEOUT = 120  # 服务启动超时（秒）— SBERT 首次加载较慢
LOG_FILE = BASE_DIR / "scu5_launcher.log"

# ─── 日志 ────────────────────────────────────
_logger = logging.getLogger("SCU5.launcher")


def _setup_logging():
    """配置日志：同时输出到文件和 stderr"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(str(LOG_FILE), encoding="utf-8", mode="a"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def _log(msg: str):
    _logger.info(msg)


# ─── 服务端线程 ────────────────────────────────────
_server_thread: Optional[threading.Thread] = None
_server_started = threading.Event()
_server_error: Optional[str] = None


def _run_server():
    """在后台线程中加载并运行 FastAPI 服务（uvicorn.Server 直接驱动）

    通过导入 server 模块触发其模块级初始化（创建 ledger/guard/app 等），
    然后 uvicorn.Server.run() 阻塞运行，直到被中断或主线程退出。
    """
    global _server_error
    try:
        _log("导入 server 模块（触发 FastAPI app 初始化）...")
        # 设置环境变量，确保 server.py 启动时使用我们指定的 host/port
        os.environ.setdefault("SCU3_HOST", HOST)
        # 注意：server.py 的 __main__ 块读取 SCU3_PORT，但 uvicorn.Config 直接传入更可靠

        import uvicorn
        from server import app  # noqa: F401  触发模块级副作用

        _log(f"FastAPI app 已加载，开始监听 {HOST}:{PORT}")
        config = uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            log_level="warning",  # 减少 uvicorn 日志噪音
            access_log=False,
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        # 标记服务已就绪（即将进入 serve 循环）
        _server_started.set()
        server.run()
    except Exception as e:
        _server_error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _log(f"服务线程异常退出: {_server_error}")
        _server_started.set()  # 释放等待方
    finally:
        _server_started.set()


# ─── 探活 ────────────────────────────────────
def _is_port_open(host: str = HOST, port: int = PORT, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _is_http_ready(url: str = SERVER_URL, timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _wait_for_server() -> bool:
    """轮询等待 HTTP 服务就绪"""
    _log(f"等待后端就绪（最长 {STARTUP_TIMEOUT} 秒）...")
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        # 服务线程已崩溃则提前退出
        if _server_error:
            return False
        if _is_http_ready():
            _log("后端 HTTP 服务已就绪")
            return True
        time.sleep(0.4)
    _log("等待后端超时")
    return False


# ─── 错误对话框 ────────────────────────────────────
def _show_error_dialog(title: str, message: str):
    """显示错误对话框（优先用 Windows MessageBox，回退到 print）"""
    try:
        import ctypes
        # MB_ICONERROR | MB_TASKMODAL
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x2000)
    except Exception:
        print(f"[ERROR] {title}\n{message}", file=sys.stderr)


# ─── 主入口 ────────────────────────────────────
def main() -> int:
    _setup_logging()
    _log("=" * 60)
    _log("SCU5 桌面版启动（PyWebView + 内嵌 FastAPI）")
    _log(f"项目目录: {BASE_DIR}")
    _log(f"Python: {sys.executable}")
    _log(f"服务地址: {SERVER_URL}")

    # 1. 端口已占用检测：若已有服务在跑，直接开窗复用
    if _is_port_open():
        _log(f"端口 {PORT} 已被占用，假设服务已在运行，直接打开窗口")
        return _launch_webview()

    # 2. 启动服务线程
    global _server_thread
    _server_thread = threading.Thread(
        target=_run_server, name="SCU5-Server", daemon=True
    )
    _server_thread.start()
    _log(f"服务线程已启动 (PID={os.getpid()}, TID={_server_thread.ident})")

    # 3. 等待服务就绪
    if not _wait_for_server():
        err = _server_error or f"后端在 {STARTUP_TIMEOUT} 秒内未就绪"
        _log(f"启动失败: {err}")
        _show_error_dialog(
            "SCU5 启动失败",
            f"后端服务启动失败：\n\n{err}\n\n"
            f"日志文件：{LOG_FILE}\n"
            f"请检查端口 {PORT} 是否被占用或依赖是否完整。",
        )
        return 1

    # 4. 启动 PyWebView 窗口
    return _launch_webview()


def _launch_webview() -> int:
    """创建并运行 PyWebView 窗口"""
    try:
        import webview
    except ImportError as e:
        _log(f"pywebview 未安装: {e}")
        _show_error_dialog(
            "SCU5 缺少依赖",
            f"未找到 pywebview 库：{e}\n\n请运行：\npip install pywebview",
        )
        return 1

    _log("创建 PyWebView 窗口...")
    window = webview.create_window(
        title="SCU5 智能计算单元",
        url=SERVER_URL,
        width=1280,
        height=860,
        min_size=(900, 600),
        resizable=True,
        text_select=True,
        easy_drag=False,
        confirm_close=False,
    )

    try:
        # debug=False：发布模式；如需调试前端，改为 True
        webview.start(debug=False)
        _log("PyWebView 窗口已关闭")
    except Exception as e:
        _log(f"PyWebView 运行异常: {e}\n{traceback.format_exc()}")
        _show_error_dialog("SCU5 窗口异常", f"{type(e).__name__}: {e}")
        return 1
    finally:
        # 窗口关闭后，服务线程是守护线程，会随主线程退出而终止
        _log("SCU5 桌面版退出")

    return 0


if __name__ == "__main__":
    sys.exit(main())
