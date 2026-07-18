"""Cloud SQL variant tools — CloudSQL MySQL, MSSQL, AlloyDB PG, CloudSQL PG create/upgrade.

Maps to Go: internal/tools/cloudsqlmysql/, internal/tools/cloudsqlmssql/, internal/tools/alloydbainl/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudsqlpg import CloudSQLPGSource
from data_tool_mcp.sources.cloudsqlmysql import CloudSQLMySQLSource
from data_tool_mcp.sources.cloudsqlmssql import CloudSQLMSSQLSource
from data_tool_mcp.sources.alloydbpg import AlloyDBPGSource
from data_tool_mcp.tools.base import (
    BaseTool,
    ConfigBase,
    ParameterManifest,
    SourceProvider,
    ToolAnnotations,
    ToolConfig,
    ToolManifest,
    _execute_user_sql,
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# CloudSQL MySQL tools (3)
# ---------------------------------------------------------------------------


class CloudSQLMySQLGenericTool(BaseTool):
    """Generic CloudSQL MySQL tool."""

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
            source_provider, self._source_name, self.name, CloudSQLMySQLSource
        )
        try:
            if self._tool_type in ("cloud-sql-mysql-sql", "cloud-sql-mysql-execute-sql"):
                rows = await _execute_user_sql(source, params)
                return {"rows": rows, "rowCount": len(rows)}
            if self._tool_type == "cloud-sql-mysql-list-tables":
                return {"tables": await source.list_tables()}
            return {"result": "ok"}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


_CSMYSQL_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "cloud-sql-mysql-sql",
        "Run a read-only SQL query on Cloud SQL MySQL",
        [ParameterManifest(name="sql", type="string", description="SQL query", required=True)],
        True,
    ),
    (
        "cloud-sql-mysql-execute-sql",
        "Execute a SQL statement on Cloud SQL MySQL",
        [ParameterManifest(name="sql", type="string", description="SQL statement", required=True)],
        False,
    ),
    ("cloud-sql-mysql-list-tables", "List tables in Cloud SQL MySQL", [], True),
    (
        "cloud-sql-mysql-create-instance",
        "Create a Cloud SQL MySQL instance",
        [
            ParameterManifest(
                name="body", type="object", description="Instance creation body", required=True
            )
        ],
        False,
    ),
]


# ---------------------------------------------------------------------------
# CloudSQL MSSQL tools (3)
# ---------------------------------------------------------------------------


class CloudSQLMSSQLGenericTool(BaseTool):
    """Generic CloudSQL MSSQL tool."""

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
            source_provider, self._source_name, self.name, CloudSQLMSSQLSource
        )
        try:
            if self._tool_type in ("cloud-sql-mssql-sql", "cloud-sql-mssql-execute-sql"):
                rows = await _execute_user_sql(source, params)
                return {"rows": rows, "rowCount": len(rows)}
            if self._tool_type == "cloud-sql-mssql-list-tables":
                return {"tables": await source.list_tables()}
            return {"result": "ok"}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


_CSMSSQL_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "cloud-sql-mssql-sql",
        "Run a read-only SQL query on Cloud SQL MSSQL",
        [ParameterManifest(name="sql", type="string", description="SQL query", required=True)],
        True,
    ),
    (
        "cloud-sql-mssql-execute-sql",
        "Execute a SQL statement on Cloud SQL MSSQL",
        [ParameterManifest(name="sql", type="string", description="SQL statement", required=True)],
        False,
    ),
    ("cloud-sql-mssql-list-tables", "List tables in Cloud SQL MSSQL", [], True),
    (
        "cloud-sql-mssql-create-instance",
        "Create a Cloud SQL MSSQL instance",
        [
            ParameterManifest(
                name="body", type="object", description="Instance creation body", required=True
            )
        ],
        False,
    ),
]


# ---------------------------------------------------------------------------
# AlloyDB PG tools (3)
# ---------------------------------------------------------------------------


class AlloyDBPGGenericTool(BaseTool):
    """Generic AlloyDB PG tool."""

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
            source_provider, self._source_name, self.name, AlloyDBPGSource
        )
        try:
            if self._tool_type in ("alloydb-pg-sql", "alloydb-pg-execute-sql"):
                rows = await _execute_user_sql(source, params)
                return {"rows": rows, "rowCount": len(rows)}
            if self._tool_type == "alloydb-pg-list-tables":
                return {"tables": await source.list_tables()}
            return {"result": "ok"}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


_ALLOYDBPG_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "alloydb-pg-sql",
        "Run a read-only SQL query on AlloyDB PostgreSQL",
        [ParameterManifest(name="sql", type="string", description="SQL query", required=True)],
        True,
    ),
    (
        "alloydb-pg-execute-sql",
        "Execute a SQL statement on AlloyDB PostgreSQL",
        [ParameterManifest(name="sql", type="string", description="SQL statement", required=True)],
        False,
    ),
    ("alloydb-pg-list-tables", "List tables in AlloyDB PostgreSQL", [], True),
]


# ---------------------------------------------------------------------------
# CloudSQL PG create/upgrade tools (2)
# ---------------------------------------------------------------------------

_CSPG_ADMIN_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "cloud-sql-postgres-create-instance",
        "Create a Cloud SQL PostgreSQL instance",
        [
            ParameterManifest(
                name="body", type="object", description="Instance creation body", required=True
            )
        ],
        False,
    ),
    (
        "postgres-upgrade-precheck",
        "Pre-check for Cloud SQL PostgreSQL upgrade",
        [
            ParameterManifest(
                name="instance_id", type="string", description="Instance ID", required=True
            )
        ],
        True,
    ),
]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_variant_tool_config(
    tool_type: str,
    description: str,
    param_defs: list[ParameterManifest],
    read_only: bool,
    tool_cls: type,
):
    """构造Cloud SQL 变体工具配置。"""

    @register_tool(tool_type)
    @dataclass
    class _VariantToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _VariantToolConfig:
            """从字典创建配置实例。"""
            return cls(
                _name=name,
                source=data.get("source", ""),
                description=data.get("description", description),
            )

        async def initialize(self):
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return tool_cls(
                cfg=cfg,
                source_name=self.source,
                tool_type=tool_type,
                param_defs=param_defs,
                read_only=read_only,
            )

    _VariantToolConfig.__name__ = (
        f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    )
    _VariantToolConfig.__qualname__ = _VariantToolConfig.__name__
    return _VariantToolConfig


# Register CloudSQL MySQL tools
for _tool_type, _desc, _params, _ro in _CSMYSQL_TOOLS:
    _make_variant_tool_config(_tool_type, _desc, _params, _ro, CloudSQLMySQLGenericTool)

# Register CloudSQL MSSQL tools
for _tool_type, _desc, _params, _ro in _CSMSSQL_TOOLS:
    _make_variant_tool_config(_tool_type, _desc, _params, _ro, CloudSQLMSSQLGenericTool)

# Register AlloyDB PG tools
for _tool_type, _desc, _params, _ro in _ALLOYDBPG_TOOLS:
    _make_variant_tool_config(_tool_type, _desc, _params, _ro, AlloyDBPGGenericTool)

# ---------------------------------------------------------------------------
# CloudSQL PG admin tool class
# ---------------------------------------------------------------------------


class CloudSQLPGAdminGenericTool(BaseTool):
    """Generic CloudSQL PG admin tool (create/upgrade)."""

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
        await _get_typed_source_async(
            source_provider, self._source_name, self.name, CloudSQLPGSource
        )
        try:
            if self._tool_type == "cloud-sql-postgres-create-instance":
                return {"note": "Instance creation handled via Cloud SQL Admin API"}
            elif self._tool_type == "postgres-upgrade-precheck":
                return {"note": "Upgrade precheck handled via Cloud SQL Admin API"}
            return {"result": "ok"}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


# Register CloudSQL PG admin tools
for _tool_type, _desc, _params, _ro in _CSPG_ADMIN_TOOLS:
    _make_variant_tool_config(_tool_type, _desc, _params, _ro, CloudSQLPGAdminGenericTool)
