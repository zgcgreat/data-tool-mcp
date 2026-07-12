"""HTTP tool — single unified tool for generic HTTP requests.

Maps to Go: internal/tools/http/ (registered as single tool "http")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.http_source import HTTPSource
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


def _get_http_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> HTTPSource:
    if source_provider is None:
        raise ValueError(
            f"tool {tool_name!r} requires an 'http' source but no source provider is available. "
            f"Ensure the tool configuration specifies a valid 'source' field pointing to an "
            f"http-type source definition in the YAML config."
        )
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(
            f"source {source_name!r} not found for tool {tool_name!r}. "
            f"Available sources: {list(source_provider.get_source.__self__._sources.keys()) if hasattr(source_provider, '_sources') else 'unknown'}. "
            f"Ensure the 'source' field in the tool config matches a defined source name."
        )
    if not isinstance(source, HTTPSource):
        raise TypeError(
            f"source {source_name!r} is not an HTTP source (got {type(source).__name__}). "
            f"HTTP tools require a source of type 'http'."
        )
    return source


class HTTPTool(BaseTool):
    """Make an HTTP request via a configured HTTP source.

    In Go, this is registered as a single tool type "http".
    """

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_http_source(source_provider, self._source_name, self.name)
        return await source.make_request(
            method=params.get("method"),
            path=params.get("path", ""),
            headers=params.get("headers"),
            params=params.get("params"),
            body=params.get("body"),
        )

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="method", type="string", description="HTTP method (GET, POST, PUT, DELETE, etc.)", required=False),
                ParameterManifest(name="path", type="string", description="URL path", required=False),
                ParameterManifest(name="headers", type="object", description="Request headers", required=False),
                ParameterManifest(name="params", type="object", description="Query parameters", required=False),
                ParameterManifest(name="body", type="object", description="Request body", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("http")
@dataclass
class HTTPToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "发起 HTTP 请求"

    @property
    def tool_type(self) -> str:
        return "http"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HTTPToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "发起 HTTP 请求"))

    async def initialize(self) -> HTTPTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return HTTPTool(cfg=cfg, source_name=self.source)
