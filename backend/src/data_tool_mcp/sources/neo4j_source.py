"""Neo4j source — official Python driver wrapped with asyncio.

Maps to Go: internal/sources/neo4j/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class Neo4jSource(NoSQLSource):
    """Neo4j source using the official Python driver with asyncio wrapper."""

    def __init__(self, name: str, driver: Any, database: str):
        self._name = name
        self._driver = driver
        self._database = database

    @property
    def source_type(self) -> str:
        return "neo4j"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._driver.verify_connectivity())

    async def close(self) -> None:
        self._driver.close()

    async def execute_cypher(self, query: str, params: dict | None = None) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            with self._driver.session(database=self._database) as session:
                result = session.run(query, params or {})
                return [dict(record) for record in result]

        return await loop.run_in_executor(None, _run)

    async def get_schema(self) -> list[dict[str, Any]]:
        return await self.execute_cypher("CALL db.schema.visualization()")


@register_source("neo4j")
@dataclass
class Neo4jSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    uri: str = "bolt://localhost:7687"
    user: str = ""
    password: str = ""
    database: str = "neo4j"
    max_connection_pool_size: int = 10

    @property
    def source_type(self) -> str:
        return "neo4j"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Neo4jSourceConfig:
        return cls(
            _name=name,
            uri=data.get("uri", "bolt://localhost:7687"),
            user=data.get("user", ""),
            password=data.get("password", ""),
            database=data.get("database", "neo4j"),
            max_connection_pool_size=data.get("maxConnectionPoolSize", 10),
        )

    async def initialize(self, tracer=None) -> Neo4jSource:
        try:
            from neo4j import GraphDatabase
        except ImportError as e:
            raise ImportError("neo4j is required: pip install neo4j") from e

        driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password) if self.user else None,
            max_connection_pool_size=self.max_connection_pool_size,
        )
        source = Neo4jSource(name=self._name, driver=driver, database=self.database)
        await source.connect()
        return source
