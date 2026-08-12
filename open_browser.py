# -*- coding: utf-8 -*-
"""
SCU5 浏览器自动打开助手
======================
轮询后端端口，服务就绪后自动打开默认浏览器
独立运行，不影响后端进程
"""
import time
import socket
import webbrowser
import sys

HOST = "127.0.0.1"
PORT = 8300
URL = f"http://{HOST}:{PORT}/"
MAX_WAIT = 60  # 最长等待 60 秒


def is_port_open(host=HOST, port=PORT, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def main():
    # 等待端口就绪
    waited = 0
    while waited < MAX_WAIT:
        if is_port_open():
            # 端口开了，再多等 1 秒让 HTTP 服务完全就绪
            time.sleep(1)
            break
        time.sleep(0.5)
        waited += 0.5
    else:
        print(f"[open_browser] 等待 {MAX_WAIT} 秒后端口仍未开放，放弃打开浏览器", file=sys.stderr)
        return 1

    # 打开浏览器
    try:
        webbrowser.open(URL, new=2)
        print(f"[open_browser] 已打开浏览器: {URL}")
    except Exception as e:
        print(f"[open_browser] 打开浏览器失败: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
