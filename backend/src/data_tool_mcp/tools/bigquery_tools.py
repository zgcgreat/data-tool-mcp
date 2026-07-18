"""BigQuery tools — 10 tools for BigQuery data analytics.

Maps to Go: internal/tools/bigquery/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.bigquery import BigQuerySource
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
# BigQuery 操作分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------


async def _bq_execute_sql(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """执行BigQuery的SQL 查询。"""
    sql = params.get("sql", "")
    if not sql:
        raise ValueError("missing 'sql' parameter")
    rows = await source.execute_sql(sql)
    return {"rows": rows, "rowCount": len(rows)}


async def _bq_list_dataset_ids(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """列出BigQuery的数据集 ID。"""
    return {"dataset_ids": await source.list_dataset_ids()}


async def _bq_list_table_ids(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """列出BigQuery的表 ID。"""
    return {"table_ids": await source.list_table_ids(params.get("dataset_id", ""))}


async def _bq_get_dataset_info(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """获取BigQuery的数据集信息。"""
    return {"dataset_info": await source.get_dataset_info(params.get("dataset_id", ""))}


async def _bq_get_table_info(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """获取BigQuery的表信息。"""
    return {
        "table_info": await source.get_table_info(
            params.get("dataset_id", ""), params.get("table_id", "")
        )
    }


async def _bq_forecast(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """执行 BigQuery 预测分析。"""
    rows = await source.execute_sql(params.get("sql", ""))
    return {"rows": rows, "rowCount": len(rows)}


async def _bq_conversational(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """执行 BigQuery 对话式查询。"""
    rows = await source.execute_sql(params.get("question", ""))
    return {"rows": rows, "rowCount": len(rows)}


async def _bq_search_catalog(source: BigQuerySource, params: dict[str, Any]) -> dict[str, Any]:
    """搜索BigQuery的数据目录。"""
    rows = await source.search_catalog(params.get("query", ""))
    return {"rows": rows, "rowCount": len(rows)}


_BQ_DISPATCH: dict[str, Any] = {
    "bigquery-sql": _bq_execute_sql,
    "bigquery-execute-sql": _bq_execute_sql,
    "bigquery-list-dataset-ids": _bq_list_dataset_ids,
    "bigquery-list-table-ids": _bq_list_table_ids,
    "bigquery-get-dataset-info": _bq_get_dataset_info,
    "bigquery-get-table-info": _bq_get_table_info,
    "bigquery-forecast": _bq_forecast,
    "bigquery-analyze-contribution": _bq_forecast,
    "bigquery-conversational-analytics": _bq_conversational,
    "bigquery-search-catalog": _bq_search_catalog,
}


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_BQ_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "bigquery-sql",
        "Run a read-only SQL query on BigQuery",
        [
            ParameterManifest(
                name="sql", type="string", description="SQL query to execute", required=True
            )
        ],
        True,
    ),
    (
        "bigquery-execute-sql",
        "Execute a SQL statement on BigQuery (may modify data)",
        [
            ParameterManifest(
                name="sql", type="string", description="SQL statement to execute", required=True
            )
        ],
        False,
    ),
    ("bigquery-list-dataset-ids", "List all dataset IDs in the BigQuery project", [], True),
    (
        "bigquery-list-table-ids",
        "List all table IDs in a BigQuery dataset",
        [
            ParameterManifest(
                name="dataset_id", type="string", description="Dataset ID", required=True
            )
        ],
        True,
    ),
    (
        "bigquery-get-dataset-info",
        "Get information about a BigQuery dataset",
        [
            ParameterManifest(
                name="dataset_id", type="string", description="Dataset ID", required=True
            )
        ],
        True,
    ),
    (
        "bigquery-get-table-info",
        "Get information about a BigQuery table",
        [
            ParameterManifest(
                name="dataset_id", type="string", description="Dataset ID", required=True
            ),
            ParameterManifest(
                name="table_id", type="string", description="Table ID", required=True
            ),
        ],
        True,
    ),
    (
        "bigquery-forecast",
        "Run a forecast query on BigQuery",
        [
            ParameterManifest(
                name="sql", type="string", description="Forecast SQL query", required=True
            )
        ],
        True,
    ),
    (
        "bigquery-analyze-contribution",
        "Run a contribution analysis query on BigQuery",
        [
            ParameterManifest(
                name="sql",
                type="string",
                description="Contribution analysis SQL query",
                required=True,
            )
        ],
        True,
    ),
    (
        "bigquery-conversational-analytics",
        "Run a conversational analytics query on BigQuery",
        [
            ParameterManifest(
                name="question",
                type="string",
                description="Natural language question",
                required=True,
            )
        ],
        True,
    ),
    (
        "bigquery-search-catalog",
        "Search the BigQuery catalog",
        [ParameterManifest(name="query", type="string", description="Search query", required=True)],
        True,
    ),
]


class BigQueryGenericTool(BaseTool):
    """Generic BigQuery tool that dispatches based on tool type."""

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
            source_provider, self._source_name, self.name, BigQuerySource
        )
        try:
            handler = _BQ_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown BigQuery tool type: {self._tool_type}")
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


def _make_bq_tool_config(
    tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool
):
    """构造BigQuery工具配置。"""

    @register_tool(tool_type)
    @dataclass
    class _BQToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _BQToolConfig:
            """从字典创建配置实例。"""
            return cls(
                _name=name,
                source=data.get("source", ""),
                description=data.get("description", description),
            )

        async def initialize(self) -> BigQueryGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return BigQueryGenericTool(
                cfg=cfg,
                source_name=self.source,
                tool_type=tool_type,
                param_defs=param_defs,
                read_only=read_only,
            )

    _BQToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _BQToolConfig.__qualname__ = _BQToolConfig.__name__
    return _BQToolConfig


for _tool_type, _desc, _params, _ro in _BQ_TOOLS:
    _make_bq_tool_config(_tool_type, _desc, _params, _ro)
