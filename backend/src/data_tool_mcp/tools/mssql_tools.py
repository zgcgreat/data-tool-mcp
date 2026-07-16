"""MSSQL tools — 3 tools for SQL Server introspection.

Maps to Go: internal/tools/mssql/
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
# mssql-sql
# ---------------------------------------------------------------------------

class MSSQLSQLTool(BaseTool):
    """Run a read-only SQL query on MSSQL.

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
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._statement = statement
        self._template_parameters = template_parameters or []
        self._parameters = parameters or []

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
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


@register_tool("mssql-sql")
@dataclass
class MSSQLSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 MSSQL 上执行只读 SQL 查询"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        return "mssql-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MSSQLSQLToolConfig:
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 MSSQL 上执行只读 SQL 查询"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
            parameters=data.get("parameters", []),
        )

    async def initialize(self) -> MSSQLSQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MSSQLSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
            parameters=self.parameters,
        )


# ---------------------------------------------------------------------------
# mssql-execute-sql
# ---------------------------------------------------------------------------

class MSSQLExecuteSQLTool(BaseTool):
    """Execute a SQL statement on MSSQL (may modify data).

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
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name
        self._statement = statement
        self._template_parameters = template_parameters or []
        self._parameters = parameters or []

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
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


@register_tool("mssql-execute-sql")
@dataclass
class MSSQLExecuteSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 MSSQL 上执行 SQL 语句（可能修改数据）"
    statement: str = ""
    template_parameters: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_type(self) -> str:
        return "mssql-execute-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MSSQLExecuteSQLToolConfig:
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 MSSQL 上执行 SQL 语句"),
            statement=data.get("statement", ""),
            template_parameters=data.get("templateParameters", []),
            parameters=data.get("parameters", []),
        )

    async def initialize(self) -> MSSQLExecuteSQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MSSQLExecuteSQLTool(
            cfg=cfg,
            source_name=self.source,
            statement=self.statement,
            template_parameters=self.template_parameters,
            parameters=self.parameters,
        )


# ---------------------------------------------------------------------------
# mssql-list-tables
# ---------------------------------------------------------------------------

class MSSQLListTablesTool(BaseTool):
    """List all tables in the MSSQL database."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, SQLSource)
        try:
            rows = await source.execute_sql(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
            )
            return {"tables": [r["TABLE_NAME"] for r in rows]}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=[], auth_required=self.auth_required)


@register_tool("mssql-list-tables")
@dataclass
class MSSQLListTablesToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "列出 MSSQL 数据库中的所有表"

    @property
    def tool_type(self) -> str:
        return "mssql-list-tables"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MSSQLListTablesToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "列出 MSSQL 数据库中的所有表"))

    async def initialize(self) -> MSSQLListTablesTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MSSQLListTablesTool(cfg=cfg, source_name=self.source)
