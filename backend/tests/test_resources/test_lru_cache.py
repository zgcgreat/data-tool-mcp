"""LRU 缓存 + 引用计数的竞态场景测试。

验证方案 C 修复的 3 个严重 bug:
  1. add_source 的 evict+set 竞态(replace 方法修复)
  2. release 多余调用不触发误淘汰
  3. remove_source/invalidate 后 get_source 不命中已删除 source
  4. execute_query/list_source_tables 中 acquire 后 raise 的 refcount 泄漏
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from data_tool_mcp.resources.lru_cache import LRUCache


class FakeSource:
    """模拟 Source 对象,跟踪 close 调用次数。"""

    def __init__(self, name: str):
        self.name = name
        self.close_count = 0

    async def close(self):
        self.close_count += 1


async def _close_callback(source: FakeSource):
    await source.close()


@pytest.fixture
def cache():
    return LRUCache(maxsize=3, close_callback=_close_callback)


class TestLRUGet:
    """Bug 3: pending_evict 中的 key 视为未命中。"""

    async def test_get_returns_none_for_pending_evict(self, cache: LRUCache):
        """标记待淘汰后,get 应返回 None,防止获取到旧 source。"""
        src = FakeSource("old")
        cache.set("src1", src)
        cache.acquire("src1")  # refcount=1,正在使用
        await cache.evict("src1")  # 标记待淘汰(refcount>0 不 pop)

        # get 应返回 None(待淘汰),不是旧 source
        assert cache.get("src1") is None
        assert src.close_count == 0  # 旧 source 未关闭(refcount>0)

        # release 后 refcount 归零,真正淘汰
        await cache.release("src1")
        assert src.close_count == 1


class TestLRURelease:
    """Bug 2: release 多余调用不触发误淘汰。"""

    async def test_release_with_zero_refcount_is_noop(self, cache: LRUCache):
        """refcount=0 时 release 不应触发淘汰(防止 get_source 失败后的多余 release)。"""
        src = FakeSource("src1")
        cache.set("src1", src)
        # 没有 acquire,直接 release
        await cache.release("src1")
        # source 仍在缓存中,未被淘汰
        assert cache.get("src1") is src
        assert src.close_count == 0

    async def test_release_does_not_evict_active_source(self, cache: LRUCache):
        """refcount=2 时一次 release 不应触发淘汰,即使 key 在 pending_evict 中。"""
        src = FakeSource("src1")
        cache.set("src1", src)
        cache.acquire("src1")  # refcount=1
        cache.acquire("src1")  # refcount=2
        await cache.evict("src1")  # 标记待淘汰(refcount=2>0)

        # 多余的 release(模拟 get_source 失败后的多余调用)
        await cache.release("src1")  # refcount=2-1=1

        # source 仍在缓存中,未被淘汰(refcount=1>0)
        assert cache.contains("src1")
        assert src.close_count == 0

        # 正常 release
        await cache.release("src1")  # refcount=1-1=0,触发淘汰
        assert src.close_count == 1


class TestLRUReplace:
    """Bug 1: replace 方法原子替换,返回旧值。"""

    async def test_replace_returns_old_value(self, cache: LRUCache):
        """replace 应返回旧值,不关闭(由调用方负责)。"""
        old = FakeSource("old")
        new = FakeSource("new")
        cache.set("src1", old)
        cache.acquire("src1")  # refcount=1

        returned = cache.replace("src1", new)
        assert returned is old
        assert cache.get("src1") is new
        assert old.close_count == 0  # replace 不关闭旧值

        # refcount 被清除,新 source 从 0 开始
        # 正在使用旧 source 的请求 release 不影响新 source
        await cache.release("src1")  # refcount=0-1=-1 → no-op
        assert cache.get("src1") is new  # 新 source 仍在

    async def test_replace_nonexistent_returns_none(self, cache: LRUCache):
        """replace 不存在的 key 返回 None。"""
        new = FakeSource("new")
        returned = cache.replace("src1", new)
        assert returned is None
        assert cache.get("src1") is new

    async def test_replace_clears_pending_evict(self, cache: LRUCache):
        """replace 应清除 pending_evict 标记。"""
        old = FakeSource("old")
        new = FakeSource("new")
        cache.set("src1", old)
        cache.acquire("src1")
        await cache.evict("src1")  # 标记待淘汰

        cache.replace("src1", new)
        # pending_evict 已清除,新 source 可以正常 get
        assert cache.get("src1") is new


class TestResourceManagerAddSource:
    """Bug 1: add_source 原子替换,不泄漏旧 source。"""

    async def test_add_source_closes_old_source(self):
        """add_source 替换旧 source 时应异步关闭旧 source。"""
        from data_tool_mcp.resources import ResourceManager

        rm = ResourceManager()
        old = FakeSource("old")
        new = FakeSource("new")

        # 用 MagicMock 模拟 Source(有 close 方法)
        old_mock = MagicMock()
        old_mock.close = AsyncMock()
        new_mock = MagicMock()
        new_mock.close = AsyncMock()

        await rm.add_source("src1", old_mock, config={"type": "test"})
        await rm.add_source("src1", new_mock, config={"type": "test"})

        # 旧 source 应被关闭(异步,需等待)
        await asyncio.sleep(0.01)
        assert old_mock.close.called
        assert not new_mock.close.called

        # 新 source 在缓存中
        source = rm._source_cache.get("src1")
        assert source is new_mock

        await rm.close()

    async def test_add_source_does_not_evict_new_on_release(self):
        """add_source 后 release 不应淘汰新 source(修复 evict+set 竞态)。"""
        from data_tool_mcp.resources import ResourceManager

        rm = ResourceManager()
        old_mock = MagicMock()
        old_mock.close = AsyncMock()
        new_mock = MagicMock()
        new_mock.close = AsyncMock()

        # 模拟:旧 source 正在被使用(refcount=1)
        await rm.add_source("src1", old_mock, config={"type": "test"})
        await rm.get_source("src1")  # acquire, refcount=1

        # 替换为新 source
        await rm.add_source("src1", new_mock, config={"type": "test"})

        # 旧 source 的 release 不应影响新 source
        await rm.release_source("src1")  # 旧 refcount(已被 replace 清除) → no-op

        # 新 source 仍在缓存中
        source = rm._source_cache.get("src1")
        assert source is new_mock
        assert not new_mock.close.called

        await rm.close()


class TestResourceManagerRemoveSource:
    """Bug 3: remove_source 后 get_source 不命中已删除 source。"""

    async def test_remove_source_then_get_returns_none(self):
        """remove_source 后 get_source 应返回 None,不返回旧 source。"""
        from data_tool_mcp.resources import ResourceManager

        rm = ResourceManager()
        mock = MagicMock()
        mock.close = AsyncMock()

        await rm.add_source("src1", mock, config={"type": "test"})
        await rm.get_source("src1")  # acquire, refcount=1

        await rm.remove_source("src1")

        # get_source 应返回 None(配置已删除,且 cache 中标记待淘汰)
        source = await rm.get_source("src1")
        assert source is None

        await rm.release_source("src1")  # 清理 refcount
        await rm.close()


class TestExecuteQueryRefcount:
    """Bug 4: execute_query 中 acquire 后 raise 不泄漏 refcount。"""

    async def test_execute_query_releases_on_type_error(self):
        """execute_query 在 source 不支持 execute_sql 时也应 release。"""
        from data_tool_mcp.admin.router import router
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport

        # 使用 spec=[] 限制 MagicMock 不自动生成 execute_sql 属性
        class NonSQLSource:
            """没有 execute_sql 方法的 source。"""
            pass

        app = FastAPI()
        rm = MagicMock()
        rm.has_source.return_value = True
        rm.get_source = AsyncMock(return_value=NonSQLSource())
        rm.release_source = AsyncMock()
        app.state.resource_manager = rm
        app.state.config = MagicMock()
        app.state.config.version = "0.1.0"
        app.state.config.enabled_source_types = []
        app.include_router(router)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/mcp-api/query", json={
                "sourceName": "src1",
                "statement": "SELECT 1",
            })
            assert resp.status_code == 400
            assert "does not support SQL queries" in resp.json()["detail"]

        # release_source 应被调用(不泄漏 refcount)
        rm.release_source.assert_called_once_with("src1")
