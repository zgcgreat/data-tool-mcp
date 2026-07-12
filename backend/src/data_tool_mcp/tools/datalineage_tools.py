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
    register_tool,
)


def _get_datalineage_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> DataLineageSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, DataLineageSource):
        raise TypeError(f"source {source_name!r} is not a Data Lineage source")
    return source


class DataLineageSearchTool(BaseTool):
    """Search data lineage events."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_datalineage_source(source_provider, self._source_name, self.name)
        query = params.get("query", "")
        if not query:
            raise ValueError("missing 'query' parameter")
        results = await source.search_lineage(query, params.get("page_size", 100))
        return {"results": results}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="query", type="string", description="Lineage search query", required=True),
                ParameterManifest(name="page_size", type="integer", description="Max results", required=False),
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
        return "datalineage-search-lineage"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataLineageSearchToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "搜索数据血缘事件"))

    async def initialize(self) -> DataLineageSearchTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return DataLineageSearchTool(cfg=cfg, source_name=self.source)
