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


class WaitTool(BaseTool):
    """Wait for a specified number of seconds.

    In Go, this is registered as a single tool type "wait".
    Used primarily in workflow/pipeline scenarios where a delay is needed
    between operations (e.g., waiting for a resource to be ready).
    """

    def __init__(self, cfg: ConfigBase):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: Any = None,
        access_token: str = "",
    ) -> Any:
        seconds = params.get("seconds", 0)
        # Type validation — reject non-numeric values early
        if not isinstance(seconds, (int, float)):
            raise TypeError(f"'seconds' must be a number, got {type(seconds).__name__}")
        if seconds < 0:
            raise ValueError("wait seconds must be non-negative")
        if seconds > 0:
            await asyncio.sleep(seconds)
        return {"waited": seconds}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="seconds", type="integer", description="Number of seconds to wait", required=True),
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
        return "wait"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> WaitToolConfig:
        return cls(_name=name, description=data.get("description", "等待指定秒数"))

    async def initialize(self) -> WaitTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return WaitTool(cfg=cfg)
