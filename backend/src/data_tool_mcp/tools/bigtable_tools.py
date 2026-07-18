"""Bigtable tools — 1 tool for Bigtable federated SQL queries.

Maps to Go: internal/tools/bigtable/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.bigtable import BigtableSource
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


class BigtableSQLTool(BaseTool):
    """Run a federated SQL query on Bigtable via BigQuery."""

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
            source_provider, self._source_name, self.name, BigtableSource
        )
        try:
            sql = params.get("sql", "")
            if not sql:
                raise ValueError("missing 'sql' parameter")
            rows = await source.execute_sql(sql)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="sql", type="string", description="SQL query to execute", required=True
                )
            ],
            auth_required=self.auth_required,
        )


@register_tool("bigtable-sql")
@dataclass
class BigtableSQLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 Bigtable 上执行联邦 SQL 查询"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "bigtable-sql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> BigtableSQLToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在 Bigtable 上执行联邦 SQL 查询"),
        )

    async def initialize(self) -> BigtableSQLTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return BigtableSQLTool(cfg=cfg, source_name=self.source)
