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
    register_tool,
)


def _get_cloudsql_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> CloudSQLAdminSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, CloudSQLAdminSource):
        raise TypeError(f"source {source_name!r} is not a Cloud SQL Admin source")
    return source


# ---------------------------------------------------------------------------
# Generic Cloud SQL Admin tool
# ---------------------------------------------------------------------------

class CloudSQLGenericTool(BaseTool):
    """Generic Cloud SQL Admin tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_cloudsql_source(source_provider, self._source_name, self.name)

        if self._tool_type == "cloud-sql-list-instances":
            instances = await source.list_instances()
            return {"instances": instances}
        elif self._tool_type == "cloud-sql-get-instance":
            return {"instance": await source.get_instance(params["instance_id"])}
        elif self._tool_type == "cloud-sql-create-database":
            return {"result": await source.create_database(params["instance_id"], params["database"])}
        elif self._tool_type == "cloud-sql-list-databases":
            databases = await source.list_databases(params["instance_id"])
            return {"databases": databases}
        elif self._tool_type == "cloud-sql-create-users":
            return {"result": await source.create_users(params["instance_id"], params["name"], params["password"])}
        elif self._tool_type == "cloud-sql-clone-instance":
            return {"result": await source.clone_instance(params["instance_id"], params.get("clone_body", {}))}
        elif self._tool_type == "cloud-sql-create-backup":
            return {"result": await source.create_backup(params["instance_id"], params.get("body", {}))}
        elif self._tool_type == "cloud-sql-restore-backup":
            return {"result": await source.restore_backup(params["instance_id"], params.get("body", {}))}
        elif self._tool_type == "cloud-sql-wait-for-operation":
            return {"result": await source.wait_for_operation(params["operation_id"])}
        elif self._tool_type == "cloud-sql-admin-execute-many":
            project = params["project"]
            instance_id = params["instanceId"]
            database = params["database"]
            sql = params["sql"]
            return {"result": await source.execute_sql(project, instance_id, database, sql, access_token)}
        elif self._tool_type == "cloud-sql-admin-sql-many":
            project = params["project"]
            instance_id = params["instanceId"]
            database = params["database"]
            sql = params["sql"]
            return {"result": await source.execute_sql(project, instance_id, database, sql, access_token)}
        else:
            raise ValueError(f"unknown Cloud SQL tool type: {self._tool_type}")

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
    @register_tool(tool_type)
    @dataclass
    class _CSToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _CSToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> CloudSQLGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return CloudSQLGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _CSToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _CSToolConfig.__qualname__ = _CSToolConfig.__name__
    return _CSToolConfig


for _tool_type, _desc, _params, _ro in _CS_TOOLS:
    _make_cs_tool_config(_tool_type, _desc, _params, _ro)
