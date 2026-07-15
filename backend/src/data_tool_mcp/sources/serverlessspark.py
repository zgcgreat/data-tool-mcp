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
        self._name = name
        self._project_id = project_id
        self._region = region

    @property
    def source_type(self) -> str:
        return "serverless-spark"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def _request(self, method: str, path: str, body: dict | None = None) -> Any:
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
        resp = await self._request("GET", "sessions")
        return resp.get("sessions", [])

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("GET", f"sessions/{session_id}")

    async def list_batches(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "batches")
        return resp.get("batches", [])

    async def get_batch(self, batch_id: str) -> dict[str, Any]:
        return await self._request("GET", f"batches/{batch_id}")

    async def create_spark_batch(self, batch_id: str, batch: dict) -> Any:
        return await self._request("POST", f"batches?batchId={batch_id}", batch)

    async def create_pyspark_batch(self, batch_id: str, main_python_file_uri: str, args: list[str] | None = None) -> Any:
        body = {
            "pysparkBatch": {
                "mainPythonFileUri": main_python_file_uri,
                "args": args or [],
            }
        }
        return await self._request("POST", f"batches?batchId={batch_id}", body)

    async def cancel_batch(self, batch_id: str) -> Any:
        return await self._request("POST", f"batches/{batch_id}:cancel")


@register_source("serverless-spark")
@dataclass
class ServerlessSparkSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    region: str = ""

    @property
    def source_type(self) -> str:
        return "serverless-spark"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ServerlessSparkSourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            region=data.get("region", ""),
        )

    async def initialize(self, tracer=None) -> ServerlessSparkSource:
        source = ServerlessSparkSource(name=self._name, project_id=self.project_id, region=self.region)
        await source.connect()
        return source
