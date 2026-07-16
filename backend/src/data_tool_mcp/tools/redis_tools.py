"""Redis tool — single unified tool for Redis key-value operations.

Maps to Go: internal/tools/redis/ (registered as single tool "redis")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.redis import RedisSource
from data_tool_mcp.tools.base import (
    BaseTool,
    ConfigBase,
    ParameterManifest,
    SourceProvider,
    ToolAnnotations,
    ToolConfig,
    ToolManifest,
    register_tool,
)


async def _get_redis_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> RedisSource:
    """Resolve a RedisSource from the SourceProvider."""
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, RedisSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Redis source")
    return source


class RedisTool(BaseTool):
    """Unified Redis tool — dispatches based on command parameter.

    In Go, redis is registered as a single tool type "redis" that accepts
    a command parameter (get, set, delete, etc.).
    """

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = await _get_redis_source(source_provider, self._source_name, self.name)
        try:
            command = params.get("command", "").lower()

            if command == "get":
                key = params.get("key", "")
                value = await source.get(key)
                return {"key": key, "value": value}
            elif command == "set":
                key = params.get("key", "")
                value = params.get("value", "")
                ex = params.get("ex")
                await source.set(key, value, ex=ex)
                return {"key": key, "status": "OK"}
            elif command == "delete":
                keys = params.get("keys", [])
                if isinstance(keys, str):
                    keys = [keys]
                deleted = await source.delete(*keys)
                return {"deleted": deleted}
            else:
                raise ValueError(f"unsupported redis command: {command!r}. Supported: get, set, delete")
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="command", type="string", description="Redis command to execute (get, set, delete)", required=True),
                ParameterManifest(name="key", type="string", description="Redis key (for get/set)", required=False),
                ParameterManifest(name="value", type="string", description="Value to set (for set)", required=False),
                ParameterManifest(name="keys", type="array", description="Keys to delete (for delete)", required=False),
                ParameterManifest(name="ex", type="integer", description="Expiry in seconds (for set)", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("redis")
@dataclass
class RedisToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "执行 Redis 键值操作（get、set、delete）"

    @property
    def tool_type(self) -> str:
        return "redis"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> RedisToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "执行 Redis 键值操作"))

    async def initialize(self) -> RedisTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return RedisTool(cfg=cfg, source_name=self.source)
