"""Dataproc tools — 4 tools for Dataproc cluster and job management.

Maps to Go: internal/tools/dataproc/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.dataproc_source import DataprocSource
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
# Dataproc 操作分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _dpc_list_jobs(source: DataprocSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Dataproc的作业列表。"""
    return {"jobs": await source.list_jobs()}

async def _dpc_get_job(source: DataprocSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Dataproc的作业。"""
    return {"job": await source.get_job(params["job_id"])}

async def _dpc_list_clusters(source: DataprocSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Dataproc的集群列表。"""
    return {"clusters": await source.list_clusters()}

async def _dpc_get_cluster(source: DataprocSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Dataproc的集群。"""
    return {"cluster": await source.get_cluster(params["cluster_name"])}


_DATAPROC_DISPATCH: dict[str, Any] = {
    "dataproc-list-jobs": _dpc_list_jobs,
    "dataproc-get-job": _dpc_get_job,
    "dataproc-list-clusters": _dpc_list_clusters,
    "dataproc-get-cluster": _dpc_get_cluster,
}


class DataprocGenericTool(BaseTool):
    """Generic Dataproc tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest]):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, DataprocSource)
        try:
            handler = _DATAPROC_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Dataproc tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


_DATAPROC_TOOLS: list[tuple[str, str, list[ParameterManifest]]] = [
    ("dataproc-list-jobs", "List all Dataproc jobs", []),
    ("dataproc-get-job", "Get a Dataproc job",
     [ParameterManifest(name="job_id", type="string", description="Job ID", required=True)]),
    ("dataproc-list-clusters", "List all Dataproc clusters", []),
    ("dataproc-get-cluster", "Get a Dataproc cluster",
     [ParameterManifest(name="cluster_name", type="string", description="Cluster name", required=True)]),
]


def _make_dataproc_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest]):
    """构造Dataproc工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _DataprocToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _DataprocToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> DataprocGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return DataprocGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs)

    _DataprocToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _DataprocToolConfig.__qualname__ = _DataprocToolConfig.__name__
    return _DataprocToolConfig


for _tool_type, _desc, _params in _DATAPROC_TOOLS:
    _make_dataproc_tool_config(_tool_type, _desc, _params)
