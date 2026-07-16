"""Spanner tools — 5 tools for Cloud Spanner.

Maps to Go: internal/tools/spanner/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.spanner import SpannerSource
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


async def _get_spanner_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> SpannerSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, SpannerSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Spanner source")
    return source


class SpannerGenericTool(BaseTool):
    """Generic Spanner tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_spanner_source(source_provider, self._source_name, self.name)
        try:
            tt = self._tool_type

            if tt in ("spanner-sql", "spanner-execute-sql"):
                sql = params.get("sql", "")
                if not sql:
                    raise ValueError("missing 'sql' parameter")
                rows = await source.execute_sql(sql)
                return {"rows": rows, "rowCount": len(rows)}
            elif tt == "spanner-list-tables":
                tables = await source.list_tables()
                return {"tables": tables}
            elif tt == "spanner-list-graphs":
                graphs = await source.list_graphs()
                return {"graphs": graphs}
            elif tt == "spanner-search-catalog":
                query = params.get("query", "")
                rows = await source.search_catalog(query)
                return {"rows": rows, "rowCount": len(rows)}
            else:
                raise ValueError(f"unknown Spanner tool type: {tt}")
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


_SPANNER_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("spanner-sql", "Run a read-only SQL query on Spanner",
     [ParameterManifest(name="sql", type="string", description="SQL query to execute", required=True)], True),
    ("spanner-execute-sql", "Execute a SQL statement on Spanner",
     [ParameterManifest(name="sql", type="string", description="SQL statement to execute", required=True)], False),
    ("spanner-list-tables", "List all tables in Spanner", [], True),
    ("spanner-list-graphs", "List all property graphs in Spanner", [], True),
    ("spanner-search-catalog", "Search the Spanner catalog",
     [ParameterManifest(name="query", type="string", description="Search query", required=True)], True),
]


def _make_spanner_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    @register_tool(tool_type)
    @dataclass
    class _SpannerToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _SpannerToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> SpannerGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return SpannerGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _SpannerToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _SpannerToolConfig.__qualname__ = _SpannerToolConfig.__name__
    return _SpannerToolConfig


for _tool_type, _desc, _params, _ro in _SPANNER_TOOLS:
    _make_spanner_tool_config(_tool_type, _desc, _params, _ro)
