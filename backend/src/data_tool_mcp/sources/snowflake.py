"""Snowflake source — snowflake SQLAlchemy connector.

Maps to Go: internal/sources/snowflake/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from data_tool_mcp.sources.base import SQLSource, SourceConfig, register_source


class SnowflakeSource(SQLSource):
    """Snowflake database source using snowflake connector via SQLAlchemy."""

    def __init__(self, name: str, engine: Any, session_factory: Any):
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        return "snowflake"

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
            return [row[1] for row in result.fetchall()]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(text(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = :table_name "
                "ORDER BY ordinal_position"
            ), {"table_name": table_name})
            return [dict(row) for row in result.mappings().all()]


@register_source("snowflake")
@dataclass
class SnowflakeSourceConfig(SourceConfig):
    """Snowflake source configuration.

    Maps to Go: internal/sources/snowflake/ Config struct
    """
    _name: str = field(init=True, repr=False)
    connection_string: str = ""
    account: str = ""
    user: str = ""
    password: str = ""
    database: str = ""
    schema: str = "PUBLIC"
    warehouse: str = ""
    role: str = ""
    max_open_conns: int = 4

    @property
    def source_type(self) -> str:
        return "snowflake"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SnowflakeSourceConfig:
        return cls(
            _name=name,
            connection_string=data.get("connectionString", ""),
            account=data.get("account", ""),
            user=data.get("user", ""),
            password=data.get("password", ""),
            database=data.get("database", ""),
            schema=data.get("schema", "PUBLIC"),
            warehouse=data.get("warehouse", ""),
            role=data.get("role", ""),
            max_open_conns=data.get("maxOpenConns", 4),
        )

    def _build_url(self) -> str:
        if self.connection_string:
            return self.connection_string
        url = f"snowflake://{self.user}:{self.password}@{self.account}/{self.database}/{self.schema}"
        params = []
        if self.warehouse:
            params.append(f"warehouse={self.warehouse}")
        if self.role:
            params.append(f"role={self.role}")
        if params:
            url += "?" + "&".join(params)
        return url

    async def initialize(self, tracer=None) -> SnowflakeSource:
        url = self._build_url()
        engine = create_async_engine(url, pool_size=self.max_open_conns, echo=False)
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = SnowflakeSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
