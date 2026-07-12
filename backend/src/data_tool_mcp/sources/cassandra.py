"""Cassandra source — cassandra-driver wrapped with asyncio.

Maps to Go: internal/sources/cassandra/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class CassandraSource(NoSQLSource):
    """Cassandra source using cassandra-driver with asyncio wrapper."""

    def __init__(self, name: str, cluster: Any, session: Any):
        self._name = name
        self._cluster = cluster
        self._session = session

    @property
    def source_type(self) -> str:
        return "cassandra"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._session.execute("SELECT release_version FROM system.local"))

    async def close(self) -> None:
        self._cluster.shutdown()

    async def execute_cql(self, cql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._session.execute(cql, params))
        return [dict(row._asdict()) for row in result]

    async def list_tables(self) -> list[str]:
        rows = await self.execute_cql(
            "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
            (self._keyspace,),
        )
        return [row["table_name"] for row in rows]


@register_source("cassandra")
@dataclass
class CassandraSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    host: str = "localhost"
    port: int = 9042
    username: str = ""
    password: str = ""
    keyspace: str = ""
    datacenter: str = ""
    max_connections: int = 4

    @property
    def source_type(self) -> str:
        return "cassandra"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CassandraSourceConfig:
        return cls(
            _name=name,
            host=data.get("host", "localhost"),
            port=data.get("port", 9042),
            username=data.get("username", ""),
            password=data.get("password", ""),
            keyspace=data.get("keyspace", ""),
            datacenter=data.get("datacenter", ""),
            max_connections=data.get("maxConnections", 4),
        )

    async def initialize(self, tracer=None) -> CassandraSource:
        try:
            from cassandra.cluster import Cluster
            from cassandra.auth import PlainTextAuthProvider
        except ImportError as e:
            raise ImportError("cassandra-driver is required: pip install cassandra-driver") from e

        auth_provider = None
        if self.username and self.password:
            auth_provider = PlainTextAuthProvider(username=self.username, password=self.password)

        cluster = Cluster(
            contact_points=[self.host],
            port=self.port,
            auth_provider=auth_provider,
            max_connections=self.max_connections,
        )
        session = cluster.connect(self.keyspace or None)
        source = CassandraSource(name=self._name, cluster=cluster, session=session)
        source._keyspace = self.keyspace
        await source.connect()
        return source
