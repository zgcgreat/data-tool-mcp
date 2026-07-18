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
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# Spanner 操作分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------


async def _spn_execute_sql(source: SpannerSource, params: dict[str, Any]) -> dict[str, Any]:
    """执行Spanner的SQL 查询。"""
    sql = params.get("sql", "")
    if not sql:
        raise ValueError("missing 'sql' parameter")
    rows = await source.execute_sql(sql)
    return {"rows": rows, "rowCount": len(rows)}


async def _spn_list_tables(source: SpannerSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Spanner的表列表。"""
    return {"tables": await source.list_tables()}


async def _spn_list_graphs(source: SpannerSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Spanner的图列表。"""
    return {"graphs": await source.list_graphs()}


async def _spn_search_catalog(source: SpannerSource, params: dict[str, Any]) -> dict[str, Any]:
    """搜索Spanner的数据目录。"""
    rows = await source.search_catalog(params.get("query", ""))
    return {"rows": rows, "rowCount": len(rows)}


_SPANNER_DISPATCH: dict[str, Any] = {
    "spanner-sql": _spn_execute_sql,
    "spanner-execute-sql": _spn_execute_sql,
    "spanner-list-tables": _spn_list_tables,
    "spanner-list-graphs": _spn_list_graphs,
    "spanner-search-catalog": _spn_search_catalog,
}


class SpannerGenericTool(BaseTool):
    """Generic Spanner tool that dispatches based on tool type."""

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        tool_type: str,
        param_defs: list[ParameterManifest],
        read_only: bool,
    ):
        """初始化工具配置。"""
        ann = (
            ToolAnnotations(read_only_hint=True)
            if read_only
            else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        )
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, SpannerSource
        )
        try:
            handler = _SPANNER_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Spanner tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


_SPANNER_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "spanner-sql",
        "Run a read-only SQL query on Spanner",
        [
            ParameterManifest(
                name="sql", type="string", description="SQL query to execute", required=True
            )
        ],
        True,
    ),
    (
        "spanner-execute-sql",
        "Execute a SQL statement on Spanner",
        [
            ParameterManifest(
                name="sql", type="string", description="SQL statement to execute", required=True
            )
        ],
        False,
    ),
    ("spanner-list-tables", "List all tables in Spanner", [], True),
    ("spanner-list-graphs", "List all property graphs in Spanner", [], True),
    (
        "spanner-search-catalog",
        "Search the Spanner catalog",
        [ParameterManifest(name="query", type="string", description="Search query", required=True)],
        True,
    ),
]


def _make_spanner_tool_config(
    tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool
):
    """构造Spanner工具配置。"""

    @register_tool(tool_type)
    @dataclass
    class _SpannerToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _SpannerToolConfig:
            """从字典创建配置实例。"""
            return cls(
                _name=name,
                source=data.get("source", ""),
                description=data.get("description", description),
            )

        async def initialize(self) -> SpannerGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return SpannerGenericTool(
                cfg=cfg,
                source_name=self.source,
                tool_type=tool_type,
                param_defs=param_defs,
                read_only=read_only,
            )

    _SpannerToolConfig.__name__ = (
        f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    )
    _SpannerToolConfig.__qualname__ = _SpannerToolConfig.__name__
    return _SpannerToolConfig


for _tool_type, _desc, _params, _ro in _SPANNER_TOOLS:
    _make_spanner_tool_config(_tool_type, _desc, _params, _ro)
