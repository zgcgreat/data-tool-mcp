"""Data Lineage tools — 1 tool for lineage search.

Maps to Go: internal/tools/datalineage/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.datalineage import DataLineageSource
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


class DataLineageSearchTool(BaseTool):
    """Search data lineage events."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, DataLineageSource
        )
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            results = await source.search_lineage(query, params.get("page_size", 100))
            return {"results": results}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="query", type="string", description="Lineage search query", required=True
                ),
                ParameterManifest(
                    name="page_size", type="integer", description="Max results", required=False
                ),
            ],
            auth_required=self.auth_required,
        )


@register_tool("datalineage-search-lineage")
@dataclass
class DataLineageSearchToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "搜索数据血缘事件"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "datalineage-search-lineage"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataLineageSearchToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "搜索数据血缘事件"),
        )

    async def initialize(self) -> DataLineageSearchTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return DataLineageSearchTool(cfg=cfg, source_name=self.source)
