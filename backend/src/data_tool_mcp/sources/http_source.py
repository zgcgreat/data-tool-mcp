"""HTTP source — httpx-based generic REST API.

Maps to Go: internal/sources/http/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class HTTPSource(Source):
    """HTTP source using httpx for generic REST API access."""

    def __init__(self, name: str, base_url: str, default_headers: dict[str, str], default_method: str, client: httpx.AsyncClient):
        self._name = name
        self._base_url = base_url
        self._default_headers = default_headers
        self._default_method = default_method
        self._client = client

    @property
    def source_type(self) -> str:
        return "http"

    async def connect(self) -> None:
        if self._base_url:
            resp = await self._client.get(self._base_url)
            resp.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()

    async def make_request(
        self, method: str | None = None, path: str = "",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{path}".rstrip("/") if self._base_url else path
        merged_headers = {**self._default_headers, **(headers or {})}
        resp = await self._client.request(
            method=method or self._default_method,
            url=url,
            headers=merged_headers,
            params=params,
            json=body if isinstance(body, (dict, list)) else None,
            content=body if isinstance(body, str) else None,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status_code": resp.status_code, "text": resp.text}


@register_source("http")
@dataclass
class HTTPSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    base_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    method: str = "GET"
    auth_type: str = ""
    auth_token: str = ""

    @property
    def source_type(self) -> str:
        return "http"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HTTPSourceConfig:
        return cls(
            _name=name,
            base_url=data.get("baseUrl", ""),
            headers=data.get("headers", {}),
            method=data.get("method", "GET"),
            auth_type=data.get("authType", ""),
            auth_token=data.get("authToken", ""),
        )

    async def initialize(self, tracer=None) -> HTTPSource:
        client_headers: dict[str, str] = dict(self.headers)
        if self.auth_type == "bearer" and self.auth_token:
            client_headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.auth_type == "basic" and self.auth_token:
            client_headers["Authorization"] = f"Basic {self.auth_token}"

        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx is required for HTTP source support: pip install httpx"
            ) from e

        client = httpx.AsyncClient(headers=client_headers, timeout=30.0)
        source = HTTPSource(
            name=self._name, base_url=self.base_url,
            default_headers=dict(self.headers), default_method=self.method,
            client=client,
        )
        await source.connect()
        return source
