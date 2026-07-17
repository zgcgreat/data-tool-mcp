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
    _get_typed_source_async,
    register_tool,
)


class CloudMonitoringQueryTool(BaseTool):
    """Query Cloud Monitoring using PromQL."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, CloudMonitoringSource)
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            results = await source.query_prometheus(query)
            return {"results": results}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
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
        """返回工具类型标识符。"""
        return "cloud-monitoring-query-prometheus"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudMonitoringQueryToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "使用 PromQL 查询 Cloud Monitoring"))

    async def initialize(self) -> CloudMonitoringQueryTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return CloudMonitoringQueryTool(cfg=cfg, source_name=self.source)
