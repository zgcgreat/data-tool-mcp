"""Cloud Gemini Data Analytics source — GCP REST API.

Maps to Go: internal/sources/cloudgda/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class CloudGDASource(Source):
    """Cloud Gemini Data Analytics source using GCP REST API."""

    def __init__(self, name: str, project_id: str, location: str):
        """初始化数据源配置。"""
        self._name = name
        self._project_id = project_id
        self._location = location
        self._parent = f"projects/{project_id}/locations/{location}"

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-gemini-data-analytics"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass

    async def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        """向 GDA REST API 发送带认证的请求。"""
        try:
            import httpx
            from google.auth import default
            from google.auth.transport.requests import Request
        except ImportError as e:
            raise ImportError(
                "httpx and google-auth are required for Cloud GDA support: "
                "pip install httpx google-auth"
            ) from e

        creds, _ = default()
        creds.refresh(Request())
        headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
        url = f"https://analytics.googleapis.com/v1alpha/{path}"
        async with httpx.AsyncClient() as client:
            resp = await getattr(client, method.lower())(url, headers=headers, json=body)
            return resp.json()

    async def query(self, query: str) -> dict[str, Any]:
        """执行自然语言查询。"""
        return await self._request("POST", f"{self._parent}:query", {"query": query})

    async def list_accessible_data_agents(self) -> list[dict[str, Any]]:
        """列出可访问的数据代理。"""
        resp = await self._request("GET", f"{self._parent}/dataAgents")
        return resp.get("dataAgents", [])

    async def get_data_agent_info(self, agent_id: str) -> dict[str, Any]:
        """获取指定数据代理的详细信息。"""
        return await self._request("GET", f"{self._parent}/dataAgents/{agent_id}")

    async def ask_data_agent(self, agent_id: str, question: str) -> dict[str, Any]:
        """向指定数据代理提问。"""
        return await self._request(
            "POST", f"{self._parent}/dataAgents/{agent_id}:ask", {"question": question}
        )


@register_source("cloud-gemini-data-analytics")
@dataclass
class CloudGDASourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    location: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-gemini-data-analytics"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudGDASourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", ""),
        )

    async def initialize(self, tracer=None) -> CloudGDASource:
        """创建并初始化数据源实例。"""
        source = CloudGDASource(name=self._name, project_id=self.project_id, location=self.location)
        await source.connect()
        return source
