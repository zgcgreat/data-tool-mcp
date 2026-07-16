"""PostgreSQL tools — 24 tools for PostgreSQL introspection and administration.

Maps to Go: internal/tools/postgresql/
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
    _build_sql_tool_parameters,
    _execute_sql_with_modes,
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# Generic SQL query tool (read-only)
# ---------------------------------------------------------------------------

class PgSQLTool(BaseTool):
    """Run a read-only SQL query on PostgreSQL.

    Supports three modes (matching Go postgres-sql):
      1. statement + templateParameters → render template, then execute
      2. statement + parameters         → execute with bind params
      3. statement only                 → execute fixed SQL directly
      4. no statement                   → user provides 'sql' param
    """

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        statement: str = "",
        template_parameters: list[dict[str, Any]] | None = None,
        parameters: list[dict[str, Any]] | None = None,
    ):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._statement = statement
        self._template_parameters = template_parameters or []
        self._parameters = parameters or []

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await _execute_sql_with_modes(
                source, self._statement, self._template_parameters, self._parameters, params
            )
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        param_defs = self._template_parameters or self._parameters
        parameters = _build_sql_tool_parameters(param_defs, self._statement, "SQL query to execute")
        return ToolManifest(
            description=self.description,
            parameters=parameters,
            auth_required=self.auth_required,
        )


@register_tool("postgres-sql")
@dataclass
class PgSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 PostgreSQL 上执行只读 SQL 查询"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        return "postgres-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> PgSQLToolConfig:
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 PostgreSQL 上执行只读 SQL 查询"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
            parameters=data.get("parameters", []),
        )

    async def initialize(self) -> PgSQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return PgSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
            parameters=self.parameters,
        )


# ---------------------------------------------------------------------------
# Execute SQL tool (read-write)
# ---------------------------------------------------------------------------

class PgExecuteSQLTool(BaseTool):
    """Execute a SQL statement on PostgreSQL (may modify data).

    Supports the same statement/templateParameters/parameters modes as PgSQLTool.
    """

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        statement: str = "",
        template_parameters: list[dict[str, Any]] | None = None,
        parameters: list[dict[str, Any]] | None = None,
    ):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name
        self._statement = statement
        self._template_parameters = template_parameters or []
        self._parameters = parameters or []

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await _execute_sql_with_modes(
                source, self._statement, self._template_parameters, self._parameters, params
            )
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        param_defs = self._template_parameters or self._parameters
        parameters = _build_sql_tool_parameters(param_defs, self._statement, "SQL statement to execute")
        return ToolManifest(
            description=self.description,
            parameters=parameters,
            auth_required=self.auth_required,
        )


@register_tool("postgres-execute-sql")
@dataclass
class PgExecuteSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 PostgreSQL 上执行 SQL 语句（可能修改数据）"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        return "postgres-execute-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> PgExecuteSQLToolConfig:
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 PostgreSQL 上执行 SQL 语句"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
            parameters=data.get("parameters", []),
        )

    async def initialize(self) -> PgExecuteSQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return PgExecuteSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
            parameters=self.parameters,
        )


# ---------------------------------------------------------------------------
# List-type tools — fixed SQL query tools
# ---------------------------------------------------------------------------

class PgListTool(BaseTool):
    """Generic PostgreSQL list tool that executes a fixed SQL query."""

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
# Tool definitions registry — (tool_type, description, sql, param_defs)
# ---------------------------------------------------------------------------

_PG_LIST_TOOLS: list[tuple[str, str, str, list[ParameterManifest]]] = [
    ("postgres-list-tables",
     "列出 PostgreSQL 数据库中的所有表",
     "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
     []),
    ("postgres-list-views",
     "列出 PostgreSQL 数据库中的所有视图",
     "SELECT viewname FROM pg_views WHERE schemaname = 'public'",
     []),
    ("postgres-list-schemas",
     "列出 PostgreSQL 数据库中的所有模式",
     "SELECT schema_name FROM information_schema.schemata",
     []),
    ("postgres-list-indexes",
     "列出 PostgreSQL 数据库中的所有索引",
     "SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'public'",
     []),
    ("postgres-list-sequences",
     "列出 PostgreSQL 数据库中的所有序列",
     "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'",
     []),
    ("postgres-list-triggers",
     "列出 PostgreSQL 数据库中的所有触发器",
     "SELECT tgname, relname FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid",
     []),
    ("postgres-list-roles",
     "列出 PostgreSQL 数据库中的所有角色",
     "SELECT rolname FROM pg_roles",
     []),
    ("postgres-list-stored-procedure",
     "列出 PostgreSQL 数据库中的所有存储过程",
     "SELECT routine_name FROM information_schema.routines WHERE routine_type = 'FUNCTION'",
     []),
    ("postgres-list-active-queries",
     "列出 PostgreSQL 数据库中的所有活动查询",
     "SELECT pid, query, state, duration FROM pg_stat_activity WHERE state = 'active'",
     []),
    ("postgres-list-locks",
     "列出 PostgreSQL 数据库中的所有锁",
     "SELECT locktype, relation::regclass, mode, pid FROM pg_locks",
     []),
    ("postgres-list-available-extensions",
     "列出 PostgreSQL 数据库中的所有可用扩展",
     "SELECT name FROM pg_available_extensions",
     []),
    ("postgres-list-installed-extensions",
     "列出 PostgreSQL 数据库中的所有已安装扩展",
     "SELECT extname FROM pg_extension",
     []),
    ("postgres-list-pg-settings",
     "列出 PostgreSQL 设置",
     "SELECT name, setting, source FROM pg_settings",
     []),
    ("postgres-list-tablespaces",
     "列出 PostgreSQL 数据库中的所有表空间",
     "SELECT spcname FROM pg_tablespace",
     []),
    ("postgres-list-publication-tables",
     "列出 PostgreSQL 数据库中的所有发布表",
     "SELECT pubname, tablename FROM pg_publication_tables",
     []),
    ("postgres-list-query-stats",
     "列出 pg_stat_statements 中的查询统计信息",
     "SELECT query, calls, total_exec_time, rows FROM pg_stat_statements",
     []),
    ("postgres-list-table-stats",
     "列出 pg_stat_user_tables 中的表统计信息",
     "SELECT relname, n_live_tup, n_dead_tup FROM pg_stat_user_tables",
     []),
    ("postgres-list-database-stats",
     "列出 pg_stat_database 中的数据库统计信息",
     "SELECT datname, numbackends, xact_commit, blks_read FROM pg_stat_database",
     []),
    ("postgres-long-running-transactions",
     "列出 PostgreSQL 数据库中的长时间运行事务",
     "SELECT pid, now() - xact_start AS duration, query FROM pg_stat_activity WHERE xact_start IS NOT NULL ORDER BY duration DESC",
     []),
    ("postgres-replication-stats",
     "列出 pg_stat_replication 中的复制统计信息",
     "SELECT * FROM pg_stat_replication",
     []),
]

# Tools with parameters
_PG_PARAM_TOOLS: list[tuple[str, str, str, list[ParameterManifest]]] = [
    ("postgres-get-column-cardinality",
     "从 pg_stats 获取列基数",
     "SELECT n_distinct FROM pg_stats WHERE tablename = :table_name AND attname = :column_name",
     [
         ParameterManifest(name="table_name", type="string", description="Table name", required=True),
         ParameterManifest(name="column_name", type="string", description="Column name", required=True),
     ]),
]


# ---------------------------------------------------------------------------
# Dynamic registration — create a ToolConfig for each list tool
# ---------------------------------------------------------------------------

def _make_list_tool_config(tool_type: str, desc: str, sql: str, param_defs: list[ParameterManifest]):
    """Factory: create a ToolConfig class for a PostgreSQL list-type tool."""
    _default_desc = desc

    @register_tool(tool_type)
    @dataclass
    class _PgListToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = field(default_factory=lambda: _default_desc)

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _PgListToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", _default_desc))

        async def initialize(self) -> PgListTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return PgListTool(cfg=cfg, source_name=self.source, sql=sql, param_defs=param_defs)

    _PgListToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _PgListToolConfig.__qualname__ = _PgListToolConfig.__name__
    return _PgListToolConfig


# Register all list tools
for _tool_type, _desc, _sql, _params in _PG_LIST_TOOLS + _PG_PARAM_TOOLS:
    _make_list_tool_config(_tool_type, _desc, _sql, _params)


# ---------------------------------------------------------------------------
# postgres-database-overview — complex multi-query tool
# ---------------------------------------------------------------------------

class PgDatabaseOverviewTool(BaseTool):
    """Get a comprehensive overview of the PostgreSQL database."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            tables = await source.execute_sql("SELECT count(*) as table_count FROM pg_tables WHERE schemaname = 'public'")
            views = await source.execute_sql("SELECT count(*) as view_count FROM pg_views WHERE schemaname = 'public'")
            indexes = await source.execute_sql("SELECT count(*) as index_count FROM pg_indexes WHERE schemaname = 'public'")
            schemas = await source.execute_sql("SELECT count(*) as schema_count FROM information_schema.schemata")
            extensions = await source.execute_sql("SELECT count(*) as extension_count FROM pg_extension")
            size = await source.execute_sql("SELECT pg_database_size(current_database()) as db_size")
            return {
                "tables": tables,
                "views": views,
                "indexes": indexes,
                "schemas": schemas,
                "extensions": extensions,
                "database_size": size,
            }
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[],
            auth_required=self.auth_required,
        )


@register_tool("postgres-database-overview")
@dataclass
class PgDatabaseOverviewToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "获取 PostgreSQL 数据库的全面概览"

    @property
    def tool_type(self) -> str:
        return "postgres-database-overview"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> PgDatabaseOverviewToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "获取 PostgreSQL 数据库的全面概览"))

    async def initialize(self) -> PgDatabaseOverviewTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return PgDatabaseOverviewTool(cfg=cfg, source_name=self.source)
