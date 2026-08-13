# -*- coding: utf-8 -*-
"""
api/middleware.py - 统一中间件与异步工具（SCU5.1 增强）
=========================================================
解决已知限制：
  - 限制1：输入验证中间件（统一路径校验，替代手动调用 safe_join_path）
  - 限制3：事件循环监控探针（检测同步阻塞）
  - 限制6：同步->异步包装工具 run_sync（替代逐个 asyncio.to_thread）
"""
import os
import re
import time
import asyncio
import logging
import threading
from typing import Dict, Any, Optional, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from w1_layer.path_utils import safe_join_path

logger = logging.getLogger("SCU3.api.middleware")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ==================== 限制1：路径校验中间件 ====================

PATH_CHECK_RULES: Dict[str, Dict[str, str]] = {
    "/multimodal/image":   {"path": "SCU3_data"},
    "/multimodal/audio":   {"path": "SCU3_data"},
    "/multimodal/video":   {"path": "SCU3_data"},
    "/vision/chat":        {"image_path": "SCU3_data"},
    "/self-modify/propose": {"target_file": ""},
}

TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e%2f", re.I),
    re.compile(r"%2e%2e%5c", re.I),
    re.compile(r"\.\.%2f", re.I),
    re.compile(r"\.\.%5c", re.I),
]


class PathValidationMiddleware(BaseHTTPMiddleware):
    """统一路径校验中间件（限制1）"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. 快速拦截 URL 中的目录穿越特征
        raw_url = str(request.url)
        for pat in TRAVERSAL_PATTERNS:
            if pat.search(raw_url):
                logger.warning(f"路径校验中间件拦截目录穿越: {path}")
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "非法路径：禁止目录穿越"}
                )

        # 2. 对登记端点校验路径字段
        rules = PATH_CHECK_RULES.get(path)
        if rules:
            try:
                body = await request.body()
                if body:
                    import json
                    try:
                        data = json.loads(body)
                    except Exception:
                        data = {}
                    for field, allowed_root in rules.items():
                        user_path = data.get(field, "")
                        if not user_path:
                            continue
                        # SCU5.1: URL 解码后再校验（防止 %2e%2e%2f 绕过）
                        import urllib.parse as _urlparse
                        _decoded = _urlparse.unquote(user_path)
                        allowed_abs = os.path.join(BASE_DIR, allowed_root) if allowed_root else BASE_DIR
                        safe = safe_join_path(_decoded, allowed_abs)
                        if safe is None:
                            logger.warning(f"路径校验中间件拦截越界路径: {path}.{field}={user_path}")
                            return JSONResponse(
                                status_code=400,
                                content={"success": False, "error": f"路径越界：{field} 必须在 {allowed_root or '项目根'} 内"}
                            )
            except Exception as e:
                logger.warning(f"路径校验中间件异常(放行): {e}")

        return await call_next(request)


# ==================== 限制3：事件循环监控探针 ====================

class EventLoopMonitor:
    """事件循环延迟监控（限制3）"""

    def __init__(self, warn_threshold: float = 0.5, interval: float = 5.0):
        self.warn_threshold = warn_threshold
        self.interval = interval
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._latencies: list = []
        self._max_latency: float = 0.0
        self._block_count: int = 0

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="loop_monitor")
        self._thread.start()
        logger.info(f"事件循环监控探针已启动 (间隔={self.interval}s, 告警阈值={self.warn_threshold}s)")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self):
        while not self._stop_event.is_set():
            if self._loop is None or not self._loop.is_running():
                if self._stop_event.wait(1.0):
                    return
                continue
            try:
                start = time.monotonic()
                fut = asyncio.run_coroutine_threadsafe(self._probe(), self._loop)
                latency = fut.result(timeout=self.warn_threshold * 4 + 1.0)
                elapsed = time.monotonic() - start
                actual = max(elapsed, latency)
                self._record(actual)
            except asyncio.TimeoutError:
                self._record(self.warn_threshold * 4)
                logger.warning(f"事件循环探针超时(>{self.warn_threshold*4:.1f}s)，疑似同步阻塞")
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.debug(f"事件循环探针异常: {e}")
            self._stop_event.wait(self.interval)

    async def _probe(self) -> float:
        return 0.001

    def _record(self, latency: float):
        self._latencies.append(latency)
        if len(self._latencies) > 100:
            self._latencies.pop(0)
        if latency > self._max_latency:
            self._max_latency = latency
        if latency > self.warn_threshold:
            self._block_count += 1
            logger.warning(f"事件循环延迟 {latency:.3f}s 超阈值 {self.warn_threshold}s")

    def stats(self) -> Dict[str, Any]:
        if not self._latencies:
            return {"enabled": bool(self._thread and self._thread.is_alive()), "samples": 0}
        avg = sum(self._latencies) / len(self._latencies)
        return {
            "enabled": bool(self._thread and self._thread.is_alive()),
            "samples": len(self._latencies),
            "avg_latency_ms": round(avg * 1000, 2),
            "max_latency_ms": round(self._max_latency * 1000, 2),
            "block_count": self._block_count,
            "warn_threshold_ms": round(self.warn_threshold * 1000, 2),
            "interval_s": self.interval,
        }


_loop_monitor = EventLoopMonitor()


def get_loop_monitor() -> EventLoopMonitor:
    return _loop_monitor


# ==================== 限制6：同步->异步包装工具 ====================

async def run_sync(func: Callable, *args, **kwargs) -> Any:
    """统一的同步->异步包装工具（限制6）

    替代逐个调用 asyncio.to_thread，集中管理同步调用的异步包装。
    """
    return await asyncio.to_thread(func, *args, **kwargs)


class LoopMonitorMiddleware(BaseHTTPMiddleware):
    """在 /health 响应头中附加事件循环延迟信息"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/health":
            try:
                stats = _loop_monitor.stats()
                if stats.get("samples", 0) > 0:
                    response.headers["X-Loop-Latency-Avg"] = str(stats["avg_latency_ms"])
                    response.headers["X-Loop-Latency-Max"] = str(stats["max_latency_ms"])
                    response.headers["X-Loop-Block-Count"] = str(stats["block_count"])
            except Exception:
                pass
        return response
