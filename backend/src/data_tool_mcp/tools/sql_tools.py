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
    register_tool,
)
from data_tool_mcp.tools.template import render_sql_template as render_template


def _get_sql_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
    tool_type: str,
) -> SQLSource:
    """Resolve a SQLSource from the SourceProvider.

    Maps to Go: GetCompatibleSource[SQLSource](resourceMgr, sourceName, toolName, toolType)
    """
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, SQLSource):
        raise TypeError(
            f"invalid source for {tool_type!r} tool: source {source_name!r} is not a SQL source"
        )
    return source


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
        source = _get_sql_source(source_provider, self._source_name, self.name, "sqlite-sql")
        if self._statement:
            sql = render_template(self._statement, params)
        else:
            sql = params.get("sql", "")
            if not sql:
                raise ValueError("missing 'sql' parameter")
        rows = await source.execute_sql(sql)
        return {"rows": rows, "rowCount": len(rows)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        if self._template_parameters:
            parameters = [
                ParameterManifest(
                    name=p.get("name", ""),
                    type=p.get("type", "string"),
                    description=p.get("description", ""),
                    required=p.get("required", False),
                    default=p.get("default"),
                )
                for p in self._template_parameters
            ]
            return ToolManifest(
                description=self.description,
                parameters=parameters,
                auth_required=self.auth_required,
            )
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="sql", type="string", description="SQL query to execute", required=True
                ),
            ],
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
        return "sqlite-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SQLiteSQLToolConfig:
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 SQLite 上执行只读 SQL 查询"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
        )

    async def initialize(self) -> SQLiteSQLTool:
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
        source = _get_sql_source(source_provider, self._source_name, self.name, "sqlite-execute-sql")
        if self._statement:
            sql = render_template(self._statement, params)
        else:
            sql = params.get("sql", "")
            if not sql:
                raise ValueError("missing 'sql' parameter")
        rows = await source.execute_sql(sql)
        return {"rows": rows, "rowCount": len(rows)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        if self._template_parameters:
            parameters = [
                ParameterManifest(
                    name=p.get("name", ""),
                    type=p.get("type", "string"),
                    description=p.get("description", ""),
                    required=p.get("required", False),
                    default=p.get("default"),
                )
                for p in self._template_parameters
            ]
            return ToolManifest(
                description=self.description,
                parameters=parameters,
                auth_required=self.auth_required,
            )
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="sql", type="string", description="SQL statement to execute", required=True
                ),
            ],
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
        return "sqlite-execute-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SQLiteExecuteSQLToolConfig:
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 SQLite 上执行 SQL 语句"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
        )

    async def initialize(self) -> SQLiteExecuteSQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return SQLiteExecuteSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
        )
