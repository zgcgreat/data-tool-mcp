"""HTTP source — httpx-based generic REST API.

Maps to Go: internal/sources/http/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


def _build_request_body(body: Any) -> dict[str, Any]:
    """根据 body 类型构造 httpx request 的 json/content 参数。"""
    if isinstance(body, (dict, list)):
        return {"json": body}
    if isinstance(body, str):
        return {"content": body}
    return {}


_AUTH_HEADER_BUILDERS = {
    "bearer": lambda token: f"Bearer {token}",
    "basic": lambda token: f"Basic {token}",
}


def _build_auth_headers(auth_type: str, auth_token: str) -> dict[str, str]:
    """根据认证类型构造 Authorization 请求头。"""
    builder = _AUTH_HEADER_BUILDERS.get(auth_type)
    if not builder or not auth_token:
        return {}
    return {"Authorization": builder(auth_token)}


def _parse_response(resp: Any) -> dict[str, Any]:
    """解析 HTTP 响应:优先返回 JSON,失败则返回状态码和文本。"""
    try:
        return resp.json()
    except Exception:
        return {"status_code": resp.status_code, "text": resp.text}


def _import_httpx() -> Any:
    """延迟导入 httpx,未安装时抛出带提示的 ImportError。"""
    try:
        import httpx
    except ImportError as e:
        raise ImportError(
            "httpx is required for HTTP source support: pip install httpx"
        ) from e
    return httpx


class HTTPSource(Source):
    """HTTP source using httpx for generic REST API access."""

    def __init__(self, name: str, base_url: str, default_headers: dict[str, str], default_method: str, client: httpx.AsyncClient):
        """初始化数据源配置。"""
        self._name = name
        self._base_url = base_url
        self._default_headers = default_headers
        self._default_method = default_method
        self._client = client

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "http"

    async def connect(self) -> None:
        """建立数据库连接。"""
        if self._base_url:
            resp = await self._client.get(self._base_url)
            resp.raise_for_status()

    async def close(self) -> None:
        """关闭数据库连接。"""
        await self._client.aclose()

    def _build_url(self, path: str) -> str:
        """构造请求 URL,有 base_url 时拼接并去除尾部斜杠。"""
        if self._base_url:
            return f"{self._base_url}/{path}".rstrip("/")
        return path

    async def make_request(
        self, method: str | None = None, path: str = "",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> dict[str, Any]:
        """发起 HTTP 请求并返回解析后的响应。"""
        url = self._build_url(path)
        merged_headers = {**self._default_headers, **(headers or {})}
        resp = await self._client.request(
            method=method or self._default_method,
            url=url,
            headers=merged_headers,
            params=params,
            **_build_request_body(body),
        )
        resp.raise_for_status()
        return _parse_response(resp)


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
        """返回数据源类型标识符。"""
        return "http"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HTTPSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            base_url=data.get("baseUrl", ""),
            headers=data.get("headers", {}),
            method=data.get("method", "GET"),
            auth_type=data.get("authType", ""),
            auth_token=data.get("authToken", ""),
        )

    async def initialize(self, tracer=None) -> HTTPSource:
        """创建并初始化数据源实例。"""
        client_headers: dict[str, str] = {
            **dict(self.headers),
            **_build_auth_headers(self.auth_type, self.auth_token),
        }
        httpx = _import_httpx()
        client = httpx.AsyncClient(headers=client_headers, timeout=30.0)
        source = HTTPSource(
            name=self._name, base_url=self.base_url,
            default_headers=dict(self.headers), default_method=self.method,
            client=client,
        )
        await source.connect()
        return source
