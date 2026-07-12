"""Dataplex tools — 20 tools for Dataplex data management.

Maps to Go: internal/tools/dataplex/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.dataplex_source import DataplexSource
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


def _get_dataplex_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> DataplexSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, DataplexSource):
        raise TypeError(f"source {source_name!r} is not a Dataplex source")
    return source


class DataplexGenericTool(BaseTool):
    """Generic Dataplex tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_dataplex_source(source_provider, self._source_name, self.name)
        tt = self._tool_type

        # Lakes
        if tt == "dataplex-list-lakes":
            return {"lakes": await source.list_lakes()}
        elif tt == "dataplex-get-lake":
            return {"lake": await source.get_lake(params["lake_id"])}
        elif tt == "dataplex-create-lake":
            return {"result": await source.create_lake(params["lake_id"], params.get("lake", {}))}
        elif tt == "dataplex-delete-lake":
            return {"result": await source.delete_lake(params["lake_id"])}

        # Zones
        elif tt == "dataplex-list-zones":
            return {"zones": await source.list_zones(params["lake_id"])}
        elif tt == "dataplex-get-zone":
            return {"zone": await source.get_zone(params["lake_id"], params["zone_id"])}
        elif tt == "dataplex-create-zone":
            return {"result": await source.create_zone(params["lake_id"], params["zone_id"], params.get("zone", {}))}
        elif tt == "dataplex-delete-zone":
            return {"result": await source.delete_zone(params["lake_id"], params["zone_id"])}

        # Assets
        elif tt == "dataplex-list-assets":
            return {"assets": await source.list_assets(params["lake_id"], params["zone_id"])}
        elif tt == "dataplex-get-asset":
            return {"asset": await source.get_asset(params["lake_id"], params["zone_id"], params["asset_id"])}
        elif tt == "dataplex-create-asset":
            return {"result": await source.create_asset(params["lake_id"], params["zone_id"], params["asset_id"], params.get("asset", {}))}
        elif tt == "dataplex-delete-asset":
            return {"result": await source.delete_asset(params["lake_id"], params["zone_id"], params["asset_id"])}

        # Tasks
        elif tt == "dataplex-list-tasks":
            return {"tasks": await source.list_tasks(params["lake_id"])}
        elif tt == "dataplex-get-task":
            return {"task": await source.get_task(params["lake_id"], params["task_id"])}
        elif tt == "dataplex-create-task":
            return {"result": await source.create_task(params["lake_id"], params["task_id"], params.get("task", {}))}
        elif tt == "dataplex-delete-task":
            return {"result": await source.delete_task(params["lake_id"], params["task_id"])}

        # Discovery / quality / insights (placeholder — SDK methods not yet in source)
        elif tt in ("dataplex-discover-metadata", "dataplex-get-discovery-results",
                     "dataplex-check-data-quality", "dataplex-get-data-quality-results",
                     "dataplex-search-dq-scans",
                     "dataplex-generate-data-profile", "dataplex-get-data-profile",
                     "dataplex-generate-data-insights", "dataplex-get-data-insights",
                     "dataplex-get-data-product", "dataplex-list-data-products",
                     "dataplex-list-data-assets",
                     "dataplex-lookup-entry", "dataplex-lookup-context",
                     "dataplex-search-entries", "dataplex-search-aspect-types",
                     "dataplex-get-operation", "dataplex-get-run-status"):
            return {"tool_type": tt, "note": "Full SDK integration pending"}

        else:
            raise ValueError(f"unknown Dataplex tool type: {tt}")

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_DATAPLEX_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    # Lakes (4)
    ("dataplex-list-lakes", "List all Dataplex lakes", [], True),
    ("dataplex-get-lake", "Get a Dataplex lake",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-create-lake", "Create a Dataplex lake",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="lake", type="object", description="Lake configuration", required=False)], False),
    ("dataplex-delete-lake", "Delete a Dataplex lake",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], False),

    # Zones (4)
    ("dataplex-list-zones", "List zones in a Dataplex lake",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-get-zone", "Get a Dataplex zone",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="zone_id", type="string", description="Zone ID", required=True)], True),
    ("dataplex-create-zone", "Create a Dataplex zone",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="zone_id", type="string", description="Zone ID", required=True),
      ParameterManifest(name="zone", type="object", description="Zone configuration", required=False)], False),
    ("dataplex-delete-zone", "Delete a Dataplex zone",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="zone_id", type="string", description="Zone ID", required=True)], False),

    # Assets (4)
    ("dataplex-list-assets", "List assets in a Dataplex zone",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="zone_id", type="string", description="Zone ID", required=True)], True),
    ("dataplex-get-asset", "Get a Dataplex asset",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="zone_id", type="string", description="Zone ID", required=True),
      ParameterManifest(name="asset_id", type="string", description="Asset ID", required=True)], True),
    ("dataplex-create-asset", "Create a Dataplex asset",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="zone_id", type="string", description="Zone ID", required=True),
      ParameterManifest(name="asset_id", type="string", description="Asset ID", required=True),
      ParameterManifest(name="asset", type="object", description="Asset configuration", required=False)], False),
    ("dataplex-delete-asset", "Delete a Dataplex asset",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="zone_id", type="string", description="Zone ID", required=True),
      ParameterManifest(name="asset_id", type="string", description="Asset ID", required=True)], False),

    # Tasks (4)
    ("dataplex-list-tasks", "List tasks in a Dataplex lake",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-get-task", "Get a Dataplex task",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="task_id", type="string", description="Task ID", required=True)], True),
    ("dataplex-create-task", "Create a Dataplex task",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="task_id", type="string", description="Task ID", required=True),
      ParameterManifest(name="task", type="object", description="Task configuration", required=False)], False),
    ("dataplex-delete-task", "Delete a Dataplex task",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True),
      ParameterManifest(name="task_id", type="string", description="Task ID", required=True)], False),

    # Discovery / Quality / Insights (12)
    ("dataplex-discover-metadata", "Discover metadata in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-get-discovery-results", "Get discovery results in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-check-data-quality", "Check data quality in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-get-data-quality-results", "Get data quality results in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-search-dq-scans", "Search DQ scans in Dataplex",
     [ParameterManifest(name="query", type="string", description="Search query", required=False)], True),
    ("dataplex-generate-data-profile", "Generate a data profile in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], False),
    ("dataplex-get-data-profile", "Get a data profile in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-generate-data-insights", "Generate data insights in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], False),
    ("dataplex-get-data-insights", "Get data insights in Dataplex",
     [ParameterManifest(name="lake_id", type="string", description="Lake ID", required=True)], True),
    ("dataplex-get-data-product", "Get a data product in Dataplex",
     [ParameterManifest(name="product_id", type="string", description="Data product ID", required=True)], True),
    ("dataplex-list-data-products", "List data products in Dataplex", [], True),
    ("dataplex-list-data-assets", "List data assets in Dataplex", [], True),

    # Catalog / lineage (6)
    ("dataplex-lookup-entry", "Look up a catalog entry",
     [ParameterManifest(name="entry", type="string", description="Entry name", required=True)], True),
    ("dataplex-lookup-context", "Look up a catalog context",
     [ParameterManifest(name="context", type="string", description="Context name", required=True)], True),
    ("dataplex-search-entries", "Search catalog entries",
     [ParameterManifest(name="query", type="string", description="Search query", required=True)], True),
    ("dataplex-search-aspect-types", "Search aspect types",
     [ParameterManifest(name="query", type="string", description="Search query", required=False)], True),
    ("dataplex-get-operation", "Get a Dataplex operation",
     [ParameterManifest(name="operation_name", type="string", description="Operation name", required=True)], True),
    ("dataplex-get-run-status", "Get a Dataplex run status",
     [ParameterManifest(name="run_id", type="string", description="Run ID", required=True)], True),
]


def _make_dataplex_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    @register_tool(tool_type)
    @dataclass
    class _DataplexToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _DataplexToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> DataplexGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return DataplexGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _DataplexToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _DataplexToolConfig.__qualname__ = _DataplexToolConfig.__name__
    return _DataplexToolConfig


for _tool_type, _desc, _params, _ro in _DATAPLEX_TOOLS:
    _make_dataplex_tool_config(_tool_type, _desc, _params, _ro)
