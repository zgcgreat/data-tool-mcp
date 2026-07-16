"""TDSQL tools — 8 diagnostic tools for TDSQL (MySQL compatible).

TDSQL 兼容 MySQL 协议,因此诊断工具复用 MySQL 的 information_schema /
performance_schema 查询语句。仅工具类型名从 mysql-* 改为 tdsql-*。

tdsql-sql 与 tdsql-execute-sql 已在 other_sql_tools.py 中注册。

Maps to Go: internal/tools/mysql/ (TDSQL 复用 MySQL 工具集)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import SQLSource
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
# TDSQL list-type / param-type diagnostic tools
# ---------------------------------------------------------------------------

class TDSQLListTool(BaseTool):
    """Generic TDSQL diagnostic tool that executes a fixed SQL query.

    支持无参 (固定 SQL) 和带参 (如 EXPLAIN :sql) 两种模式,
    与 MySQLListTool 行为一致。
    """

    def __init__(self, cfg: ConfigBase, source_name: str, sql: str, param_defs: list[ParameterManifest] | None = None):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._sql = sql
        self._param_defs = param_defs or []

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await source.execute_sql(self._sql, params if params else None)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


# ---------------------------------------------------------------------------
# Tool definitions — (tool_type, description, sql, param_defs)
# SQL 语句与 mysql_tools.py 保持一致 (information_schema / performance_schema)
# ---------------------------------------------------------------------------

_TDSQL_LIST_TOOLS: list[tuple[str, str, str, list[ParameterManifest]]] = [
    ("tdsql-list-tables",
     "列出 TDSQL 数据库中的所有表",
     "SHOW TABLES",
     []),
    ("tdsql-list-table-stats",
     "List table statistics in the TDSQL database",
     "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()",
     []),
    ("tdsql-list-active-queries",
     "List active queries in the TDSQL database",
     "SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO FROM information_schema.PROCESSLIST WHERE COMMAND != 'Sleep'",
     []),
    ("tdsql-list-all-locks",
     "List all locks in the TDSQL database",
     "SELECT * FROM information_schema.INNODB_LOCKS",
     []),
    ("tdsql-list-table-fragmentation",
     "List table fragmentation in the TDSQL database",
     "SELECT TABLE_NAME, DATA_FREE, DATA_LENGTH, ROUND(DATA_FREE / (DATA_LENGTH + 1), 2) AS fragmentation_ratio FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND DATA_FREE > 0",
     []),
    ("tdsql-list-tables-missing-unique-indexes",
     "List tables missing unique indexes in the TDSQL database",
     "SELECT T.TABLE_NAME FROM information_schema.TABLES T LEFT JOIN information_schema.TABLE_CONSTRAINTS C ON T.TABLE_NAME = C.TABLE_NAME AND C.CONSTRAINT_TYPE = 'UNIQUE' WHERE T.TABLE_SCHEMA = DATABASE() AND C.CONSTRAINT_NAME IS NULL",
     []),
    ("tdsql-show-query-stats",
     "Show query statistics in the TDSQL database",
     "SELECT * FROM performance_schema.events_statements_summary_by_digest ORDER BY COUNT_STAR DESC LIMIT 20",
     []),
]

_TDSQL_PARAM_TOOLS: list[tuple[str, str, str, list[ParameterManifest]]] = [
    ("tdsql-get-query-plan",
     "Get the query execution plan for a SQL statement on TDSQL",
     "EXPLAIN :sql",
     [
         ParameterManifest(name="sql", type="string", description="SQL statement to explain", required=True),
     ]),
]


def _make_tdsql_list_tool_config(tool_type: str, description: str, sql: str, param_defs: list[ParameterManifest]):
    @register_tool(tool_type)
    @dataclass
    class _TDSQLListToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _TDSQLListToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> TDSQLListTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return TDSQLListTool(cfg=cfg, source_name=self.source, sql=sql, param_defs=param_defs)

    _TDSQLListToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _TDSQLListToolConfig.__qualname__ = _TDSQLListToolConfig.__name__
    return _TDSQLListToolConfig


for _tool_type, _desc, _sql, _params in _TDSQL_LIST_TOOLS + _TDSQL_PARAM_TOOLS:
    _make_tdsql_list_tool_config(_tool_type, _desc, _sql, _params)
