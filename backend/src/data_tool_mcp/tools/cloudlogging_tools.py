"""Cloud Logging Admin tools — 3 tools for Cloud Logging.

Maps to Go: internal/tools/cloudloggingadmin/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudloggingadmin import CloudLoggingAdminSource
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
# Cloud Logging 操作分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _log_query_logs(source: CloudLoggingAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """查询Cloud Logging的日志。"""
    return {"entries": await source.query_logs(params.get("filter", ""), params.get("limit", 100))}

async def _log_list_log_names(source: CloudLoggingAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Cloud Logging的日志名称。"""
    return {"log_names": await source.list_log_names()}

async def _log_list_resource_types(source: CloudLoggingAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Cloud Logging的资源类型。"""
    return {"resource_types": await source.list_resource_types()}


_LOGGING_DISPATCH: dict[str, Any] = {
    "cloud-logging-admin-query-logs": _log_query_logs,
    "cloud-logging-admin-list-log-names": _log_list_log_names,
    "cloud-logging-admin-list-resource-types": _log_list_resource_types,
}


class CloudLoggingGenericTool(BaseTool):
    """Generic Cloud Logging Admin tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest]):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, CloudLoggingAdminSource)
        try:
            handler = _LOGGING_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Cloud Logging tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


_LOGGING_TOOLS: list[tuple[str, str, list[ParameterManifest]]] = [
    ("cloud-logging-admin-query-logs", "Query Cloud Logging logs",
     [ParameterManifest(name="filter", type="string", description="Log filter expression", required=False),
      ParameterManifest(name="limit", type="integer", description="Max entries to return", required=False)]),
    ("cloud-logging-admin-list-log-names", "List Cloud Logging log names", []),
    ("cloud-logging-admin-list-resource-types", "List Cloud Logging resource types", []),
]


def _make_logging_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest]):
    """构造Cloud Logging工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _LoggingToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _LoggingToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> CloudLoggingGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return CloudLoggingGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs)

    _LoggingToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _LoggingToolConfig.__qualname__ = _LoggingToolConfig.__name__
    return _LoggingToolConfig


for _tool_type, _desc, _params in _LOGGING_TOOLS:
    _make_logging_tool_config(_tool_type, _desc, _params)
