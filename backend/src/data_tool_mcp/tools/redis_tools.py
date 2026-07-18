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
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# Redis 命令分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------


async def _rd_get(source: RedisSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取 Redis 键值。"""
    key = params.get("key", "")
    return {"key": key, "value": await source.get(key)}


async def _rd_set(source: RedisSource, params: dict[str, Any]) -> dict[str, Any]:
    """设置 Redis 键值。"""
    key = params.get("key", "")
    await source.set(key, params.get("value", ""), ex=params.get("ex"))
    return {"key": key, "status": "OK"}


async def _rd_delete(source: RedisSource, params: dict[str, Any]) -> dict[str, Any]:
    """删除 Redis 键。"""
    keys = params.get("keys", [])
    if isinstance(keys, str):
        keys = [keys]
    return {"deleted": await source.delete(*keys)}


_REDIS_DISPATCH: dict[str, Any] = {
    "get": _rd_get,
    "set": _rd_set,
    "delete": _rd_delete,
}


class RedisTool(BaseTool):
    """Unified Redis tool — dispatches based on command parameter.

    In Go, redis is registered as a single tool type "redis" that accepts
    a command parameter (get, set, delete, etc.).
    """

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(
            cfg, annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True)
        )
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, RedisSource
        )
        try:
            command = params.get("command", "").lower()
            handler = _REDIS_DISPATCH.get(command)
            if handler is None:
                raise ValueError(
                    f"unsupported redis command: {command!r}. Supported: get, set, delete"
                )
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="command",
                    type="string",
                    description="Redis command to execute (get, set, delete)",
                    required=True,
                ),
                ParameterManifest(
                    name="key", type="string", description="Redis key (for get/set)", required=False
                ),
                ParameterManifest(
                    name="value",
                    type="string",
                    description="Value to set (for set)",
                    required=False,
                ),
                ParameterManifest(
                    name="keys",
                    type="array",
                    description="Keys to delete (for delete)",
                    required=False,
                ),
                ParameterManifest(
                    name="ex",
                    type="integer",
                    description="Expiry in seconds (for set)",
                    required=False,
                ),
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
        """返回工具类型标识符。"""
        return "redis"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> RedisToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "执行 Redis 键值操作"),
        )

    async def initialize(self) -> RedisTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return RedisTool(cfg=cfg, source_name=self.source)
