"""Dgraph source — pydgraph with asyncio wrapper.

Maps to Go: internal/sources/dgraph/
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class DgraphSource(NoSQLSource):
    """Dgraph source using pydgraph with asyncio wrapper."""

    def __init__(self, name: str, client: Any):
        """初始化数据源配置。"""
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "dgraph"

    async def connect(self) -> None:
        """建立数据库连接。"""
        loop = asyncio.get_event_loop()

        def _check() -> None:
            """同步执行登录校验。"""
            self._client.login(self._stub, self._api_key) if self._api_key else None

        await loop.run_in_executor(None, _check)

    async def close(self) -> None:
        """关闭数据库连接。"""
        self._client.close()

    async def execute_dql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """执行 DQL 查询并返回结果。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步执行只读事务查询并收集结果。"""
            txn = self._client.txn(read_only=True)
            try:
                resp = txn.query(query, variables=json.dumps(variables) if variables else None)
                result = json.loads(resp.json)
                return result if isinstance(result, list) else [result]
            finally:
                txn.discard()

        return await loop.run_in_executor(None, _run)


@register_source("dgraph")
@dataclass
class DgraphSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    url: str = "localhost:9080"
    api_key: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "dgraph"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DgraphSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            url=data.get("url", "localhost:9080"),
            api_key=data.get("apiKey", ""),
        )

    async def initialize(self, tracer=None) -> DgraphSource:
        """创建并初始化数据源实例。"""
        try:
            import pydgraph
        except ImportError as e:
            raise ImportError("pydgraph is required: pip install pydgraph") from e

        client_stub = pydgraph.DgraphClientStub(self.url)
        client = pydgraph.DgraphClient(client_stub)
        source = DgraphSource(name=self._name, client=client)
        source._stub = client_stub
        source._api_key = self.api_key
        await source.connect()
        return source
