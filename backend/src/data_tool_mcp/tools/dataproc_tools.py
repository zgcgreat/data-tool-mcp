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
    register_tool,
)


async def _get_dataproc_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> DataprocSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, DataprocSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Dataproc source")
    return source


class DataprocGenericTool(BaseTool):
    """Generic Dataproc tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest]):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_dataproc_source(source_provider, self._source_name, self.name)
        try:
            if self._tool_type == "dataproc-list-jobs":
                jobs = await source.list_jobs()
                return {"jobs": jobs}
            elif self._tool_type == "dataproc-get-job":
                job = await source.get_job(params["job_id"])
                return {"job": job}
            elif self._tool_type == "dataproc-list-clusters":
                clusters = await source.list_clusters()
                return {"clusters": clusters}
            elif self._tool_type == "dataproc-get-cluster":
                cluster = await source.get_cluster(params["cluster_name"])
                return {"cluster": cluster}
            else:
                raise ValueError(f"unknown Dataproc tool type: {self._tool_type}")
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
    @register_tool(tool_type)
    @dataclass
    class _DataprocToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _DataprocToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> DataprocGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return DataprocGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs)

    _DataprocToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _DataprocToolConfig.__qualname__ = _DataprocToolConfig.__name__
    return _DataprocToolConfig


for _tool_type, _desc, _params in _DATAPROC_TOOLS:
    _make_dataproc_tool_config(_tool_type, _desc, _params)
