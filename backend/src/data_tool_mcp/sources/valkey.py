"""Valkey source — valkey or redis-py async (Redis-compatible).

Maps to Go: internal/sources/valkey/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


def _make_redis_client(module: Any, host: str, port: int, password: str, db: int, ssl: bool) -> Any:
    """使用给定模块构造异步 Redis 兼容客户端。"""
    return module.Redis(
        host=host,
        port=port,
        password=password or None,
        db=db,
        ssl=ssl,
        decode_responses=True,
    )


def _import_redis_asyncio() -> Any:
    """优先导入 valkey.asyncio,失败则回退到 redis.asyncio,两者均不可用时报错。"""
    try:
        import valkey.asyncio as aiovalkey

        return aiovalkey
    except ImportError:
        pass
    try:
        import redis.asyncio as aioredis

        return aioredis
    except ImportError as e:
        raise ImportError(
            "valkey or redis is required: pip install valkey or pip install redis"
        ) from e


class ValkeySource(NoSQLSource):
    """Valkey source using valkey or redis-py async client."""

    def __init__(self, name: str, client: Any):
        """初始化数据源配置。"""
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "valkey"

    async def connect(self) -> None:
        """建立数据库连接。"""
        await self._client.ping()

    async def close(self) -> None:
        """关闭数据库连接。"""
        await self._client.aclose()

    async def execute_command(self, *args: Any) -> Any:
        """执行原生 Redis 命令。"""
        return await self._client.execute_command(*args)

    async def get(self, key: str) -> str | None:
        """获取指定键的值。"""
        return await self._client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """设置键值对。"""
        await self._client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        """删除指定键。"""
        return await self._client.delete(*keys)

    async def keys(self, pattern: str = "*") -> list[str]:
        """按模式匹配列出所有键。"""
        return [k.decode() if isinstance(k, bytes) else k for k in await self._client.keys(pattern)]


@register_source("valkey")
@dataclass
class ValkeySourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    ssl: bool = False

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "valkey"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ValkeySourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            host=data.get("host", "localhost"),
            port=data.get("port", 6379),
            password=data.get("password", ""),
            db=data.get("db", 0),
            ssl=data.get("ssl", False),
        )

    async def initialize(self, tracer=None) -> ValkeySource:
        """创建并初始化数据源实例。"""
        module = _import_redis_asyncio()
        client = _make_redis_client(module, self.host, self.port, self.password, self.db, self.ssl)
        source = ValkeySource(name=self._name, client=client)
        await source.connect()
        return source
