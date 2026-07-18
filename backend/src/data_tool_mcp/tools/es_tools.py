"""Elasticsearch tools — 2 tools for ES|QL queries.

Maps to Go: internal/tools/elasticsearch/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.elasticsearch import ElasticsearchSource
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
# elasticsearch-esql — read-only
# ---------------------------------------------------------------------------


class ESESQLTool(BaseTool):
    """Run a read-only ES|QL query on Elasticsearch."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, ElasticsearchSource
        )
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            rows = await source.execute_esql(query)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="query", type="string", description="ES|QL query to execute", required=True
                )
            ],
            auth_required=self.auth_required,
        )


@register_tool("elasticsearch-esql")
@dataclass
class ESESQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Elasticsearch 上执行只读 ES|QL 查询"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "elasticsearch-esql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ESESQLToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 Elasticsearch 上执行只读 ES|QL 查询"),
        )

    async def initialize(self) -> ESESQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return ESESQLTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# elasticsearch-execute-esql — read-write
# ---------------------------------------------------------------------------


class ESExecuteESQLTool(BaseTool):
    """Execute an ES|QL statement on Elasticsearch (may modify data)."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(
            cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True)
        )
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, ElasticsearchSource
        )
        try:
            query = params.get("query", "")
            if not query:
                raise ValueError("missing 'query' parameter")
            rows = await source.execute_esql(query)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="query",
                    type="string",
                    description="ES|QL statement to execute",
                    required=True,
                )
            ],
            auth_required=self.auth_required,
        )


@register_tool("elasticsearch-execute-esql")
@dataclass
class ESExecuteESQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Elasticsearch 上执行 ES|QL 语句（可能修改数据）"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "elasticsearch-execute-esql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ESExecuteESQLToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 Elasticsearch 上执行 ES|QL 语句"),
        )

    async def initialize(self) -> ESExecuteESQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return ESExecuteESQLTool(cfg=cfg, source_name=self.source)
