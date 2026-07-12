"""Cassandra/ScyllaDB/Dgraph tools — 3 tools for CQL and DQL query languages.

Maps to Go: internal/tools/cassandra/, internal/tools/scylladb/, internal/tools/dgraph/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


# ---------------------------------------------------------------------------
# cassandra-cql
# ---------------------------------------------------------------------------

class CassandraCQLTool(BaseTool):
    """Run a CQL query on Cassandra."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        if source_provider is None:
            raise ValueError(f"tool {self.name!r} requires a source provider")
        source = source_provider.get_source(self._source_name)
        if source is None:
            raise ValueError(f"source {self._source_name!r} not found")
        cql = params.get("cql", "")
        if not cql:
            raise ValueError("missing 'cql' parameter")
        rows = await source.execute_cql(cql)
        return {"rows": rows, "rowCount": len(rows)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
        return "cassandra-cql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CassandraCQLToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Cassandra 上执行 CQL 查询"))

    async def initialize(self) -> CassandraCQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return CassandraCQLTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# scylladb-cql
# ---------------------------------------------------------------------------

class ScyllaDBCQLTool(BaseTool):
    """Run a CQL query on ScyllaDB."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        if source_provider is None:
            raise ValueError(f"tool {self.name!r} requires a source provider")
        source = source_provider.get_source(self._source_name)
        if source is None:
            raise ValueError(f"source {self._source_name!r} not found")
        cql = params.get("cql", "")
        if not cql:
            raise ValueError("missing 'cql' parameter")
        rows = await source.execute_cql(cql)
        return {"rows": rows, "rowCount": len(rows)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
        return "scylladb-cql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ScyllaDBCQLToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 ScyllaDB 上执行 CQL 查询"))

    async def initialize(self) -> ScyllaDBCQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return ScyllaDBCQLTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# dgraph-dql
# ---------------------------------------------------------------------------

class DgraphDQLTool(BaseTool):
    """Run a DQL query on Dgraph."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        if source_provider is None:
            raise ValueError(f"tool {self.name!r} requires a source provider")
        source = source_provider.get_source(self._source_name)
        if source is None:
            raise ValueError(f"source {self._source_name!r} not found")
        query = params.get("query", "")
        if not query:
            raise ValueError("missing 'query' parameter")
        variables = params.get("variables")
        rows = await source.execute_dql(query, variables=variables)
        return {"rows": rows, "rowCount": len(rows)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
        return "dgraph-dql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DgraphDQLToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Dgraph 上执行 DQL 查询"))

    async def initialize(self) -> DgraphDQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return DgraphDQLTool(cfg=cfg, source_name=self.source)
