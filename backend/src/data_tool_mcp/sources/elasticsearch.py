"""Elasticsearch source — elasticsearch-async.

Maps to Go: internal/sources/elasticsearch/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class ElasticsearchSource(NoSQLSource):
    """Elasticsearch source using async elasticsearch client."""

    def __init__(self, name: str, client: Any):
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        return "elasticsearch"

    async def connect(self) -> None:
        await self._client.info()

    async def close(self) -> None:
        await self._client.close()

    async def execute_esql(self, query: str) -> list[dict[str, Any]]:
        resp = await self._client.esql.query(query=query)
        columns = [col["name"] for col in resp.get("columns", [])]
        return [dict(zip(columns, row)) for row in resp.get("values", [])]

    async def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
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
        return "elasticsearch"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ElasticsearchSourceConfig:
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
        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError as e:
            raise ImportError("elasticsearch[async] is required: pip install elasticsearch[async]") from e

        kwargs: dict[str, Any] = {"verify_certs": self.verify_certs}
        if self.cloud_id:
            kwargs["cloud_id"] = self.cloud_id
        else:
            kwargs["hosts"] = self.hosts
        if self.api_key:
            kwargs["api_key"] = self.api_key
        elif self.username:
            kwargs["basic_auth"] = (self.username, self.password)

        client = AsyncElasticsearch(**kwargs)
        source = ElasticsearchSource(name=self._name, client=client)
        await source.connect()
        return source
