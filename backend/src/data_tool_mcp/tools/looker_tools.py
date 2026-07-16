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
    register_tool,
)


async def _get_looker_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> LookerSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, LookerSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Looker source")
    return source


# ---------------------------------------------------------------------------
# Generic Looker tool
# ---------------------------------------------------------------------------

class LookerGenericTool(BaseTool):
    """Generic Looker tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_looker_source(source_provider, self._source_name, self.name)
        try:
            tt = self._tool_type

            # LookML
            if tt == "looker-get-models":
                models = await source.get_lookml_models()
                return {"models": models}
            elif tt == "looker-get-model":
                return {"model": await source.get_lookml_model(params["model_name"])}
            elif tt == "looker-get-explores":
                model = await source.get_lookml_model(params["model_name"])
                return {"explores": model.get("explores", [])}
            elif tt == "looker-get-explore":
                return {"explore": await source.get_lookml_explore(params["model_name"], params["explore_name"])}

            # Query
            elif tt == "looker-create-query":
                return {"query": await source.create_query(params["body"])}
            elif tt == "looker-run-query":
                result = await source.run_query(params["query_id"], params.get("result_format", "json"))
                return {"result": result}
            elif tt == "looker-run-inline-query":
                result = await source.run_inline_query(params.get("result_format", "json"), params["body"])
                return {"result": result}

            # Looks
            elif tt == "looker-get-looks":
                return {"looks": await source.get_look(params.get("look_id", 0))} if "look_id" in params else {"looks": []}
            elif tt == "looker-get-look":
                return {"look": await source.get_look(params["look_id"])}
            elif tt == "looker-run-look":
                result = await source.run_look(params["look_id"], params.get("result_format", "json"))
                return {"result": result}

            # Dashboards
            elif tt == "looker-get-dashboards":
                dashboards = await source.get_all_dashboards()
                return {"dashboards": dashboards}
            elif tt == "looker-get-dashboard":
                return {"dashboard": await source.get_dashboard(params["dashboard_id"])}
            elif tt == "looker-run-dashboard":
                return {"dashboard": await source.get_dashboard(params["dashboard_id"])}

            # Connections
            elif tt == "looker-get-connections":
                connections = await source.get_all_connections()
                return {"connections": connections}

            # Users
            elif tt == "looker-get-users":
                users = await source.get_all_users()
                return {"users": users}

            # Folders
            elif tt == "looker-get-folders":
                folders = await source.get_all_folders()
                return {"folders": folders}

            # Projects
            elif tt == "looker-get-projects":
                projects = await source.get_all_projects()
                return {"projects": projects}

            # Fallback for tools that need more SDK methods
            else:
                return {"tool_type": tt, "params": params, "note": "SDK method not yet mapped in LookerSource"}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
    @register_tool(tool_type)
    @dataclass
    class _LookerToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _LookerToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> LookerGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return LookerGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _LookerToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _LookerToolConfig.__qualname__ = _LookerToolConfig.__name__
    return _LookerToolConfig


for _tool_type, _desc, _params, _ro in _LOOKER_TOOLS:
    _make_looker_tool_config(_tool_type, _desc, _params, _ro)
