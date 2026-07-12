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
    register_tool,
)


def _get_valkey_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> ValkeySource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, ValkeySource):
        raise TypeError(f"source {source_name!r} is not a Valkey source")
    return source


class ValkeyTool(BaseTool):
    """Unified Valkey tool — dispatches based on command parameter.

    In Go, valkey is registered as a single tool type "valkey" that accepts
    a command parameter (execute-command, get, set, delete, keys).
    """

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_valkey_source(source_provider, self._source_name, self.name)
        command = params.get("command", "").lower()

        if command == "execute-command":
            args = params.get("args", [])
            result = await source.execute_command(*args)
            return {"result": result}
        elif command == "get":
            value = await source.get(params["key"])
            return {"value": value}
        elif command == "set":
            await source.set(params["key"], params["value"], params.get("ex"))
            return {"set": True}
        elif command == "delete":
            keys = params.get("keys", [])
            if isinstance(keys, str):
                keys = [keys]
            count = await source.delete(*keys)
            return {"deleted": count}
        elif command == "keys":
            pattern = params.get("pattern", "*")
            keys = await source.keys(pattern)
            return {"keys": keys}
        else:
            raise ValueError(f"unsupported valkey command: {command!r}. Supported: execute-command, get, set, delete, keys")

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
        return "valkey"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ValkeyToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "执行 Valkey 操作"))

    async def initialize(self) -> ValkeyTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return ValkeyTool(cfg=cfg, source_name=self.source)
