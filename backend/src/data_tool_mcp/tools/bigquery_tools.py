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
    register_tool,
)


def _get_bq_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> BigQuerySource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, BigQuerySource):
        raise TypeError(f"source {source_name!r} is not a BigQuery source")
    return source


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_BQ_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("bigquery-sql", "Run a read-only SQL query on BigQuery",
     [ParameterManifest(name="sql", type="string", description="SQL query to execute", required=True)],
     True),
    ("bigquery-execute-sql", "Execute a SQL statement on BigQuery (may modify data)",
     [ParameterManifest(name="sql", type="string", description="SQL statement to execute", required=True)],
     False),
    ("bigquery-list-dataset-ids", "List all dataset IDs in the BigQuery project", [], True),
    ("bigquery-list-table-ids", "List all table IDs in a BigQuery dataset",
     [ParameterManifest(name="dataset_id", type="string", description="Dataset ID", required=True)],
     True),
    ("bigquery-get-dataset-info", "Get information about a BigQuery dataset",
     [ParameterManifest(name="dataset_id", type="string", description="Dataset ID", required=True)],
     True),
    ("bigquery-get-table-info", "Get information about a BigQuery table",
     [ParameterManifest(name="dataset_id", type="string", description="Dataset ID", required=True),
      ParameterManifest(name="table_id", type="string", description="Table ID", required=True)],
     True),
    ("bigquery-forecast", "Run a forecast query on BigQuery",
     [ParameterManifest(name="sql", type="string", description="Forecast SQL query", required=True)],
     True),
    ("bigquery-analyze-contribution", "Run a contribution analysis query on BigQuery",
     [ParameterManifest(name="sql", type="string", description="Contribution analysis SQL query", required=True)],
     True),
    ("bigquery-conversational-analytics", "Run a conversational analytics query on BigQuery",
     [ParameterManifest(name="question", type="string", description="Natural language question", required=True)],
     True),
    ("bigquery-search-catalog", "Search the BigQuery catalog",
     [ParameterManifest(name="query", type="string", description="Search query", required=True)],
     True),
]


class BigQueryGenericTool(BaseTool):
    """Generic BigQuery tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_bq_source(source_provider, self._source_name, self.name)
        if self._tool_type in ("bigquery-sql", "bigquery-execute-sql"):
            sql = params.get("sql", "")
            if not sql:
                raise ValueError("missing 'sql' parameter")
            rows = await source.execute_sql(sql)
            return {"rows": rows, "rowCount": len(rows)}
        elif self._tool_type == "bigquery-list-dataset-ids":
            ids = await source.list_dataset_ids()
            return {"dataset_ids": ids}
        elif self._tool_type == "bigquery-list-table-ids":
            dataset_id = params.get("dataset_id", "")
            ids = await source.list_table_ids(dataset_id)
            return {"table_ids": ids}
        elif self._tool_type == "bigquery-get-dataset-info":
            dataset_id = params.get("dataset_id", "")
            info = await source.get_dataset_info(dataset_id)
            return {"dataset_info": info}
        elif self._tool_type == "bigquery-get-table-info":
            dataset_id = params.get("dataset_id", "")
            table_id = params.get("table_id", "")
            info = await source.get_table_info(dataset_id, table_id)
            return {"table_info": info}
        elif self._tool_type in ("bigquery-forecast", "bigquery-analyze-contribution"):
            sql = params.get("sql", "")
            rows = await source.execute_sql(sql)
            return {"rows": rows, "rowCount": len(rows)}
        elif self._tool_type == "bigquery-conversational-analytics":
            question = params.get("question", "")
            rows = await source.execute_sql(question)
            return {"rows": rows, "rowCount": len(rows)}
        elif self._tool_type == "bigquery-search-catalog":
            query = params.get("query", "")
            rows = await source.search_catalog(query)
            return {"rows": rows, "rowCount": len(rows)}
        else:
            raise ValueError(f"unknown BigQuery tool type: {self._tool_type}")

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


def _make_bq_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    @register_tool(tool_type)
    @dataclass
    class _BQToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _BQToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> BigQueryGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return BigQueryGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _BQToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _BQToolConfig.__qualname__ = _BQToolConfig.__name__
    return _BQToolConfig


for _tool_type, _desc, _params, _ro in _BQ_TOOLS:
    _make_bq_tool_config(_tool_type, _desc, _params, _ro)
