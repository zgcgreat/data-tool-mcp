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
    register_tool,
)


async def _get_logging_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> CloudLoggingAdminSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, CloudLoggingAdminSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Cloud Logging Admin source")
    return source


class CloudLoggingGenericTool(BaseTool):
    """Generic Cloud Logging Admin tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest]):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_logging_source(source_provider, self._source_name, self.name)
        try:
            if self._tool_type == "cloud-logging-admin-query-logs":
                entries = await source.query_logs(params.get("filter", ""), params.get("limit", 100))
                return {"entries": entries}
            elif self._tool_type == "cloud-logging-admin-list-log-names":
                names = await source.list_log_names()
                return {"log_names": names}
            elif self._tool_type == "cloud-logging-admin-list-resource-types":
                types = await source.list_resource_types()
                return {"resource_types": types}
            else:
                raise ValueError(f"unknown Cloud Logging tool type: {self._tool_type}")
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


_LOGGING_TOOLS: list[tuple[str, str, list[ParameterManifest]]] = [
    ("cloud-logging-admin-query-logs", "Query Cloud Logging logs",
     [ParameterManifest(name="filter", type="string", description="Log filter expression", required=False),
      ParameterManifest(name="limit", type="integer", description="Max entries to return", required=False)]),
    ("cloud-logging-admin-list-log-names", "List Cloud Logging log names", []),
    ("cloud-logging-admin-list-resource-types", "List Cloud Logging resource types", []),
]


def _make_logging_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest]):
    @register_tool(tool_type)
    @dataclass
    class _LoggingToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _LoggingToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> CloudLoggingGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return CloudLoggingGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs)

    _LoggingToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _LoggingToolConfig.__qualname__ = _LoggingToolConfig.__name__
    return _LoggingToolConfig


for _tool_type, _desc, _params in _LOGGING_TOOLS:
    _make_logging_tool_config(_tool_type, _desc, _params)
