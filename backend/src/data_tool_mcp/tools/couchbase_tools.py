"""Couchbase tools — 1 tool for Couchbase SQL++ (N1QL) queries.

Maps to Go: internal/tools/couchbase/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.couchbase import CouchbaseSource
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


def _get_couchbase_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> CouchbaseSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, CouchbaseSource):
        raise TypeError(f"source {source_name!r} is not a Couchbase source")
    return source


class CouchbaseSQLTool(BaseTool):
    """Run a SQL++ query on Couchbase."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_couchbase_source(source_provider, self._source_name, self.name)
        query = params.get("query", "")
        if not query:
            raise ValueError("missing 'query' parameter")
        rows = await source.execute_sql(query, params.get("params"))
        return {"rows": rows, "rowCount": len(rows)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="query", type="string", description="SQL++ query to execute", required=True),
                ParameterManifest(name="params", type="object", description="Query parameters", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("couchbase-sql")
@dataclass
class CouchbaseSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Couchbase 上执行 SQL++ 查询"

    @property
    def tool_type(self) -> str:
        return "couchbase-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CouchbaseSQLToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "在 Couchbase 上执行 SQL++ 查询"))

    async def initialize(self) -> CouchbaseSQLTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return CouchbaseSQLTool(cfg=cfg, source_name=self.source)
