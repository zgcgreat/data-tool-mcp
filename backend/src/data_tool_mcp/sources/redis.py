"""Redis source — redis-py async.

Maps to Go: internal/sources/redis/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class RedisSource(NoSQLSource):
    """Redis source using redis-py async."""

    def __init__(self, name: str, client: aioredis.Redis):
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        return "redis"

    async def connect(self) -> None:
        await self._client.ping()

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        await self._client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        return await self._client.delete(*keys)

    async def keys(self, pattern: str = "*") -> list[str]:
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
        return "redis"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> RedisSourceConfig:
        return cls(
            _name=name,
            address=data.get("address", "localhost:6379"),
            password=data.get("password", ""),
            db=data.get("db", 0),
        )

    async def initialize(self, tracer=None) -> RedisSource:
        try:
            import redis.asyncio as aioredis
        except ImportError as e:
            raise ImportError(
                "redis is required for Redis support: pip install 'redis[hiredis]'"
            ) from e

        client = aioredis.Redis(
            host=self.address.split(":")[0],
            port=int(self.address.split(":")[1]) if ":" in self.address else 6379,
            password=self.password or None,
            db=self.db,
            decode_responses=True,
        )
        source = RedisSource(name=self._name, client=client)
        await source.connect()
        return source
