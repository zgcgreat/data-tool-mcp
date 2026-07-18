"""Redis source — redis-py async.

Maps to Go: internal/sources/redis/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


def _import_aioredis() -> Any:
    """延迟导入 redis.asyncio,未安装时抛出带提示的 ImportError。"""
    try:
        import redis.asyncio as aioredis
    except ImportError as e:
        raise ImportError(
            "redis is required for Redis support: pip install 'redis[hiredis]'"
        ) from e
    return aioredis


def _parse_address(address: str) -> tuple[str, int]:
    """解析 'host:port' 格式的地址,默认端口 6379。"""
    parts = address.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 6379
    return host, port


class RedisSource(NoSQLSource):
    """Redis source using redis-py async."""

    def __init__(self, name: str, client: Any):
        """初始化数据源配置。"""
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "redis"

    async def connect(self) -> None:
        """建立数据库连接。"""
        await self._client.ping()

    async def close(self) -> None:
        """关闭数据库连接。"""
        await self._client.aclose()

    async def get(self, key: str) -> str | None:
        """获取指定键的值。"""
        return await self._client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """设置键值对,可选过期时间。"""
        await self._client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        """删除指定键,返回删除数量。"""
        return await self._client.delete(*keys)

    async def keys(self, pattern: str = "*") -> list[str]:
        """按模式匹配返回所有键。"""
        return [k.decode() if isinstance(k, bytes) else k for k in await self._client.keys(pattern)]


@register_source("redis")
@dataclass
class RedisSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    address: str = "localhost:6379"
    password: str = ""
    db: int = 0

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "redis"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> RedisSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            address=data.get("address", "localhost:6379"),
            password=data.get("password", ""),
            db=data.get("db", 0),
        )

    async def initialize(self, tracer=None) -> RedisSource:
        """创建并初始化数据源实例。"""
        aioredis = _import_aioredis()
        host, port = _parse_address(self.address)
        client = aioredis.Redis(
            host=host,
            port=port,
            password=self.password or None,
            db=self.db,
            decode_responses=True,
        )
        source = RedisSource(name=self._name, client=client)
        await source.connect()
        return source
