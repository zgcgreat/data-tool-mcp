"""Cloud SQL PostgreSQL tools — Vector Assist tools only.

Maps to Go: internal/tools/cloudsqlpg/
  - vectorassistdefinespec/      → vector-assist-define-spec
  - vectorassistgetspec/         → vector-assist-get-spec
  - vectorassistlistspecs/       → vector-assist-list-specs
  - vectorassistmodifyspec/      → vector-assist-modify-spec
  - vectorassistdeletespec/      → vector-assist-delete-spec
  - vectorassistgeneratequery/   → vector-assist-generate-query
  - vectorassistimprovequeryrecall/ → vector-assist-improve-query-recall
  - vectorassistapplyspec/       → vector-assist-apply-spec
  - cloudsqlpgcreateinstances/   → cloud-sql-postgres-create-instance (in cloud_sql_variant_tools.py)
  - cloudsqlpgupgradeprecheck/   → postgres-upgrade-precheck (in cloud_sql_variant_tools.py)

Note: Go's cloudsqlpg/ does NOT contain cloud-sql-pg-sql / cloud-sql-pg-execute-sql /
cloud-sql-pg-list-tables tools.  Those were Python-only inventions and have been removed.
Cloud SQL PG SQL operations use the standard postgres-sql / postgres-execute-sql tools
from pg_tools.py instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudsqlpg import CloudSQLPGSource
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
# Vector Assist tools — data-driven registration
# Maps to Go: internal/tools/cloudsqlpg/vectorassist*/
# ---------------------------------------------------------------------------

_VA_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "vector-assist-define-spec",
        "Define a Vector Assist specification",
        [
            ParameterManifest(
                name="spec",
                type="object",
                description="Vector Assist spec definition",
                required=True,
            )
        ],
        False,
    ),
    (
        "vector-assist-get-spec",
        "Get a Vector Assist specification",
        [ParameterManifest(name="spec_id", type="string", description="Spec ID", required=True)],
        True,
    ),
    ("vector-assist-list-specs", "List all Vector Assist specifications", [], True),
    (
        "vector-assist-modify-spec",
        "Modify a Vector Assist specification",
        [
            ParameterManifest(name="spec_id", type="string", description="Spec ID", required=True),
            ParameterManifest(
                name="spec", type="object", description="Updated spec definition", required=True
            ),
        ],
        False,
    ),
    (
        "vector-assist-delete-spec",
        "Delete a Vector Assist specification",
        [ParameterManifest(name="spec_id", type="string", description="Spec ID", required=True)],
        False,
    ),
    (
        "vector-assist-generate-query",
        "Generate a query using Vector Assist",
        [
            ParameterManifest(
                name="question",
                type="string",
                description="Natural language question",
                required=True,
            )
        ],
        True,
    ),
    (
        "vector-assist-improve-query-recall",
        "Improve query recall using Vector Assist",
        [
            ParameterManifest(
                name="query", type="string", description="Query to improve", required=True
            )
        ],
        True,
    ),
    (
        "vector-assist-apply-spec",
        "Apply a Vector Assist specification",
        [
            ParameterManifest(
                name="spec_id", type="string", description="Spec ID to apply", required=True
            )
        ],
        False,
    ),
]


class VectorAssistGenericTool(BaseTool):
    """Generic Vector Assist tool — dispatches to CloudSQLPGSource SQL execution."""

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        tool_type: str,
        param_defs: list[ParameterManifest],
        read_only: bool,
    ):
        """初始化工具配置。"""
        ann = (
            ToolAnnotations(read_only_hint=True)
            if read_only
            else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        )
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, CloudSQLPGSource
        )
        try:
            # Vector Assist operations are SQL-driven; dispatch to execute_sql
            sql = params.get("sql", params.get("query", params.get("question", "")))
            if sql:
                rows = await source.execute_sql(sql)
                return {"rows": rows, "rowCount": len(rows)}
            return {"result": "ok"}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


def _make_va_tool_config(
    tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool
):
    """构造Cloud SQL Postgres工具配置。"""

    @register_tool(tool_type)
    @dataclass
    class _VAToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _VAToolConfig:
            """从字典创建配置实例。"""
            return cls(
                _name=name,
                source=data.get("source", ""),
                description=data.get("description", description),
            )

        async def initialize(self) -> VectorAssistGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return VectorAssistGenericTool(
                cfg=cfg,
                source_name=self.source,
                tool_type=tool_type,
                param_defs=param_defs,
                read_only=read_only,
            )

    _VAToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _VAToolConfig.__qualname__ = _VAToolConfig.__name__
    return _VAToolConfig


for _tool_type, _desc, _params, _ro in _VA_TOOLS:
    _make_va_tool_config(_tool_type, _desc, _params, _ro)
