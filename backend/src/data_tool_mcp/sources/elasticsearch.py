"""Elasticsearch source — elasticsearch-async.

Maps to Go: internal/sources/elasticsearch/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


def _import_async_elasticsearch() -> Any:
    """延迟导入 elasticsearch,未安装时抛出带提示的 ImportError。"""
    try:
        from elasticsearch import AsyncElasticsearch
    except ImportError as e:
        raise ImportError("elasticsearch is required: pip install elasticsearch") from e
    return AsyncElasticsearch


def _add_es_endpoint(kwargs: dict[str, Any], cloud_id: str, hosts: list[str]) -> None:
    """添加 cloud_id 或 hosts 到 kwargs。"""
    if cloud_id:
        kwargs["cloud_id"] = cloud_id
        return
    kwargs["hosts"] = hosts


def _add_es_auth(kwargs: dict[str, Any], api_key: str, username: str, password: str) -> None:
    """添加 api_key 或 basic_auth 到 kwargs。"""
    if api_key:
        kwargs["api_key"] = api_key
        return
    if username:
        kwargs["basic_auth"] = (username, password)


def _build_es_kwargs(
    cloud_id: str, hosts: list[str], api_key: str,
    username: str, password: str, verify_certs: bool,
) -> dict[str, Any]:
    """构造 AsyncElasticsearch 的连接参数。"""
    kwargs: dict[str, Any] = {"verify_certs": verify_certs}
    _add_es_endpoint(kwargs, cloud_id, hosts)
    _add_es_auth(kwargs, api_key, username, password)
    return kwargs


class ElasticsearchSource(NoSQLSource):
    """Elasticsearch source using async elasticsearch client."""

    def __init__(self, name: str, client: Any):
        """初始化数据源配置。"""
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "elasticsearch"

    async def connect(self) -> None:
        """建立数据库连接。"""
        await self._client.info()

    async def close(self) -> None:
        """关闭数据库连接。"""
        await self._client.close()

    async def execute_esql(self, query: str) -> list[dict[str, Any]]:
        """执行 ES|QL 查询并返回结果。"""
        resp = await self._client.esql.query(query=query)
        columns = [col["name"] for col in resp.get("columns", [])]
        return [dict(zip(columns, row)) for row in resp.get("values", [])]

    async def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        """执行搜索查询并返回响应。"""
        resp = await self._client.search(index=index, body=body)
        return dict(resp)


@register_source("elasticsearch")
@dataclass
class ElasticsearchSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    hosts: list[str] = field(default_factory=lambda: ["http://localhost:9200"])
    username: str = ""
    password: str = ""
    api_key: str = ""
    cloud_id: str = ""
    verify_certs: bool = True

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "elasticsearch"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ElasticsearchSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            hosts=data.get("hosts", ["http://localhost:9200"]),
            username=data.get("username", ""),
            password=data.get("password", ""),
            api_key=data.get("apiKey", ""),
            cloud_id=data.get("cloudId", ""),
            verify_certs=data.get("verifyCerts", True),
        )

    async def initialize(self, tracer=None) -> ElasticsearchSource:
        """创建并初始化数据源实例。"""
        AsyncElasticsearch = _import_async_elasticsearch()
        kwargs = _build_es_kwargs(
            self.cloud_id, self.hosts, self.api_key,
            self.username, self.password, self.verify_certs,
        )
        client = AsyncElasticsearch(**kwargs)
        source = ElasticsearchSource(name=self._name, client=client)
        await source.connect()
        return source
