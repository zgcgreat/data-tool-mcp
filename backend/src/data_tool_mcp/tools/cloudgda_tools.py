"""Cloud Gemini Data Analytics / Conversational Analytics tool.

Maps to Go: internal/tools/cloudgda/ (registered as single tool "cloud-gemini-data-analytics-query")
Also maps: internal/tools/conversationalanalytics/ (4 tools registered separately)

In Go, cloudgda registers as "cloud-gemini-data-analytics-query" (single tool),
while conversationalanalytics registers 4 separate tools:
- conversational-analytics-list-accessible-data-agents
- conversational-analytics-get-data-agent-info
- conversational-analytics-ask-data-agent
- conversational-analytics-query

We keep all 5 registrations to match Go exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudgda import CloudGDASource
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


async def _get_gda_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> CloudGDASource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, CloudGDASource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Cloud GDA source")
    return source


# ---------------------------------------------------------------------------
# cloud-gemini-data-analytics-query (from cloudgda/)
# ---------------------------------------------------------------------------

class CloudGDAQueryTool(BaseTool):
    """Query using Cloud Gemini Data Analytics."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_gda_source(source_provider, self._source_name, self.name)
        try:
            query = params.get("query", "")
            result = await source.query(query)
            return {"result": result}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="query", type="string", description="Natural language query", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("cloud-gemini-data-analytics-query")
@dataclass
class CloudGDAQueryToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "使用 Cloud Gemini Data Analytics 进行查询"

    @property
    def tool_type(self) -> str:
        return "cloud-gemini-data-analytics-query"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudGDAQueryToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "使用 Cloud Gemini Data Analytics 进行查询"))

    async def initialize(self) -> CloudGDAQueryTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return CloudGDAQueryTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# Conversational Analytics tools (from conversationalanalytics/)
# ---------------------------------------------------------------------------

class ConversationalAnalyticsGenericTool(BaseTool):
    """Generic Conversational Analytics tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_gda_source(source_provider, self._source_name, self.name)
        try:
            tt = self._tool_type

            if tt == "conversational-analytics-query":
                query = params.get("query", "")
                result = await source.query(query)
                return {"result": result}
            elif tt == "conversational-analytics-list-accessible-data-agents":
                agents = await source.list_accessible_data_agents()
                return {"data_agents": agents}
            elif tt == "conversational-analytics-get-data-agent-info":
                info = await source.get_data_agent_info(params["agent_id"])
                return {"data_agent": info}
            elif tt == "conversational-analytics-ask-data-agent":
                result = await source.ask_data_agent(params["agent_id"], params["question"])
                return {"result": result}
            else:
                raise ValueError(f"unknown Conversational Analytics tool type: {tt}")
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


_CA_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("conversational-analytics-query", "Query using conversational analytics",
     [ParameterManifest(name="query", type="string", description="Natural language query", required=True)], True),
    ("conversational-analytics-list-accessible-data-agents", "List accessible data agents", [], True),
    ("conversational-analytics-get-data-agent-info", "Get data agent information",
     [ParameterManifest(name="agent_id", type="string", description="Data agent ID", required=True)], True),
    ("conversational-analytics-ask-data-agent", "Ask a question to a data agent",
     [ParameterManifest(name="agent_id", type="string", description="Data agent ID", required=True),
      ParameterManifest(name="question", type="string", description="Question to ask", required=True)], True),
]


def _make_ca_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    @register_tool(tool_type)
    @dataclass
    class _CAToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _CAToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> ConversationalAnalyticsGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return ConversationalAnalyticsGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _CAToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _CAToolConfig.__qualname__ = _CAToolConfig.__name__
    return _CAToolConfig


for _tool_type, _desc, _params, _ro in _CA_TOOLS:
    _make_ca_tool_config(_tool_type, _desc, _params, _ro)
