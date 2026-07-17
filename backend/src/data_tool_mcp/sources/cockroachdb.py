"""CockroachDB source — asyncpg + SQLAlchemy (PostgreSQL compatible).

Maps to Go: internal/sources/cockroachdb/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from data_tool_mcp.sources.base import SQLSource, SourceConfig, register_source


class CockroachDBSource(SQLSource):
    """CockroachDB database source (PostgreSQL compatible) using asyncpg via SQLAlchemy."""

    def __init__(self, name: str, engine: Any, session_factory: Any):
        """初始化数据源配置。"""
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cockroachdb"

    async def connect(self) -> None:
        """建立数据库连接。"""
        async with self._engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

    async def close(self) -> None:
        """关闭数据库连接。"""
        await self._engine.dispose()

    async def execute_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询并返回结果。"""
        async with self._session_factory() as session:
            result = await asyncio.wait_for(
                session.execute(text(sql), params or {}),
                timeout=self.query_timeout,
            )
            rows = result.mappings().fetchmany(self.max_rows)
            return [dict(row) for row in rows]

    async def list_tables(self) -> list[str]:
        """列出数据库中所有表。"""
        async with self._session_factory() as session:
            result = await session.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ))
            return [row[0] for row in result.fetchall()]

    async def list_schemas(self) -> list[str]:
        """List all schemas in the CockroachDB database."""
        async with self._session_factory() as session:
            result = await session.execute(text(
                "SELECT schema_name FROM information_schema.schemata ORDER BY schema_name"
            ))
            return [row[0] for row in result.fetchall()]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """描述表结构，返回列信息列表。"""
        async with self._session_factory() as session:
            result = await session.execute(text(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = :table_name AND table_schema = 'public' "
                "ORDER BY ordinal_position"
            ), {"table_name": table_name})
            return [dict(row) for row in result.mappings().all()]


@register_source("cockroachdb")
@dataclass
class CockroachDBSourceConfig(SourceConfig):
    """CockroachDB source configuration.

    Maps to Go: internal/sources/cockroachdb/ Config struct
    """
    _name: str = field(init=True, repr=False)
    connection_string: str = ""
    host: str = "localhost"
    port: int = 26257
    database: str = ""
    user: str = ""
    password: str = ""
    sslmode: str = "require"
    max_open_conns: int = 4

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cockroachdb"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CockroachDBSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            connection_string=data.get("connectionString", ""),
            host=data.get("host", "localhost"),
            port=data.get("port", 26257),
            database=data.get("database", ""),
            user=data.get("user", ""),
            password=data.get("password", ""),
            sslmode=data.get("sslmode", "require"),
            max_open_conns=data.get("maxOpenConns", 4),
        )

    def _build_url(self) -> str:
        """构造 SQLAlchemy 异步连接 URL。"""
        if self.connection_string:
            return (
                self.connection_string
                .replace("postgresql://", "postgresql+asyncpg://")
                .replace("postgres://", "postgresql+asyncpg://")
            )
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
            f"?sslmode={self.sslmode}"
        )

    async def initialize(self, tracer=None) -> CockroachDBSource:
        """创建并初始化数据源实例。"""
        url = self._build_url()
        engine = create_async_engine(url, pool_size=self.max_open_conns, echo=False)
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = CockroachDBSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
