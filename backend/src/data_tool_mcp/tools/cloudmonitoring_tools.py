"""Cloud Monitoring tools — 1 tool for Prometheus queries.

Maps to Go: internal/tools/cloudmonitoring/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudmonitoring import CloudMonitoringSource
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


async def _get_monitoring_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> CloudMonitoringSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, CloudMonitoringSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Cloud Monitoring source")
    return source


class CloudMonitoringQueryTool(BaseTool):
    """Query Cloud Monitoring using PromQL."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_monitoring_source(source_provider, self._source_name, self.name)
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            results = await source.query_prometheus(query)
            return {"results": results}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[ParameterManifest(name="query", type="string", description="PromQL query", required=True)],
            auth_required=self.auth_required,
        )


@register_tool("cloud-monitoring-query-prometheus")
@dataclass
class CloudMonitoringQueryToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "使用 PromQL 查询 Cloud Monitoring"

    @property
    def tool_type(self) -> str:
        return "cloud-monitoring-query-prometheus"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudMonitoringQueryToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "使用 PromQL 查询 Cloud Monitoring"))

    async def initialize(self) -> CloudMonitoringQueryTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return CloudMonitoringQueryTool(cfg=cfg, source_name=self.source)
