"""带引用计数的 LRU 缓存 — 用于 Source 对象的 cache-aside 模式。

设计要点:
  - maxsize: 最大缓存数量,超出淘汰最久未访问项(LRU)
  - 引用计数 > 0 时不淘汰,防止正在使用的 source 被 dispose 导致连接池失效
  - 淘汰时调用 close_callback 释放底层连接池
  - 主动失效(evict)标记为"待淘汰",引用归零时真正淘汰

适用场景:
  - Source 对象持有 AsyncEngine 连接池,不能频繁创建销毁
  - 上千数据源场景下,仅活跃 source 占用内存和连接
  - 多实例部署时,配合主动失效实现一致性
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class LRUCache:
    """带引用计数的 LRU 缓存。

    - get(key): 查询缓存,命中时更新 LRU 顺序,引用计数 +1
    - release(key): 引用计数 -1,归零且标记待淘汰时真正淘汰
    - set(key, value): 写入缓存,如果超出 maxsize 淘汰最久未访问项
    - evict(key): 主动失效,引用计数为 0 立即淘汰,否则标记待淘汰
    - clear(): 清空全部缓存(关闭所有 source)
    """

    def __init__(
        self,
        maxsize: int,
        close_callback: Callable[[Any], Awaitable[None]] | None = None,
    ):
        self._maxsize = maxsize
        self._close_callback = close_callback
        # 有序字典: 尾部为最近访问,头部为最久未访问
        self._cache: OrderedDict[str, Any] = OrderedDict()
        # 引用计数: 记录每个 key 被引用次数(正在使用中)
        self._refcount: dict[str, int] = {}
        # 待淘汰集合: 引用计数 > 0 时被 evict,标记后 release 归零时真正淘汰
        self._pending_evict: set[str] = set()
        # 异步锁: 保护内部状态(淘汰时调用 close_callback 是 async)
        self._lock = asyncio.Lock()

    def get(self, key: str) -> Any | None:
        """查询缓存,命中时更新 LRU 顺序。不增加引用计数(由 acquire 负责)。

        待淘汰(key in _pending_evict)的项视为未命中,防止 update/remove 后
        仍有请求获取到旧 source。
        """
        if key not in self._cache or key in self._pending_evict:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        """写入缓存。如果超出 maxsize,淘汰最久未访问且引用计数为 0 的项。"""
        self._upsert(key, value)
        self._evict_if_over_capacity()

    def _upsert(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache[key] = value
            self._cache.move_to_end(key)
            return
        self._cache[key] = value

    def _evict_if_over_capacity(self) -> None:
        while len(self._cache) > self._maxsize:
            if self._evict_one_lru():
                continue
            logger.warning(
                "LRU 缓存超限但所有项都在使用中(%d/%d),临时跳过淘汰",
                len(self._cache), self._maxsize,
            )
            break

    def _evict_one_lru(self) -> bool:
        """淘汰一个最久未访问且未被引用的项。返回 True 表示已淘汰。"""
        for k in list(self._cache.keys()):
            if self._refcount.get(k, 0) > 0:
                continue
            self._remove_entry(k)
            logger.debug("LRU 淘汰: %s (容量超限)", k)
            return True
        return False

    def _remove_entry(self, key: str) -> None:
        """同步移除缓存项并异步关闭(用于 set 容量超限时)。"""
        val = self._cache.pop(key)
        self._refcount.pop(key, None)
        self._pending_evict.discard(key)
        if val is not None and self._close_callback:
            asyncio.create_task(self._safe_close(key, val))

    def acquire(self, key: str) -> None:
        """引用计数 +1。配合 get() 使用,表示该 source 正在被使用。"""
        self._refcount[key] = self._refcount.get(key, 0) + 1

    async def release(self, key: str) -> None:
        """引用计数 -1。归零且标记待淘汰时真正淘汰。

        防御性设计: 如果 refcount 已经为 0(可能是 get_source 失败后的多余
        release 调用),直接返回,不触发误淘汰。
        """
        async with self._lock:
            await self._decrement_ref(key)

    async def _decrement_ref(self, key: str) -> None:
        current = self._refcount.get(key, 0)
        if current <= 0:
            return
        count = current - 1
        if count > 0:
            self._refcount[key] = count
            return
        await self._release_final_ref(key)

    async def _release_final_ref(self, key: str) -> None:
        """引用归零时移除 refcount,若标记待淘汰则真正淘汰。"""
        self._refcount.pop(key, None)
        if key not in self._pending_evict:
            return
        self._pending_evict.discard(key)
        val = self._cache.pop(key, None)
        await self._safe_close_if_needed(key, val)
        logger.debug("引用归零后淘汰: %s", key)

    async def _safe_close_if_needed(self, key: str, val: Any) -> None:
        """有 close_callback 且值非空时关闭,否则跳过。"""
        if val is None or not self._close_callback:
            return
        await self._safe_close(key, val)

    async def evict(self, key: str) -> None:
        """主动失效。引用计数为 0 立即淘汰,否则标记待淘汰。"""
        async with self._lock:
            await self._evict_locked(key)

    async def _evict_locked(self, key: str) -> None:
        if key not in self._cache:
            self._pending_evict.discard(key)
            return
        if self._refcount.get(key, 0) > 0:
            self._pending_evict.add(key)
            logger.debug("标记待淘汰(使用中): %s", key)
            return
        await self._evict_immediately(key)

    async def _evict_immediately(self, key: str) -> None:
        """引用计数为 0 时立即淘汰缓存项。"""
        val = self._cache.pop(key)
        self._refcount.pop(key, None)
        await self._safe_close_if_needed(key, val)
        logger.debug("主动失效: %s", key)

    async def clear(self) -> None:
        """清空全部缓存。正在使用中的项也会被关闭(用于关闭流程)。"""
        async with self._lock:
            items = list(self._cache.items())
            self._cache.clear()
            self._refcount.clear()
            self._pending_evict.clear()
        await self._close_items(items)

    async def _close_items(self, items: list[tuple[str, Any]]) -> None:
        """在锁外批量关闭缓存项,避免长时间持锁。"""
        for key, val in items:
            await self._safe_close_if_needed(key, val)

    def contains(self, key: str) -> bool:
        return key in self._cache

    def size(self) -> int:
        return len(self._cache)

    def keys(self) -> list[str]:
        return list(self._cache.keys())

    def snapshot(self) -> dict[str, Any]:
        """返回缓存项快照(不更新 LRU 顺序)。用于 get_sources_map 等只读场景。"""
        return dict(self._cache)

    def reset(self, items: dict[str, Any]) -> None:
        """替换全部缓存内容,不关闭旧项(由调用方负责关闭)。

        用于 hot-reload 的 set_resources: 调用方已捕获 old_sources 并单独关闭。
        重置引用计数和待淘汰集合。
        """
        self._cache = OrderedDict(items)
        self._refcount.clear()
        self._pending_evict.clear()

    def replace(self, key: str, value: Any) -> Any | None:
        """原子替换缓存项,返回旧值(不关闭)。

        用于 add_source 场景: 先移除旧值(清除 refcount 和 pending_evict),
        再写入新值。调用方负责异步关闭返回的旧值。

        与 evict+set 组合的区别: evict 在 refcount>0 时只标记不 pop,
        随后 set 会覆盖旧值导致泄漏; replace 直接 pop 旧值,保证原子性。
        """
        old = self._cache.pop(key, None)
        self._refcount.pop(key, None)
        self._pending_evict.discard(key)
        self._cache[key] = value
        return old

    async def _safe_close(self, key: str, val: Any) -> None:
        """安全调用 close_callback,捕获异常避免影响主流程。"""
        try:
            await self._close_callback(val)
        except Exception as e:
            logger.warning("关闭缓存项 %s 失败: %s", key, e)
