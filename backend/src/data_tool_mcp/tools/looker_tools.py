"""Looker tools — 40+ tools for Looker BI platform management and querying.

Maps to Go: internal/tools/looker/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.looker_source import LookerSource
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
# Looker 操作分发表 — 每个 handler 为 async 函数,签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _lk_get_models(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的模型列表。"""
    return {"models": await source.get_lookml_models()}

async def _lk_get_model(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的模型。"""
    return {"model": await source.get_lookml_model(params["model_name"])}

async def _lk_get_explores(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的探索列表。"""
    model = await source.get_lookml_model(params["model_name"])
    return {"explores": model.get("explores", [])}

async def _lk_get_explore(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的探索。"""
    return {"explore": await source.get_lookml_explore(params["model_name"], params["explore_name"])}

async def _lk_create_query(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """创建Looker的查询。"""
    return {"query": await source.create_query(params["body"])}

async def _lk_run_query(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """运行Looker的查询。"""
    return {"result": await source.run_query(params["query_id"], params.get("result_format", "json"))}

async def _lk_run_inline_query(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """运行Looker的内联查询。"""
    return {"result": await source.run_inline_query(params.get("result_format", "json"), params["body"])}

async def _lk_get_looks(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的Look 列表。"""
    if "look_id" in params:
        return {"looks": await source.get_look(params.get("look_id", 0))}
    return {"looks": []}

async def _lk_get_look(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的Look。"""
    return {"look": await source.get_look(params["look_id"])}

async def _lk_run_look(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """运行Looker的Look。"""
    return {"result": await source.run_look(params["look_id"], params.get("result_format", "json"))}

async def _lk_get_dashboards(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的仪表板列表。"""
    return {"dashboards": await source.get_all_dashboards()}

async def _lk_get_dashboard(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的仪表板。"""
    return {"dashboard": await source.get_dashboard(params["dashboard_id"])}

async def _lk_run_dashboard(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """运行Looker的仪表板。"""
    return {"dashboard": await source.get_dashboard(params["dashboard_id"])}

async def _lk_get_connections(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的连接列表。"""
    return {"connections": await source.get_all_connections()}

async def _lk_get_users(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的用户列表。"""
    return {"users": await source.get_all_users()}

async def _lk_get_folders(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的文件夹列表。"""
    return {"folders": await source.get_all_folders()}

async def _lk_get_projects(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Looker的项目列表。"""
    return {"projects": await source.get_all_projects()}

async def _lk_fallback(source: LookerSource, params: dict[str, Any]) -> dict[str, Any]:
    """Looker 工具兜底处理。"""
    return {"tool_type": params.get("__tool_type", ""), "params": {k: v for k, v in params.items() if k != "__tool_type"}, "note": "SDK method not yet mapped in LookerSource"}


_LOOKER_DISPATCH: dict[str, Any] = {
    "looker-get-models": _lk_get_models,
    "looker-get-model": _lk_get_model,
    "looker-get-explores": _lk_get_explores,
    "looker-get-explore": _lk_get_explore,
    "looker-create-query": _lk_create_query,
    "looker-run-query": _lk_run_query,
    "looker-run-inline-query": _lk_run_inline_query,
    "looker-get-looks": _lk_get_looks,
    "looker-get-look": _lk_get_look,
    "looker-run-look": _lk_run_look,
    "looker-get-dashboards": _lk_get_dashboards,
    "looker-get-dashboard": _lk_get_dashboard,
    "looker-run-dashboard": _lk_run_dashboard,
    "looker-get-connections": _lk_get_connections,
    "looker-get-users": _lk_get_users,
    "looker-get-folders": _lk_get_folders,
    "looker-get-projects": _lk_get_projects,
}


# ---------------------------------------------------------------------------
# Generic Looker tool
# ---------------------------------------------------------------------------

class LookerGenericTool(BaseTool):
    """Generic Looker tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        """初始化工具配置。"""
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, LookerSource)
        try:
            handler = _LOOKER_DISPATCH.get(self._tool_type)
            if handler is not None:
                return await handler(source, params)
            return await _lk_fallback(source, {"__tool_type": self._tool_type, **params})
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


# ---------------------------------------------------------------------------
# Tool definitions — grouped by category
# ---------------------------------------------------------------------------

_LOOKER_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    # LookML (4)
    ("looker-get-models", "List all LookML models", [], True),
    ("looker-get-model", "Get a LookML model",
     [ParameterManifest(name="model_name", type="string", description="Model name", required=True)], True),
    ("looker-get-explores", "List explores in a LookML model",
     [ParameterManifest(name="model_name", type="string", description="Model name", required=True)], True),
    ("looker-get-explore", "Get a LookML explore",
     [ParameterManifest(name="model_name", type="string", description="Model name", required=True),
      ParameterManifest(name="explore_name", type="string", description="Explore name", required=True)], True),

    # Query (3)
    ("looker-create-query", "Create a Looker query",
     [ParameterManifest(name="body", type="object", description="Query body", required=True)], True),
    ("looker-run-query", "Run a Looker query",
     [ParameterManifest(name="query_id", type="integer", description="Query ID", required=True),
      ParameterManifest(name="result_format", type="string", description="Result format", required=False)], True),
    ("looker-run-inline-query", "Run an inline Looker query",
     [ParameterManifest(name="body", type="object", description="Query body", required=True),
      ParameterManifest(name="result_format", type="string", description="Result format", required=False)], True),

    # Looks (3)
    ("looker-get-look", "Get a Looker look",
     [ParameterManifest(name="look_id", type="integer", description="Look ID", required=True)], True),
    ("looker-get-looks", "List all Looker looks", [], True),
    ("looker-run-look", "Run a Looker look",
     [ParameterManifest(name="look_id", type="integer", description="Look ID", required=True),
      ParameterManifest(name="result_format", type="string", description="Result format", required=False)], True),

    # Dashboards (3)
    ("looker-get-dashboards", "List all Looker dashboards", [], True),
    ("looker-get-dashboard", "Get a Looker dashboard",
     [ParameterManifest(name="dashboard_id", type="string", description="Dashboard ID", required=True)], True),
    ("looker-run-dashboard", "Run a Looker dashboard",
     [ParameterManifest(name="dashboard_id", type="string", description="Dashboard ID", required=True)], True),

    # Connections (6)
    ("looker-get-connections", "List all Looker connections", [], True),
    ("looker-get-connection-databases", "List databases in a Looker connection",
     [ParameterManifest(name="connection_name", type="string", description="Connection name", required=True)], True),
    ("looker-get-connection-schemas", "List schemas in a Looker connection",
     [ParameterManifest(name="connection_name", type="string", description="Connection name", required=True)], True),
    ("looker-get-connection-tables", "List tables in a Looker connection schema",
     [ParameterManifest(name="connection_name", type="string", description="Connection name", required=True),
      ParameterManifest(name="schema", type="string", description="Schema name", required=False)], True),
    ("looker-get-connection-table-columns", "List columns of a table in a Looker connection",
     [ParameterManifest(name="connection_name", type="string", description="Connection name", required=True),
      ParameterManifest(name="table", type="string", description="Table name", required=True)], True),

    # Explore metadata (4)
    ("looker-get-dimensions", "Get dimensions for a LookML explore",
     [ParameterManifest(name="model_name", type="string", description="Model name", required=True),
      ParameterManifest(name="explore_name", type="string", description="Explore name", required=True)], True),
    ("looker-get-measures", "Get measures for a LookML explore",
     [ParameterManifest(name="model_name", type="string", description="Model name", required=True),
      ParameterManifest(name="explore_name", type="string", description="Explore name", required=True)], True),
    ("looker-get-filters", "Get filters for a LookML explore",
     [ParameterManifest(name="model_name", type="string", description="Model name", required=True),
      ParameterManifest(name="explore_name", type="string", description="Explore name", required=True)], True),
    ("looker-get-parameters", "Get parameters for a LookML explore",
     [ParameterManifest(name="model_name", type="string", description="Model name", required=True),
      ParameterManifest(name="explore_name", type="string", description="Explore name", required=True)], True),

    # Projects (7)
    ("looker-get-projects", "List all Looker projects", [], True),
    ("looker-get-project-files", "List files in a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True)], True),
    ("looker-get-project-file", "Get a file from a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="file_id", type="string", description="File ID", required=True)], True),
    ("looker-get-project-directories", "List directories in a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True)], True),
    ("looker-create-project-file", "Create a file in a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="body", type="object", description="File body", required=True)], False),
    ("looker-update-project-file", "Update a file in a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="file_id", type="string", description="File ID", required=True),
      ParameterManifest(name="body", type="object", description="File body", required=True)], False),
    ("looker-delete-project-file", "Delete a file from a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="file_id", type="string", description="File ID", required=True)], False),
    ("looker-create-project-directory", "Create a directory in a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="directory_name", type="string", description="Directory name", required=True)], False),
    ("looker-delete-project-directory", "Delete a directory from a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="directory_name", type="string", description="Directory name", required=True)], False),

    # Git (5)
    ("looker-get-git-branch", "Get the current Git branch",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True)], True),
    ("looker-list-git-branches", "List all Git branches",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True)], True),
    ("looker-create-git-branch", "Create a Git branch",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="body", type="object", description="Branch body", required=True)], False),
    ("looker-switch-git-branch", "Switch to a Git branch",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="branch_name", type="string", description="Branch name", required=True)], False),
    ("looker-delete-git-branch", "Delete a Git branch",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True),
      ParameterManifest(name="branch_name", type="string", description="Branch name", required=True)], False),

    # Dev mode + validation (3)
    ("looker-dev-mode", "Toggle Looker dev mode",
     [ParameterManifest(name="enabled", type="boolean", description="Enable dev mode", required=True)], False),
    ("looker-validate-project", "Validate a Looker project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True)], True),
    ("looker-run-lookml-tests", "Run LookML tests",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True)], True),
    ("looker-get-lookml-tests", "Get LookML tests for a project",
     [ParameterManifest(name="project_id", type="string", description="Project ID", required=True)], True),

    # Content creation (5)
    ("looker-make-look", "Create a Looker look",
     [ParameterManifest(name="body", type="object", description="Look body", required=True)], False),
    ("looker-make-dashboard", "Create a Looker dashboard",
     [ParameterManifest(name="body", type="object", description="Dashboard body", required=True)], False),
    ("looker-add-dashboard-element", "Add an element to a Looker dashboard",
     [ParameterManifest(name="dashboard_id", type="string", description="Dashboard ID", required=True),
      ParameterManifest(name="body", type="object", description="Element body", required=True)], False),
    ("looker-add-dashboard-filter", "Add a filter to a Looker dashboard",
     [ParameterManifest(name="dashboard_id", type="string", description="Dashboard ID", required=True),
      ParameterManifest(name="body", type="object", description="Filter body", required=True)], False),
    ("looker-generate-embed-url", "Generate an embed URL for a Looker dashboard",
     [ParameterManifest(name="dashboard_id", type="string", description="Dashboard ID", required=True)], True),

    # Health (3)
    ("looker-health-analyze", "Analyze Looker health", [], True),
    ("looker-health-pulse", "Check Looker health pulse", [], True),
    ("looker-health-vacuum", "Run Looker health vacuum", [], True),

    # Conversational analytics + agents (5)
    ("looker-conversational-analytics", "Run conversational analytics in Looker",
     [ParameterManifest(name="question", type="string", description="Natural language question", required=True)], True),
    ("looker-create-agent", "Create a Looker agent",
     [ParameterManifest(name="body", type="object", description="Agent body", required=True)], False),
    ("looker-get-agent", "Get a Looker agent",
     [ParameterManifest(name="agent_id", type="string", description="Agent ID", required=True)], True),
    ("looker-list-agents", "List all Looker agents", [], True),
    ("looker-update-agent", "Update a Looker agent",
     [ParameterManifest(name="agent_id", type="string", description="Agent ID", required=True),
      ParameterManifest(name="body", type="object", description="Agent body", required=True)], False),
    ("looker-delete-agent", "Delete a Looker agent",
     [ParameterManifest(name="agent_id", type="string", description="Agent ID", required=True)], False),

    # Misc (3)
    ("looker-get-users", "List all Looker users", [], True),
    ("looker-get-folders", "List all Looker folders", [], True),
    ("looker-create-view-from-table", "Create a LookML view from a database table",
     [ParameterManifest(name="connection_name", type="string", description="Connection name", required=True),
      ParameterManifest(name="table_name", type="string", description="Table name", required=True)], False),
    ("looker-query-sql", "Get the SQL for a Looker query",
     [ParameterManifest(name="query_id", type="integer", description="Query ID", required=True)], True),
    ("looker-query-url", "Get the URL for a Looker query",
     [ParameterManifest(name="query_id", type="integer", description="Query ID", required=True)], True),
    ("looker-query", "Run a Looker query by ID",
     [ParameterManifest(name="query_id", type="integer", description="Query ID", required=True),
      ParameterManifest(name="result_format", type="string", description="Result format", required=False)], True),
]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_looker_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    """构造Looker工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _LookerToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _LookerToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> LookerGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return LookerGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _LookerToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _LookerToolConfig.__qualname__ = _LookerToolConfig.__name__
    return _LookerToolConfig


for _tool_type, _desc, _params, _ro in _LOOKER_TOOLS:
    _make_looker_tool_config(_tool_type, _desc, _params, _ro)
