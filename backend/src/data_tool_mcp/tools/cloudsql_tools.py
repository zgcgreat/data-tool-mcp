"""Cloud SQL Admin tools — 11 tools for Cloud SQL instance management.

Maps to Go: internal/tools/cloudsql/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudsqladmin import CloudSQLAdminSource
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
# Cloud SQL Admin 操作分发表 — handler 签名 (source, params, access_token) -> dict
# ---------------------------------------------------------------------------

async def _cs_list_instances(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """列出Cloud SQL的实例列表。"""
    return {"instances": await source.list_instances()}

async def _cs_get_instance(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """获取Cloud SQL的实例。"""
    return {"instance": await source.get_instance(params["instance_id"])}

async def _cs_create_database(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """创建Cloud SQL的数据库。"""
    return {"result": await source.create_database(params["instance_id"], params["database"])}

async def _cs_list_databases(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """列出Cloud SQL的数据库列表。"""
    return {"databases": await source.list_databases(params["instance_id"])}

async def _cs_create_users(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """创建Cloud SQL的用户列表。"""
    return {"result": await source.create_users(params["instance_id"], params["name"], params["password"])}

async def _cs_clone_instance(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """克隆Cloud SQL的实例。"""
    return {"result": await source.clone_instance(params["instance_id"], params.get("clone_body", {}))}

async def _cs_create_backup(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """创建Cloud SQL的backup。"""
    return {"result": await source.create_backup(params["instance_id"], params.get("body", {}))}

async def _cs_restore_backup(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """恢复Cloud SQL的backup。"""
    return {"result": await source.restore_backup(params["instance_id"], params.get("body", {}))}

async def _cs_wait_for_operation(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """等待Cloud SQL的for操作完成。"""
    return {"result": await source.wait_for_operation(params["operation_id"])}

async def _cs_admin_execute(source: CloudSQLAdminSource, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    """执行 Cloud SQL 管理操作。"""
    return {"result": await source.execute_sql(params["project"], params["instanceId"], params["database"], params["sql"], access_token)}


_CS_DISPATCH: dict[str, Any] = {
    "cloud-sql-list-instances": _cs_list_instances,
    "cloud-sql-get-instance": _cs_get_instance,
    "cloud-sql-create-database": _cs_create_database,
    "cloud-sql-list-databases": _cs_list_databases,
    "cloud-sql-create-users": _cs_create_users,
    "cloud-sql-clone-instance": _cs_clone_instance,
    "cloud-sql-create-backup": _cs_create_backup,
    "cloud-sql-restore-backup": _cs_restore_backup,
    "cloud-sql-wait-for-operation": _cs_wait_for_operation,
    "cloud-sql-admin-execute-many": _cs_admin_execute,
    "cloud-sql-admin-sql-many": _cs_admin_execute,
}


# ---------------------------------------------------------------------------
# Generic Cloud SQL Admin tool
# ---------------------------------------------------------------------------

class CloudSQLGenericTool(BaseTool):
    """Generic Cloud SQL Admin tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        """初始化工具配置。"""
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, CloudSQLAdminSource)
        try:
            handler = _CS_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Cloud SQL tool type: {self._tool_type}")
            return await handler(source, params, access_token)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_CS_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("cloud-sql-list-instances", "List all Cloud SQL instances", [], True),
    ("cloud-sql-get-instance", "Get details of a Cloud SQL instance",
     [ParameterManifest(name="instance_id", type="string", description="Cloud SQL instance ID", required=True)], True),
    ("cloud-sql-create-database", "Create a database in a Cloud SQL instance",
     [ParameterManifest(name="instance_id", type="string", description="Cloud SQL instance ID", required=True),
      ParameterManifest(name="database", type="string", description="Database name", required=True)], False),
    ("cloud-sql-list-databases", "List all databases in a Cloud SQL instance",
     [ParameterManifest(name="instance_id", type="string", description="Cloud SQL instance ID", required=True)], True),
    ("cloud-sql-create-users", "Create a user in a Cloud SQL instance",
     [ParameterManifest(name="instance_id", type="string", description="Cloud SQL instance ID", required=True),
      ParameterManifest(name="name", type="string", description="User name", required=True),
      ParameterManifest(name="password", type="string", description="User password", required=True)], False),
    ("cloud-sql-clone-instance", "Clone a Cloud SQL instance",
     [ParameterManifest(name="instance_id", type="string", description="Cloud SQL instance ID", required=True),
      ParameterManifest(name="clone_body", type="object", description="Clone request body", required=False)], False),
    ("cloud-sql-create-backup", "Create a backup of a Cloud SQL instance",
     [ParameterManifest(name="instance_id", type="string", description="Cloud SQL instance ID", required=True),
      ParameterManifest(name="body", type="object", description="Backup request body", required=False)], False),
    ("cloud-sql-restore-backup", "Restore a Cloud SQL instance from a backup",
     [ParameterManifest(name="instance_id", type="string", description="Cloud SQL instance ID", required=True),
      ParameterManifest(name="body", type="object", description="Restore request body", required=False)], False),
    ("cloud-sql-wait-for-operation", "Wait for a Cloud SQL operation to complete",
     [ParameterManifest(name="operation_id", type="string", description="Operation ID", required=True)], True),
    ("cloud-sql-admin-execute-many", "Execute multiple SQL statements on a Cloud SQL instance",
     [ParameterManifest(name="project", type="string", description="The GCP project ID", required=True),
      ParameterManifest(name="instanceId", type="string", description="The Cloud SQL instance ID", required=True),
      ParameterManifest(name="database", type="string", description="The database name", required=True),
      ParameterManifest(name="sql", type="string", description="The SQL statement to execute", required=True)], False),
    ("cloud-sql-admin-sql-many", "Run multiple read-only SQL queries on a Cloud SQL instance",
     [ParameterManifest(name="project", type="string", description="The GCP project ID", required=True),
      ParameterManifest(name="instanceId", type="string", description="The Cloud SQL instance ID", required=True),
      ParameterManifest(name="database", type="string", description="The database name", required=True),
      ParameterManifest(name="sql", type="string", description="The SQL query to run", required=True)], True),
]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_cs_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    """构造Cloud SQL工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _CSToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _CSToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> CloudSQLGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return CloudSQLGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _CSToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _CSToolConfig.__qualname__ = _CSToolConfig.__name__
    return _CSToolConfig


for _tool_type, _desc, _params, _ro in _CS_TOOLS:
    _make_cs_tool_config(_tool_type, _desc, _params, _ro)
