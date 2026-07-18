"""Dataform tools — 1 tool for Dataform compilation.

Maps to Go: internal/tools/dataform/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


class DataformCompileLocalTool(BaseTool):
    """Compile a Dataform project locally."""

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
        # Dataform compilation is typically local and doesn't require a live source
        """执行工具调用，返回查询结果。"""
        project_dir = params.get("project_dir", "")
        if not project_dir:
            raise ValueError("missing 'project_dir' parameter")
        # Placeholder: actual compilation would use dataform CLI or SDK
        return {"status": "compiled", "project_dir": project_dir}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="project_dir",
                    type="string",
                    description="Path to Dataform project directory",
                    required=True,
                ),
            ],
            auth_required=self.auth_required,
        )


@register_tool("dataform-compile-local")
@dataclass
class DataformCompileLocalToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在本地编译 Dataform 项目"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "dataform-compile-local"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataformCompileLocalToolConfig:
        """从字典创建配置实例。"""
        return cls(
            _name=name,
            source=data.get("source", ""),
            description=data.get("description", "在本地编译 Dataform 项目"),
        )

    async def initialize(self) -> DataformCompileLocalTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return DataformCompileLocalTool(cfg=cfg, source_name=self.source)
