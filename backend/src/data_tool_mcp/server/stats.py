"""轻量级请求计数器 — 按天统计工具调用次数。

用于 Dashboard 的"今日请求"指标。采用内存计数(无 DB 持久化),
重启后归零,符合"今日请求"的语义且实现最简。

跨日时自动重置计数器。
"""

from __future__ import annotations

import threading
from datetime import date


class RequestCounter:
    """线程安全的按天请求计数器。"""

    def __init__(self) -> None:
        """初始化实例。"""
        self._lock = threading.Lock()
        self._date: date = date.today()
        self._count: int = 0

    def increment(self, n: int = 1) -> None:
        """递增计数(跨日自动重置)。"""
        today = date.today()
        with self._lock:
            if today != self._date:
                self._date = today
                self._count = 0
            self._count += n

    def get_today_count(self) -> int:
        """获取今日计数(跨日自动重置)。"""
        today = date.today()
        with self._lock:
            if today != self._date:
                self._date = today
                self._count = 0
            return self._count


# 全局单例
_counter = RequestCounter()


def get_request_counter() -> RequestCounter:
    """获取全局请求计数器单例。"""
    return _counter
