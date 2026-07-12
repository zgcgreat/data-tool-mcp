"""ClickHouse source — asynch + SQLAlchemy.

Maps to Go: internal/sources/clickhouse/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from data_tool_mcp.sources.base import SQLSource, SourceConfig, register_source


class ClickHouseSource(SQLSource):
    """ClickHouse database source using asynch via SQLAlchemy."""

    def __init__(self, name: str, engine: Any, session_factory: Any):
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        return "clickhouse"

    async def connect(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self._engine.dispose()

    async def execute_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await asyncio.wait_for(
                session.execute(text(sql), params or {}),
                timeout=self.query_timeout,
            )
            rows = result.mappings().fetchmany(self.max_rows)
            return [dict(row) for row in rows]

    async def list_tables(self) -> list[str]:
        async with self._session_factory() as session:
            result = await session.execute(text("SHOW TABLES"))
            return [row[0] for row in result.fetchall()]

    async def list_databases(self) -> list[str]:
        """List all databases in the ClickHouse instance."""
        async with self._session_factory() as session:
            result = await session.execute(text("SHOW DATABASES"))
            return [row[0] for row in result.fetchall()]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(text(f"DESCRIBE {table_name}"))
            return [dict(row) for row in result.mappings().all()]


@register_source("clickhouse")
@dataclass
class ClickHouseSourceConfig(SourceConfig):
    """ClickHouse source configuration.

    Maps to Go: internal/sources/clickhouse/ Config struct
    """
    _name: str = field(init=True, repr=False)
    connection_string: str = ""
    host: str = "localhost"
    port: int = 9000
    database: str = "default"
    user: str = "default"
    password: str = ""
    secure: bool = False
    max_open_conns: int = 4

    @property
    def source_type(self) -> str:
        return "clickhouse"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ClickHouseSourceConfig:
        return cls(
            _name=name,
            connection_string=data.get("connectionString", ""),
            host=data.get("host", "localhost"),
            port=data.get("port", 9000),
            database=data.get("database", "default"),
            user=data.get("user", "default"),
            password=data.get("password", ""),
            secure=data.get("secure", False),
            max_open_conns=data.get("maxOpenConns", 4),
        )

    def _build_url(self) -> str:
        if self.connection_string:
            return self.connection_string.replace("clickhouse://", "clickhouse+asynch://")
        url = f"clickhouse+asynch://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        if self.secure:
            url += "?secure=true"
        return url

    async def initialize(self, tracer=None) -> ClickHouseSource:
        url = self._build_url()
        engine = create_async_engine(url, pool_size=self.max_open_conns, echo=False)
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = ClickHouseSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
