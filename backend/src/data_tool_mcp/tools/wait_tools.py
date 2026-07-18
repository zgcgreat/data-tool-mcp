"""Wait utility tool — pauses execution for a specified duration.

Maps to Go: internal/tools/utility/wait/ (registered as "wait")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.tools.base import (
    BaseTool,
    ConfigBase,
    ParameterManifest,
    ToolAnnotations,
    ToolConfig,
    ToolManifest,
    register_tool,
)


def _validate_wait_seconds(seconds: Any) -> None:
    """校验 wait 工具的 seconds 参数:必须为非负数。"""
    if not isinstance(seconds, (int, float)):
        raise TypeError(f"'seconds' must be a number, got {type(seconds).__name__}")
    if seconds < 0:
        raise ValueError("wait seconds must be non-negative")


class WaitTool(BaseTool):
    """Wait for a specified number of seconds.

    In Go, this is registered as a single tool type "wait".
    Used primarily in workflow/pipeline scenarios where a delay is needed
    between operations (e.g., waiting for a resource to be ready).
    """

    def __init__(self, cfg: ConfigBase):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: Any = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        seconds = params.get("seconds", 0)
        _validate_wait_seconds(seconds)
        if seconds > 0:
            await asyncio.sleep(seconds)
        return {"waited": seconds}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(
                    name="seconds",
                    type="integer",
                    description="Number of seconds to wait",
                    required=True,
                ),
            ],
            auth_required=self.auth_required,
        )


@register_tool("wait")
@dataclass
class WaitToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    description: str = "等待指定秒数"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "wait"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> WaitToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, description=data.get("description", "等待指定秒数"))

    async def initialize(self) -> WaitTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return WaitTool(cfg=cfg)
