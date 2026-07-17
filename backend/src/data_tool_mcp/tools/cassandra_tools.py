"""Cassandra/ScyllaDB/Dgraph tools — 3 tools for CQL and DQL query languages.

Maps to Go: internal/tools/cassandra/, internal/tools/scylladb/, internal/tools/dgraph/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source
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
# cassandra-cql
# ---------------------------------------------------------------------------

class CassandraCQLTool(BaseTool):
    """Run a CQL query on Cassandra."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, Source)
        try:
            cql = params.get("cql", "")
            if not cql:
                raise ValueError("missing 'cql' parameter")
            rows = await source.execute_cql(cql)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[ParameterManifest(name="cql", type="string", description="CQL query to execute", required=True)],
            auth_required=self.auth_required,
        )


@register_tool("cassandra-cql")
@dataclass
class CassandraCQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Cassandra 上执行 CQL 查询"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "cassandra-cql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CassandraCQLToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Cassandra 上执行 CQL 查询"))

    async def initialize(self) -> CassandraCQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return CassandraCQLTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# scylladb-cql
# ---------------------------------------------------------------------------

class ScyllaDBCQLTool(BaseTool):
    """Run a CQL query on ScyllaDB."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, Source)
        try:
            cql = params.get("cql", "")
            if not cql:
                raise ValueError("missing 'cql' parameter")
            rows = await source.execute_cql(cql)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[ParameterManifest(name="cql", type="string", description="CQL query to execute", required=True)],
            auth_required=self.auth_required,
        )


@register_tool("scylladb-cql")
@dataclass
class ScyllaDBCQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 ScyllaDB 上执行 CQL 查询"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "scylladb-cql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ScyllaDBCQLToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 ScyllaDB 上执行 CQL 查询"))

    async def initialize(self) -> ScyllaDBCQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return ScyllaDBCQLTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# dgraph-dql
# ---------------------------------------------------------------------------

class DgraphDQLTool(BaseTool):
    """Run a DQL query on Dgraph."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, Source)
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            variables = params.get("variables")
            rows = await source.execute_dql(query, variables=variables)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="query", type="string", description="DQL query to execute", required=True),
                ParameterManifest(name="variables", type="object", description="Query variables", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("dgraph-dql")
@dataclass
class DgraphDQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Dgraph 上执行 DQL 查询"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "dgraph-dql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DgraphDQLToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Dgraph 上执行 DQL 查询"))

    async def initialize(self) -> DgraphDQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return DgraphDQLTool(cfg=cfg, source_name=self.source)
