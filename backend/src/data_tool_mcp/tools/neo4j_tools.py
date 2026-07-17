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
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# neo4j-cypher — read-only Cypher query
# ---------------------------------------------------------------------------

class Neo4jCypherTool(BaseTool):
    """Run a read-only Cypher query on Neo4j."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, Neo4jSource)
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
        """返回工具清单，包含名称、描述和参数定义。"""
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
        """返回工具类型标识符。"""
        return "neo4j-cypher"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Neo4jCypherToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Neo4j 上执行只读 Cypher 查询"))

    async def initialize(self) -> Neo4jCypherTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return Neo4jCypherTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# neo4j-execute-cypher — write Cypher
# ---------------------------------------------------------------------------

class Neo4jExecuteCypherTool(BaseTool):
    """Execute a Cypher statement on Neo4j (may modify data)."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, Neo4jSource)
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
        """返回工具清单，包含名称、描述和参数定义。"""
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
        """返回工具类型标识符。"""
        return "neo4j-execute-cypher"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Neo4jExecuteCypherToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Neo4j 上执行 Cypher 语句"))

    async def initialize(self) -> Neo4jExecuteCypherTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return Neo4jExecuteCypherTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# neo4j-schema
# ---------------------------------------------------------------------------

class Neo4jSchemaTool(BaseTool):
    """Get the Neo4j graph schema."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, Neo4jSource)
        try:
            schema = await source.get_schema()
            return {"schema": schema}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=[], auth_required=self.auth_required)


@register_tool("neo4j-schema")
@dataclass
class Neo4jSchemaToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "获取 Neo4j 图数据库的 Schema"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "neo4j-schema"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Neo4jSchemaToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "获取 Neo4j 图数据库的 Schema"))

    async def initialize(self) -> Neo4jSchemaTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return Neo4jSchemaTool(cfg=cfg, source_name=self.source)
