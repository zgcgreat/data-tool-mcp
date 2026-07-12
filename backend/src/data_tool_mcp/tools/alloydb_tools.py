"""AlloyDB Admin tools — 10 tools for AlloyDB cluster/instance/user management.

Maps to Go: internal/tools/alloydb/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.alloydbadmin import AlloyDBAdminSource
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


def _get_alloydb_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> AlloyDBAdminSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, AlloyDBAdminSource):
        raise TypeError(f"source {source_name!r} is not an AlloyDB Admin source")
    return source


# ---------------------------------------------------------------------------
# Tool definitions — (tool_type, description, read_only)
# ---------------------------------------------------------------------------

_ALLOYDB_LIST_TOOLS: list[tuple[str, str]] = [
    ("alloydb-list-clusters", "List all AlloyDB clusters"),
    ("alloydb-list-instances", "List all instances in an AlloyDB cluster"),
    ("alloydb-list-users", "List all users in an AlloyDB cluster"),
]

_ALLOYDB_GET_TOOLS: list[tuple[str, str]] = [
    ("alloydb-get-cluster", "Get details of an AlloyDB cluster"),
    ("alloydb-get-instance", "Get details of an AlloyDB instance"),
    ("alloydb-get-user", "Get details of an AlloyDB user"),
]

_ALLOYDB_CREATE_TOOLS: list[tuple[str, str]] = [
    ("alloydb-create-cluster", "Create an AlloyDB cluster"),
    ("alloydb-create-instance", "Create an AlloyDB instance"),
    ("alloydb-create-user", "Create an AlloyDB user"),
]


# ---------------------------------------------------------------------------
# Generic AlloyDB Admin tool
# ---------------------------------------------------------------------------

class AlloyDBGenericTool(BaseTool):
    """Generic AlloyDB Admin tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_alloydb_source(source_provider, self._source_name, self.name)

        if self._tool_type == "alloydb-list-clusters":
            clusters = await source.list_clusters()
            return {"clusters": clusters}
        elif self._tool_type == "alloydb-get-cluster":
            return {"cluster": await source.get_cluster(params["cluster_id"])}
        elif self._tool_type == "alloydb-create-cluster":
            return {"result": await source.create_cluster(params["cluster_id"], params.get("cluster", {}))}
        elif self._tool_type == "alloydb-list-instances":
            instances = await source.list_instances(params["cluster_id"])
            return {"instances": instances}
        elif self._tool_type == "alloydb-get-instance":
            return {"instance": await source.get_instance(params["cluster_id"], params["instance_id"])}
        elif self._tool_type == "alloydb-create-instance":
            return {"result": await source.create_instance(params["cluster_id"], params["instance_id"], params.get("instance", {}))}
        elif self._tool_type == "alloydb-list-users":
            users = await source.list_users(params["cluster_id"])
            return {"users": users}
        elif self._tool_type == "alloydb-get-user":
            return {"user": await source.get_user(params["cluster_id"], params["user_id"])}
        elif self._tool_type == "alloydb-create-user":
            return {"result": await source.create_user(params["cluster_id"], params["user_id"], params.get("user", {}))}
        elif self._tool_type == "alloydb-wait-for-operation":
            return {"result": await source.wait_for_operation(params["operation_name"])}
        else:
            raise ValueError(f"unknown AlloyDB tool type: {self._tool_type}")

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


# ---------------------------------------------------------------------------
# Parameter definitions per tool type
# ---------------------------------------------------------------------------

_ALLOYDB_PARAMS: dict[str, list[ParameterManifest]] = {
    "alloydb-list-clusters": [],
    "alloydb-get-cluster": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
    ],
    "alloydb-create-cluster": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
        ParameterManifest(name="cluster", type="object", description="Cluster configuration", required=False),
    ],
    "alloydb-list-instances": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
    ],
    "alloydb-get-instance": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
        ParameterManifest(name="instance_id", type="string", description="AlloyDB instance ID", required=True),
    ],
    "alloydb-create-instance": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
        ParameterManifest(name="instance_id", type="string", description="AlloyDB instance ID", required=True),
        ParameterManifest(name="instance", type="object", description="Instance configuration", required=False),
    ],
    "alloydb-list-users": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
    ],
    "alloydb-get-user": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
        ParameterManifest(name="user_id", type="string", description="AlloyDB user ID", required=True),
    ],
    "alloydb-create-user": [
        ParameterManifest(name="cluster_id", type="string", description="AlloyDB cluster ID", required=True),
        ParameterManifest(name="user_id", type="string", description="AlloyDB user ID", required=True),
        ParameterManifest(name="user", type="object", description="User configuration", required=False),
    ],
    "alloydb-wait-for-operation": [
        ParameterManifest(name="operation_name", type="string", description="Operation name to wait for", required=True),
    ],
}

_ALLOYDB_READ_ONLY: set[str] = {
    "alloydb-list-clusters", "alloydb-get-cluster",
    "alloydb-list-instances", "alloydb-get-instance",
    "alloydb-list-users", "alloydb-get-user",
    "alloydb-wait-for-operation",
}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_alloydb_tool_config(tool_type: str, description: str):
    param_defs = _ALLOYDB_PARAMS.get(tool_type, [])
    read_only = tool_type in _ALLOYDB_READ_ONLY

    @register_tool(tool_type)
    @dataclass
    class _AlloyDBToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _AlloyDBToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> AlloyDBGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return AlloyDBGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _AlloyDBToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _AlloyDBToolConfig.__qualname__ = _AlloyDBToolConfig.__name__
    return _AlloyDBToolConfig


# Register all tools
_ALL_ALLOYDB_TOOLS = _ALLOYDB_LIST_TOOLS + _ALLOYDB_GET_TOOLS + _ALLOYDB_CREATE_TOOLS + [
    ("alloydb-wait-for-operation", "Wait for an AlloyDB operation to complete"),
]

for _tool_type, _desc in _ALL_ALLOYDB_TOOLS:
    _make_alloydb_tool_config(_tool_type, _desc)
