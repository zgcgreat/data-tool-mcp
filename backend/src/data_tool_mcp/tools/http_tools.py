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
    _get_typed_source_async,
    register_tool,
)


class HTTPTool(BaseTool):
    """Make an HTTP request via a configured HTTP source.

    In Go, this is registered as a single tool type "http".
    """

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(
            cfg, annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True)
        )
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, HTTPSource
        )
        try:
            return await source.make_request(
                method=params.get("method"),
                path=params.get("path", ""),
                headers=params.get("headers"),
                params=params.get("params"),
                body=params.get("body"),
            )
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="method",
                    type="string",
                    description="HTTP method (GET, POST, PUT, DELETE, etc.)",
                    required=False,
                ),
                ParameterManifest(
                    name="path", type="string", description="URL path", required=False
                ),
                ParameterManifest(
                    name="headers", type="object", description="Request headers", required=False
                ),
                ParameterManifest(
                    name="params", type="object", description="Query parameters", required=False
                ),
                ParameterManifest(
                    name="body", type="object", description="Request body", required=False
                ),
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
        """返回工具类型标识符。"""
        return "http"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HTTPToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "发起 HTTP 请求"),
        )

    async def initialize(self) -> HTTPTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return HTTPTool(cfg=cfg, source_name=self.source)
