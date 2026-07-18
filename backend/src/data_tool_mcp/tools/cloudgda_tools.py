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
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# cloud-gemini-data-analytics-query (from cloudgda/)
# ---------------------------------------------------------------------------


class CloudGDAQueryTool(BaseTool):
    """Query using Cloud Gemini Data Analytics."""

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
            source_provider, self._source_name, self.name, CloudGDASource
        )
        try:
            query = params.get("query", "")
            result = await source.query(query)
            return {"result": result}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="query", type="string", description="Natural language query", required=True
                ),
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
        """返回工具类型标识符。"""
        return "cloud-gemini-data-analytics-query"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudGDAQueryToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "使用 Cloud Gemini Data Analytics 进行查询"),
        )

    async def initialize(self) -> CloudGDAQueryTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return CloudGDAQueryTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# Conversational Analytics tools (from conversationalanalytics/)
# ---------------------------------------------------------------------------


async def _ca_query(source: CloudGDASource, params: dict[str, Any]) -> dict[str, Any]:
    """执行 Cloud GDA 查询。"""
    return {"result": await source.query(params.get("query", ""))}


async def _ca_list_agents(source: CloudGDASource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Cloud GDA的代理列表。"""
    return {"data_agents": await source.list_accessible_data_agents()}


async def _ca_get_agent_info(source: CloudGDASource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud GDA的代理信息。"""
    return {"data_agent": await source.get_data_agent_info(params["agent_id"])}


async def _ca_ask_agent(source: CloudGDASource, params: dict[str, Any]) -> dict[str, Any]:
    """向 Cloud GDA 代理提问。"""
    return {"result": await source.ask_data_agent(params["agent_id"], params["question"])}


_CA_DISPATCH: dict[str, Any] = {
    "conversational-analytics-query": _ca_query,
    "conversational-analytics-list-accessible-data-agents": _ca_list_agents,
    "conversational-analytics-get-data-agent-info": _ca_get_agent_info,
    "conversational-analytics-ask-data-agent": _ca_ask_agent,
}


async def _ca_dispatch(
    tool_type: str, source: CloudGDASource, params: dict[str, Any]
) -> dict[str, Any]:
    """分发 Cloud GDA 请求。"""
    handler = _CA_DISPATCH.get(tool_type)
    if handler is None:
        raise ValueError(f"unknown Conversational Analytics tool type: {tool_type}")
    return await handler(source, params)


class ConversationalAnalyticsGenericTool(BaseTool):
    """Generic Conversational Analytics tool that dispatches based on tool type."""

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
            source_provider, self._source_name, self.name, CloudGDASource
        )
        try:
            return await _ca_dispatch(self._tool_type, source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


_CA_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    (
        "conversational-analytics-query",
        "Query using conversational analytics",
        [
            ParameterManifest(
                name="query", type="string", description="Natural language query", required=True
            )
        ],
        True,
    ),
    (
        "conversational-analytics-list-accessible-data-agents",
        "List accessible data agents",
        [],
        True,
    ),
    (
        "conversational-analytics-get-data-agent-info",
        "Get data agent information",
        [
            ParameterManifest(
                name="agent_id", type="string", description="Data agent ID", required=True
            )
        ],
        True,
    ),
    (
        "conversational-analytics-ask-data-agent",
        "Ask a question to a data agent",
        [
            ParameterManifest(
                name="agent_id", type="string", description="Data agent ID", required=True
            ),
            ParameterManifest(
                name="question", type="string", description="Question to ask", required=True
            ),
        ],
        True,
    ),
]


def _make_ca_tool_config(
    tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool
):
    """构造Cloud GDA工具配置。"""

    @register_tool(tool_type)
    @dataclass
    class _CAToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _CAToolConfig:
            """从字典创建配置实例。"""
            return cls(
                _name=name,
                source=data.get("source", ""),
                description=data.get("description", description),
            )

        async def initialize(self) -> ConversationalAnalyticsGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return ConversationalAnalyticsGenericTool(
                cfg=cfg,
                source_name=self.source,
                tool_type=tool_type,
                param_defs=param_defs,
                read_only=read_only,
            )

    _CAToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _CAToolConfig.__qualname__ = _CAToolConfig.__name__
    return _CAToolConfig


for _tool_type, _desc, _params, _ro in _CA_TOOLS:
    _make_ca_tool_config(_tool_type, _desc, _params, _ro)
