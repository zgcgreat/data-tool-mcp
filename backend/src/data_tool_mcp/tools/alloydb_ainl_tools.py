"""AlloyDB AI NL tool — execute natural language queries via AlloyDB AI.

Maps to Go: internal/tools/alloydb-ai-nl/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.alloydbpg import AlloyDBPGSource
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


async def _get_alloydb_pg_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> AlloyDBPGSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, AlloyDBPGSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not an AlloyDB PostgreSQL source")
    return source


# ---------------------------------------------------------------------------
# AlloyDB AI NL tool
# ---------------------------------------------------------------------------

class AlloyDBAINLTool(BaseTool):
    """Execute a natural language query on AlloyDB using the alloydb_ai_nl extension."""

    def __init__(self, cfg: ConfigBase, source_name: str, nl_config: str, nl_config_parameters: dict[str, str] | None = None):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name
        self._nl_config = nl_config
        self._nl_config_parameters = nl_config_parameters

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = await _get_alloydb_pg_source(source_provider, self._source_name, self.name)
        try:
            question = params.get("question", "")
            if not question:
                raise ValueError("missing 'question' parameter")

            if self._nl_config_parameters:
                param_names = list(self._nl_config_parameters.keys())
                param_values = list(self._nl_config_parameters.values())
                names_literal = ", ".join(f"'{n}'" for n in param_names)
                values_literal = ", ".join(f"'{v}'" for v in param_values)
                sql = (
                    f"SELECT alloydb_ai_nl.execute_nl_query("
                    f"nl_question => :question, "
                    f"nl_config_id => :nl_config_id, "
                    f"param_names => ARRAY[{names_literal}], "
                    f"param_values => ARRAY[{values_literal}])"
                )
            else:
                sql = (
                    "SELECT alloydb_ai_nl.execute_nl_query("
                    "nl_question => :question, "
                    "nl_config_id => :nl_config_id)"
                )

            rows = await source.execute_sql(sql, {"question": question, "nl_config_id": self._nl_config})
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="question", type="string", description="Natural language question to ask AlloyDB AI", required=True),
            ],
            auth_required=self.auth_required,
        )


# ---------------------------------------------------------------------------
# Tool config
# ---------------------------------------------------------------------------

@register_tool("alloydb-ai-nl")
@dataclass
class AlloyDBAINLToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    nlConfig: str = ""
    nlConfigParameters: dict[str, str] | None = None
    description: str = "使用 alloydb_ai_nl 扩展在 AlloyDB 上执行自然语言查询"

    @property
    def tool_type(self) -> str:
        return "alloydb-ai-nl"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AlloyDBAINLToolConfig:
        return cls(
            _name=name,
            source=data.get("source", ""),
            nlConfig=data.get("nlConfig", ""),
            nlConfigParameters=data.get("nlConfigParameters"),
            description=data.get("description", "使用 alloydb_ai_nl 扩展在 AlloyDB 上执行自然语言查询"),
        )

    async def initialize(self) -> AlloyDBAINLTool:
        if not self.source:
            raise ValueError("alloydb-ai-nl tool requires a 'source' configuration")
        if not self.nlConfig:
            raise ValueError("alloydb-ai-nl tool requires a 'nlConfig' configuration")
        cfg = ConfigBase(name=self._name, description=self.description)
        return AlloyDBAINLTool(
            cfg=cfg,
            source_name=self.source,
            nl_config=self.nlConfig,
            nl_config_parameters=self.nlConfigParameters,
        )
