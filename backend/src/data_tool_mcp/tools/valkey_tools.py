"""Valkey tool — single unified tool for Valkey/Redis-compatible operations.

Maps to Go: internal/tools/valkey/ (registered as single tool "valkey")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.valkey import ValkeySource
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
# Valkey 命令分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _vk_execute_command(source: ValkeySource, params: dict[str, Any]) -> dict[str, Any]:
    """执行 Valkey 命令。"""
    return {"result": await source.execute_command(*params.get("args", []))}

async def _vk_get(source: ValkeySource, params: dict[str, Any]) -> dict[str, Any]:
    """获取 Valkey 键值。"""
    return {"value": await source.get(params["key"])}

async def _vk_set(source: ValkeySource, params: dict[str, Any]) -> dict[str, Any]:
    """设置 Valkey 键值。"""
    await source.set(params["key"], params["value"], params.get("ex"))
    return {"set": True}

async def _vk_delete(source: ValkeySource, params: dict[str, Any]) -> dict[str, Any]:
    """删除 Valkey 键。"""
    keys = params.get("keys", [])
    if isinstance(keys, str):
        keys = [keys]
    return {"deleted": await source.delete(*keys)}

async def _vk_keys(source: ValkeySource, params: dict[str, Any]) -> dict[str, Any]:
    """获取 Valkey 键列表。"""
    return {"keys": await source.keys(params.get("pattern", "*"))}


_VALKEY_DISPATCH: dict[str, Any] = {
    "execute-command": _vk_execute_command,
    "get": _vk_get,
    "set": _vk_set,
    "delete": _vk_delete,
    "keys": _vk_keys,
}


class ValkeyTool(BaseTool):
    """Unified Valkey tool — dispatches based on command parameter.

    In Go, valkey is registered as a single tool type "valkey" that accepts
    a command parameter (execute-command, get, set, delete, keys).
    """

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, ValkeySource)
        try:
            command = params.get("command", "").lower()
            handler = _VALKEY_DISPATCH.get(command)
            if handler is None:
                raise ValueError(f"unsupported valkey command: {command!r}. Supported: execute-command, get, set, delete, keys")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="command", type="string", description="Valkey command (execute-command, get, set, delete, keys)", required=True),
                ParameterManifest(name="args", type="array", description="Command arguments (for execute-command)", required=False),
                ParameterManifest(name="key", type="string", description="Key (for get/set)", required=False),
                ParameterManifest(name="value", type="string", description="Value (for set)", required=False),
                ParameterManifest(name="keys", type="array", description="Keys to delete (for delete)", required=False),
                ParameterManifest(name="pattern", type="string", description="Key pattern (for keys)", required=False),
                ParameterManifest(name="ex", type="integer", description="Expiry in seconds (for set)", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("valkey")
@dataclass
class ValkeyToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "执行 Valkey/Redis 兼容的键值操作"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "valkey"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ValkeyToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "执行 Valkey 操作"))

    async def initialize(self) -> ValkeyTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return ValkeyTool(cfg=cfg, source_name=self.source)
