"""ScyllaDB source — cassandra-driver with ScyllaDB defaults.

Maps to Go: internal/sources/scylladb/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source
from data_tool_mcp.sources.cassandra import _build_auth_provider, _import_cassandra


class ScyllaDBSource(NoSQLSource):
    """ScyllaDB source using cassandra-driver (CQL-compatible) with asyncio wrapper."""

    def __init__(self, name: str, cluster: Any, session: Any):
        """初始化数据源配置。"""
        self._name = name
        self._cluster = cluster
        self._session = session

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "scylladb"

    async def connect(self) -> None:
        """建立数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._session.execute("SELECT release_version FROM system.local")
        )

    async def close(self) -> None:
        """关闭数据库连接。"""
        self._cluster.shutdown()

    async def execute_cql(self, cql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行 CQL 查询并返回结果。"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._session.execute(cql, params))
        return [dict(row._asdict()) for row in result]

    async def list_tables(self) -> list[str]:
        """列出当前 keyspace 中所有表。"""
        rows = await self.execute_cql(
            "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
            (self._keyspace,),
        )
        return [row["table_name"] for row in rows]


@register_source("scylladb")
@dataclass
class ScyllaDBSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    host: str = "localhost"
    port: int = 9042
    username: str = ""
    password: str = ""
    keyspace: str = ""
    datacenter: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "scylladb"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ScyllaDBSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            host=data.get("host", "localhost"),
            port=data.get("port", 9042),
            username=data.get("username", ""),
            password=data.get("password", ""),
            keyspace=data.get("keyspace", ""),
            datacenter=data.get("datacenter", ""),
        )

    async def initialize(self, tracer=None) -> ScyllaDBSource:
        """创建并初始化数据源实例。"""
        Cluster, PlainTextAuthProvider = _import_cassandra()
        auth_provider = _build_auth_provider(self.username, self.password, PlainTextAuthProvider)
        cluster = Cluster(
            contact_points=[self.host],
            port=self.port,
            auth_provider=auth_provider,
        )
        session = cluster.connect(self.keyspace or None)
        source = ScyllaDBSource(name=self._name, cluster=cluster, session=session)
        source._keyspace = self.keyspace
        await source.connect()
        return source
