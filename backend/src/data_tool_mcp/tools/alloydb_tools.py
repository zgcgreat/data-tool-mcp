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
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# AlloyDB 操作分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _al_list_clusters(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出AlloyDB的集群列表。"""
    return {"clusters": await source.list_clusters()}

async def _al_get_cluster(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取AlloyDB的集群。"""
    return {"cluster": await source.get_cluster(params["cluster_id"])}

async def _al_create_cluster(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """创建AlloyDB的集群。"""
    return {"result": await source.create_cluster(params["cluster_id"], params.get("cluster", {}))}

async def _al_list_instances(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出AlloyDB的实例列表。"""
    return {"instances": await source.list_instances(params["cluster_id"])}

async def _al_get_instance(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取AlloyDB的实例。"""
    return {"instance": await source.get_instance(params["cluster_id"], params["instance_id"])}

async def _al_create_instance(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """创建AlloyDB的实例。"""
    return {"result": await source.create_instance(params["cluster_id"], params["instance_id"], params.get("instance", {}))}

async def _al_list_users(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出AlloyDB的用户列表。"""
    return {"users": await source.list_users(params["cluster_id"])}

async def _al_get_user(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取AlloyDB的用户。"""
    return {"user": await source.get_user(params["cluster_id"], params["user_id"])}

async def _al_create_user(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """创建AlloyDB的用户。"""
    return {"result": await source.create_user(params["cluster_id"], params["user_id"], params.get("user", {}))}

async def _al_wait_for_operation(source: AlloyDBAdminSource, params: dict[str, Any]) -> dict[str, Any]:
    """等待AlloyDB的for操作完成。"""
    return {"result": await source.wait_for_operation(params["operation_name"])}


_AL_DISPATCH: dict[str, Any] = {
    "alloydb-list-clusters": _al_list_clusters,
    "alloydb-get-cluster": _al_get_cluster,
    "alloydb-create-cluster": _al_create_cluster,
    "alloydb-list-instances": _al_list_instances,
    "alloydb-get-instance": _al_get_instance,
    "alloydb-create-instance": _al_create_instance,
    "alloydb-list-users": _al_list_users,
    "alloydb-get-user": _al_get_user,
    "alloydb-create-user": _al_create_user,
    "alloydb-wait-for-operation": _al_wait_for_operation,
}


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
        """初始化工具配置。"""
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, AlloyDBAdminSource)
        try:
            handler = _AL_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown AlloyDB tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
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
    """构造AlloyDB工具配置。"""
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
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _AlloyDBToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> AlloyDBGenericTool:
            """创建并初始化工具实例。"""
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
