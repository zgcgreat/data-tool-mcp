"""Valkey source — valkey or redis-py async (Redis-compatible).

Maps to Go: internal/sources/valkey/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class ValkeySource(NoSQLSource):
    """Valkey source using valkey or redis-py async client."""

    def __init__(self, name: str, client: Any):
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        return "valkey"

    async def connect(self) -> None:
        await self._client.ping()

    async def close(self) -> None:
        await self._client.aclose()

    async def execute_command(self, *args: Any) -> Any:
        return await self._client.execute_command(*args)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        await self._client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        return await self._client.delete(*keys)

    async def keys(self, pattern: str = "*") -> list[str]:
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
        return "valkey"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ValkeySourceConfig:
        return cls(
            _name=name,
            host=data.get("host", "localhost"),
            port=data.get("port", 6379),
            password=data.get("password", ""),
            db=data.get("db", 0),
            ssl=data.get("ssl", False),
        )

    async def initialize(self, tracer=None) -> ValkeySource:
        try:
            import valkey.asyncio as aiovalkey
            client = aiovalkey.Redis(
                host=self.host, port=self.port, password=self.password or None,
                db=self.db, ssl=self.ssl, decode_responses=True,
            )
        except ImportError:
            try:
                import redis.asyncio as aioredis
                client = aioredis.Redis(
                    host=self.host, port=self.port, password=self.password or None,
                    db=self.db, ssl=self.ssl, decode_responses=True,
                )
            except ImportError as e:
                raise ImportError("valkey or redis is required: pip install valkey or pip install redis") from e

        source = ValkeySource(name=self._name, client=client)
        await source.connect()
        return source
