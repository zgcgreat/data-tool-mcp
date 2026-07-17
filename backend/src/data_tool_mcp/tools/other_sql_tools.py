"""Other SQL tools — 27 tools for ClickHouse, Snowflake, Oracle, OceanBase, Trino,
CockroachDB, TiDB, YugabyteDB, Firebird, SingleStore, MindsDB.

Maps to Go: internal/tools/clickhouse/, internal/tools/snowflake/, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

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
# Reusable tool classes
# ---------------------------------------------------------------------------

class GenericSQLTool(BaseTool):
    """Run a read-only SQL query."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            sql = params.get("sql", "")
            if not sql:
                raise ValueError("missing 'sql' parameter")
            rows = await source.execute_sql(sql)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[ParameterManifest(name="sql", type="string", description="SQL query to execute", required=True)],
            auth_required=self.auth_required,
        )


class GenericExecuteSQLTool(BaseTool):
    """Execute a SQL statement (may modify data)."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            sql = params.get("sql", "")
            if not sql:
                raise ValueError("missing 'sql' parameter")
            rows = await source.execute_sql(sql)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[ParameterManifest(name="sql", type="string", description="SQL statement to execute", required=True)],
            auth_required=self.auth_required,
        )


class GenericListTablesTool(BaseTool):
    """List all tables via a fixed SQL query."""

    def __init__(self, cfg: ConfigBase, source_name: str, sql: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._sql = sql

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await source.execute_sql(self._sql)
            return {"tables": [list(r.values())[0] for r in rows]}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=[], auth_required=self.auth_required)


class GenericListQueryTool(BaseTool):
    """Execute a fixed SQL listing query."""

    def __init__(self, cfg: ConfigBase, source_name: str, sql: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._sql = sql

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await source.execute_sql(self._sql)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=[], auth_required=self.auth_required)


# ---------------------------------------------------------------------------
# Tool definitions — (tool_type, description, tool_class_key, extra_args)
# ---------------------------------------------------------------------------

# Format: (tool_type, description, kind, extra)
# kind: "sql" | "exec" | "list-tables" | "list-query"
_TOOL_DEFS: list[tuple[str, str, str, dict[str, Any]]] = [
    # ClickHouse (4)
    ("clickhouse-sql", "Run a read-only SQL query on ClickHouse", "sql", {}),
    ("clickhouse-execute-sql", "Execute a SQL statement on ClickHouse", "exec", {}),
    ("clickhouse-list-tables", "List all tables in the ClickHouse database", "list-tables",
     {"sql": "SELECT name FROM system.tables WHERE database = currentDatabase()"}),
    ("clickhouse-list-databases", "List all databases in ClickHouse", "list-query",
     {"sql": "SELECT name FROM system.databases"}),
    # Snowflake (2)
    ("snowflake-sql", "Run a read-only SQL query on Snowflake", "sql", {}),
    ("snowflake-execute-sql", "Execute a SQL statement on Snowflake", "exec", {}),
    # Oracle (2)
    ("oracle-sql", "Run a read-only SQL query on Oracle", "sql", {}),
    ("oracle-execute-sql", "Execute a SQL statement on Oracle", "exec", {}),
    # OceanBase (2)
    ("oceanbase-sql", "Run a read-only SQL query on OceanBase", "sql", {}),
    ("oceanbase-execute-sql", "Execute a SQL statement on OceanBase", "exec", {}),
    # TDSQL (2) — 腾讯云分布式数据库,兼容 MySQL 协议
    ("tdsql-sql", "Run a read-only SQL query on TDSQL", "sql", {}),
    ("tdsql-execute-sql", "Execute a SQL statement on TDSQL", "exec", {}),
    # GaussDB (2) — 华为云分布式数据库,兼容 PostgreSQL 协议
    ("gaussdb-sql", "Run a read-only SQL query on GaussDB", "sql", {}),
    ("gaussdb-execute-sql", "Execute a SQL statement on GaussDB", "exec", {}),
    # Trino (2)
    ("trino-sql", "Run a read-only SQL query on Trino", "sql", {}),
    ("trino-execute-sql", "Execute a SQL statement on Trino", "exec", {}),
    # CockroachDB (4)
    ("cockroachdb-sql", "Run a read-only SQL query on CockroachDB", "sql", {}),
    ("cockroachdb-execute-sql", "Execute a SQL statement on CockroachDB", "exec", {}),
    ("cockroachdb-list-tables", "List all tables in the CockroachDB database", "list-tables",
     {"sql": "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"}),
    ("cockroachdb-list-schemas", "List all schemas in the CockroachDB database", "list-query",
     {"sql": "SELECT schema_name FROM information_schema.schemata"}),
    # TiDB (2)
    ("tidb-sql", "Run a read-only SQL query on TiDB", "sql", {}),
    ("tidb-execute-sql", "Execute a SQL statement on TiDB", "exec", {}),
    # YugabyteDB (1)
    ("yugabytedb-sql", "Run a read-only SQL query on YugabyteDB", "sql", {}),
    # Firebird (2)
    ("firebird-sql", "Run a read-only SQL query on Firebird", "sql", {}),
    ("firebird-execute-sql", "Execute a SQL statement on Firebird", "exec", {}),
    # SingleStore (2)
    ("singlestore-sql", "Run a read-only SQL query on SingleStore", "sql", {}),
    ("singlestore-execute-sql", "Execute a SQL statement on SingleStore", "exec", {}),
    # MindsDB (2)
    ("mindsdb-sql", "Run a read-only SQL query on MindsDB", "sql", {}),
    ("mindsdb-execute-sql", "Execute a SQL statement on MindsDB", "exec", {}),
]


def _make_other_sql_tool_config(tool_type: str, description: str, kind: str, extra: dict[str, Any]):
    """Factory: create a ToolConfig class for an other-SQL tool."""
    _default_desc = description

    def _build_tool(cfg: ConfigBase, source: str) -> BaseTool:
        """构造工具实例。"""
        sql = extra.get("sql", "")
        builders: dict[str, Callable[[ConfigBase, str], BaseTool]] = {
            "sql": lambda c, s: GenericSQLTool(cfg=c, source_name=s),
            "exec": lambda c, s: GenericExecuteSQLTool(cfg=c, source_name=s),
            "list-tables": lambda c, s: GenericListTablesTool(cfg=c, source_name=s, sql=sql),
            "list-query": lambda c, s: GenericListQueryTool(cfg=c, source_name=s, sql=sql),
        }
        builder = builders.get(kind)
        if builder is None:
            raise ValueError(f"unknown kind: {kind}")
        return builder(cfg, source)

    @register_tool(tool_type)
    @dataclass
    class _OtherSQLToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _OtherSQLToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", _default_desc))

        async def initialize(self):
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return _build_tool(cfg, self.source)

    _OtherSQLToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _OtherSQLToolConfig.__qualname__ = _OtherSQLToolConfig.__name__
    return _OtherSQLToolConfig


for _tool_type, _desc, _kind, _extra in _TOOL_DEFS:
    _make_other_sql_tool_config(_tool_type, _desc, _kind, _extra)
