"""MySQL tools — 10 tools for MySQL introspection and administration.

Maps to Go: internal/tools/mysql/
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
# mysql-sql — read-only SQL query
# ---------------------------------------------------------------------------

class MySQLSQLTool(BaseTool):
    """Run a read-only SQL query on MySQL.

    Supports statement/templateParameters/parameters modes (same as PgSQLTool).
    """

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        statement: str = "",
        template_parameters: list[dict[str, Any]] | None = None,
        parameters: list[dict[str, Any]] | None = None,
    ):
        """初始化工具配置。"""
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
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await _execute_sql_with_modes(
                source, self._statement, self._template_parameters, self._parameters, params
            )
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        param_defs = self._template_parameters or self._parameters
        parameters = _build_sql_tool_parameters(param_defs, self._statement, "SQL query to execute")
        return ToolManifest(
            description=self.description,
            parameters=parameters,
            auth_required=self.auth_required,
        )


@register_tool("mysql-sql")
@dataclass
class MySQLSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 MySQL 上执行只读 SQL 查询"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "mysql-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MySQLSQLToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 MySQL 上执行只读 SQL 查询"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
            parameters=data.get("parameters", []),
        )

    async def initialize(self) -> MySQLSQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return MySQLSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
            parameters=self.parameters,
        )


# ---------------------------------------------------------------------------
# mysql-execute-sql — read-write SQL execution
# ---------------------------------------------------------------------------

class MySQLExecuteSQLTool(BaseTool):
    """Execute a SQL statement on MySQL (may modify data).

    Supports statement/templateParameters/parameters modes (same as PgSQLTool).
    """

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        statement: str = "",
        template_parameters: list[dict[str, Any]] | None = None,
        parameters: list[dict[str, Any]] | None = None,
    ):
        """初始化工具配置。"""
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
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await _execute_sql_with_modes(
                source, self._statement, self._template_parameters, self._parameters, params
            )
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        param_defs = self._template_parameters or self._parameters
        parameters = _build_sql_tool_parameters(param_defs, self._statement, "SQL statement to execute")
        return ToolManifest(
            description=self.description,
            parameters=parameters,
            auth_required=self.auth_required,
        )


@register_tool("mysql-execute-sql")
@dataclass
class MySQLExecuteSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 MySQL 上执行 SQL 语句（可能修改数据）"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "mysql-execute-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MySQLExecuteSQLToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 MySQL 上执行 SQL 语句"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
            parameters=data.get("parameters", []),
        )

    async def initialize(self) -> MySQLExecuteSQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return MySQLExecuteSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
            parameters=self.parameters,
        )


# ---------------------------------------------------------------------------
# MySQL list-type tools
# ---------------------------------------------------------------------------

class MySQLListTool(BaseTool):
    """Generic MySQL list tool that executes a fixed SQL query."""

    def __init__(self, cfg: ConfigBase, source_name: str, sql: str, param_defs: list[ParameterManifest] | None = None):
        """初始化工具配置。"""
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
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await source.execute_sql(self._sql, params if params else None)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


_MYSQL_LIST_TOOLS: list[tuple[str, str, str, list[ParameterManifest]]] = [
    ("mysql-list-tables",
     "列出 MySQL 数据库中的所有表",
     "SHOW TABLES",
     []),
    ("mysql-list-table-stats",
     "List table statistics in the MySQL database",
     "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()",
     []),
    ("mysql-list-active-queries",
     "List active queries in the MySQL database",
     "SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO FROM information_schema.PROCESSLIST WHERE COMMAND != 'Sleep'",
     []),
    ("mysql-list-all-locks",
     "List all locks in the MySQL database",
     "SELECT * FROM information_schema.INNODB_LOCKS",
     []),
    ("mysql-list-table-fragmentation",
     "List table fragmentation in the MySQL database",
     "SELECT TABLE_NAME, DATA_FREE, DATA_LENGTH, ROUND(DATA_FREE / (DATA_LENGTH + 1), 2) AS fragmentation_ratio FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND DATA_FREE > 0",
     []),
    ("mysql-list-tables-missing-unique-indexes",
     "List tables missing unique indexes in the MySQL database",
     "SELECT T.TABLE_NAME FROM information_schema.TABLES T LEFT JOIN information_schema.TABLE_CONSTRAINTS C ON T.TABLE_NAME = C.TABLE_NAME AND C.CONSTRAINT_TYPE = 'UNIQUE' WHERE T.TABLE_SCHEMA = DATABASE() AND C.CONSTRAINT_NAME IS NULL",
     []),
    ("mysql-show-query-stats",
     "Show query statistics in the MySQL database",
     "SELECT * FROM performance_schema.events_statements_summary_by_digest ORDER BY COUNT_STAR DESC LIMIT 20",
     []),
]

_MYSQL_PARAM_TOOLS: list[tuple[str, str, str, list[ParameterManifest]]] = [
    ("mysql-get-query-plan",
     "Get the query execution plan for a SQL statement",
     "EXPLAIN :sql",
     [
         ParameterManifest(name="sql", type="string", description="SQL statement to explain", required=True),
     ]),
]


def _make_mysql_list_tool_config(tool_type: str, description: str, sql: str, param_defs: list[ParameterManifest]):
    """构造MySQL 列表工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _MySQLListToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _MySQLListToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> MySQLListTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return MySQLListTool(cfg=cfg, source_name=self.source, sql=sql, param_defs=param_defs)

    _MySQLListToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _MySQLListToolConfig.__qualname__ = _MySQLListToolConfig.__name__
    return _MySQLListToolConfig


for _tool_type, _desc, _sql, _params in _MYSQL_LIST_TOOLS + _MYSQL_PARAM_TOOLS:
    _make_mysql_list_tool_config(_tool_type, _desc, _sql, _params)
