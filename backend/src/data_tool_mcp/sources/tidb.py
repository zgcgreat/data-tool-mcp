"""TiDB source — aiomysql + SQLAlchemy (MySQL compatible).

Maps to Go: internal/sources/tidb/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from data_tool_mcp.sources.base import SQLSource, SourceConfig, register_source


class TiDBSource(SQLSource):
    """TiDB database source (MySQL compatible) using aiomysql via SQLAlchemy."""

    def __init__(self, name: str, engine: Any, session_factory: Any):
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        return "tidb"

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

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(text(f"DESCRIBE {table_name}"))
            return [dict(row) for row in result.mappings().all()]


@register_source("tidb")
@dataclass
class TiDBSourceConfig(SourceConfig):
    """TiDB source configuration.

    Maps to Go: internal/sources/tidb/ Config struct
    """
    _name: str = field(init=True, repr=False)
    connection_string: str = ""
    host: str = "localhost"
    port: int = 4000
    database: str = ""
    user: str = ""
    password: str = ""
    ssl_mode: str = ""
    max_open_conns: int = 4

    @property
    def source_type(self) -> str:
        return "tidb"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> TiDBSourceConfig:
        return cls(
            _name=name,
            connection_string=data.get("connectionString", ""),
            host=data.get("host", "localhost"),
            port=data.get("port", 4000),
            database=data.get("database", ""),
            user=data.get("user", ""),
            password=data.get("password", ""),
            ssl_mode=data.get("sslMode", ""),
            max_open_conns=data.get("maxOpenConns", 4),
        )

    def _build_url(self) -> str:
        if self.connection_string:
            return self.connection_string.replace("mysql://", "mysql+aiomysql://")
        url = f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        if self.ssl_mode:
            url += f"?ssl={self.ssl_mode}"
        return url

    async def initialize(self, tracer=None) -> TiDBSource:
        url = self._build_url()
        engine = create_async_engine(url, pool_size=self.max_open_conns, echo=False)
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = TiDBSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
