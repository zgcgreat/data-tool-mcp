"""Neo4j tools — 3 tools for Neo4j graph database.

Maps to Go: internal/tools/neo4j/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.neo4j_source import Neo4jSource
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


async def _get_neo4j_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> Neo4jSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, Neo4jSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Neo4j source")
    return source


# ---------------------------------------------------------------------------
# neo4j-cypher — read-only Cypher query
# ---------------------------------------------------------------------------

class Neo4jCypherTool(BaseTool):
    """Run a read-only Cypher query on Neo4j."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_neo4j_source(source_provider, self._source_name, self.name)
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            query_params = params.get("params")
            rows = await source.execute_cypher(query, params=query_params)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="query", type="string", description="Cypher query to execute", required=True),
                ParameterManifest(name="params", type="object", description="Query parameters", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("neo4j-cypher")
@dataclass
class Neo4jCypherToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Neo4j 上执行只读 Cypher 查询"

    @property
    def tool_type(self) -> str:
        return "neo4j-cypher"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Neo4jCypherToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Neo4j 上执行只读 Cypher 查询"))

    async def initialize(self) -> Neo4jCypherTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return Neo4jCypherTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# neo4j-execute-cypher — write Cypher
# ---------------------------------------------------------------------------

class Neo4jExecuteCypherTool(BaseTool):
    """Execute a Cypher statement on Neo4j (may modify data)."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_neo4j_source(source_provider, self._source_name, self.name)
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            query_params = params.get("params")
            rows = await source.execute_cypher(query, params=query_params)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="query", type="string", description="Cypher statement to execute", required=True),
                ParameterManifest(name="params", type="object", description="Query parameters", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("neo4j-execute-cypher")
@dataclass
class Neo4jExecuteCypherToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Neo4j 上执行 Cypher 语句（可能修改数据）"

    @property
    def tool_type(self) -> str:
        return "neo4j-execute-cypher"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Neo4jExecuteCypherToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Neo4j 上执行 Cypher 语句"))

    async def initialize(self) -> Neo4jExecuteCypherTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return Neo4jExecuteCypherTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# neo4j-schema
# ---------------------------------------------------------------------------

class Neo4jSchemaTool(BaseTool):
    """Get the Neo4j graph schema."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_neo4j_source(source_provider, self._source_name, self.name)
        try:
            schema = await source.get_schema()
            return {"schema": schema}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=[], auth_required=self.auth_required)


@register_tool("neo4j-schema")
@dataclass
class Neo4jSchemaToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "获取 Neo4j 图数据库的 Schema"

    @property
    def tool_type(self) -> str:
        return "neo4j-schema"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Neo4jSchemaToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "获取 Neo4j 图数据库的 Schema"))

    async def initialize(self) -> Neo4jSchemaTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return Neo4jSchemaTool(cfg=cfg, source_name=self.source)
