"""Serverless Spark source — GCP REST API.

Maps to Go: internal/sources/serverlessspark/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class ServerlessSparkSource(Source):
    """Serverless Spark source using GCP Dataproc REST API."""

    def __init__(self, name: str, project_id: str, region: str):
        """初始化数据源配置。"""
        self._name = name
        self._project_id = project_id
        self._region = region

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "serverless-spark"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass

    async def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        """向 Dataproc REST API 发送带认证的请求。"""
        try:
            import httpx
            from google.auth import default
            from google.auth.transport.requests import Request
        except ImportError as e:
            raise ImportError(
                "httpx and google-auth are required for Serverless Spark support: "
                "pip install httpx google-auth"
            ) from e

        creds, _ = default()
        creds.refresh(Request())
        headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
        url = f"https://dataproc.googleapis.com/v1/projects/{self._project_id}/regions/{self._region}/{path}"
        async with httpx.AsyncClient() as client:
            resp = await getattr(client, method.lower())(url, headers=headers, json=body)
            return resp.json()

    async def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话。"""
        resp = await self._request("GET", "sessions")
        return resp.get("sessions", [])

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """获取指定会话的详细信息。"""
        return await self._request("GET", f"sessions/{session_id}")

    async def list_batches(self) -> list[dict[str, Any]]:
        """列出所有批处理作业。"""
        resp = await self._request("GET", "batches")
        return resp.get("batches", [])

    async def get_batch(self, batch_id: str) -> dict[str, Any]:
        """获取指定批处理作业的详细信息。"""
        return await self._request("GET", f"batches/{batch_id}")

    async def create_spark_batch(self, batch_id: str, batch: dict) -> Any:
        """创建 Spark 批处理作业。"""
        return await self._request("POST", f"batches?batchId={batch_id}", batch)

    async def create_pyspark_batch(
        self, batch_id: str, main_python_file_uri: str, args: list[str] | None = None
    ) -> Any:
        """创建 PySpark 批处理作业。"""
        body = {
            "pysparkBatch": {
                "mainPythonFileUri": main_python_file_uri,
                "args": args or [],
            }
        }
        return await self._request("POST", f"batches?batchId={batch_id}", body)

    async def cancel_batch(self, batch_id: str) -> Any:
        """取消指定批处理作业。"""
        return await self._request("POST", f"batches/{batch_id}:cancel")


@register_source("serverless-spark")
@dataclass
class ServerlessSparkSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    region: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "serverless-spark"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ServerlessSparkSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            region=data.get("region", ""),
        )

    async def initialize(self, tracer=None) -> ServerlessSparkSource:
        """创建并初始化数据源实例。"""
        source = ServerlessSparkSource(
            name=self._name, project_id=self.project_id, region=self.region
        )
        await source.connect()
        return source
