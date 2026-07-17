"""SQLite tools — sql and execute-sql.

Maps to Go: internal/tools/sqlite/
  - sqlitesql/     → sqlite-sql
  - sqliteexecutesql/ → sqlite-execute-sql

Other SQL database tools (postgres, mysql, mssql, etc.) are registered
in their respective dedicated files (pg_tools.py, mysql_tools.py, etc.)
and other_sql_tools.py.  This file previously contained generic
*-exec-sql / *-list-tables / *-describe-table tools that were either
duplicates of the per-DB files or did not exist in Go (describe-table).
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
    _execute_sql_with_modes,
    _get_typed_source_async,
    _manifests_from_dicts,
    register_tool,
)


# ---------------------------------------------------------------------------
# SQLite-SQL (read-only query)
# Maps to Go: sqlite-sql (internal/tools/sqlite/sqlitesql/)
# ---------------------------------------------------------------------------

class SQLiteSQLTool(BaseTool):
    """Run a read-only SQL query on SQLite."""

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        statement: str = "",
        template_parameters: list[dict[str, Any]] | None = None,
    ):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._statement = statement
        self._template_parameters = template_parameters or []

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
                source, self._statement, self._template_parameters, [], params
            )
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        if self._template_parameters:
            parameters = _manifests_from_dicts(self._template_parameters)
        else:
            parameters = [ParameterManifest(name="sql", type="string", description="SQL query to execute", required=True)]
        return ToolManifest(
            description=self.description,
            parameters=parameters,
            auth_required=self.auth_required,
        )


@register_tool("sqlite-sql")
@dataclass
class SQLiteSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 SQLite 上执行只读 SQL 查询"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "sqlite-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SQLiteSQLToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 SQLite 上执行只读 SQL 查询"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
        )

    async def initialize(self) -> SQLiteSQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return SQLiteSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
        )


# ---------------------------------------------------------------------------
# SQLite-Execute-SQL (write/DDL)
# Maps to Go: sqlite-execute-sql (internal/tools/sqlite/sqliteexecutesql/)
# ---------------------------------------------------------------------------

class SQLiteExecuteSQLTool(BaseTool):
    """Execute a SQL statement on SQLite."""

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        statement: str = "",
        template_parameters: list[dict[str, Any]] | None = None,
    ):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name
        self._statement = statement
        self._template_parameters = template_parameters or []

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
                source, self._statement, self._template_parameters, [], params
            )
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        if self._template_parameters:
            parameters = _manifests_from_dicts(self._template_parameters)
        else:
            parameters = [ParameterManifest(name="sql", type="string", description="SQL statement to execute", required=True)]
        return ToolManifest(
            description=self.description,
            parameters=parameters,
            auth_required=self.auth_required,
        )


@register_tool("sqlite-execute-sql")
@dataclass
class SQLiteExecuteSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 SQLite 上执行 SQL 语句"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "sqlite-execute-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SQLiteExecuteSQLToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 SQLite 上执行 SQL 语句"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
        )

    async def initialize(self) -> SQLiteExecuteSQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return SQLiteExecuteSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
        )
