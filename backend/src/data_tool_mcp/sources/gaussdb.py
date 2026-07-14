"""GaussDB source — asyncpg + SQLAlchemy (PostgreSQL compatible).

GaussDB 是华为云分布式数据库,兼容 PostgreSQL 协议,因此复用 asyncpg 驱动。
参考实现: postgresql.py

GaussDB 默认端口因部署形态不同:
  - 集中式: 5432 (与 PostgreSQL 一致)
  - 分布式: 25308 (CN 节点)
此处默认 5432,用户可按实际部署填写。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from data_tool_mcp.sources.base import SQLSource, SourceConfig, register_source


class GaussDBSource(SQLSource):
    """GaussDB database source (PostgreSQL compatible) using asyncpg via SQLAlchemy."""

    def __init__(self, name: str, engine: Any, session_factory: Any):
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        return "gaussdb"

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
            result = await session.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ))
            return [row[0] for row in result.fetchall()]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        # Validate table name against SQL injection
        if not table_name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"invalid table name: {table_name}")
        async with self._session_factory() as session:
            result = await session.execute(text(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = :table_name AND table_schema = 'public' "
                "ORDER BY ordinal_position"
            ), {"table_name": table_name})
            return [dict(row) for row in result.mappings().all()]


@register_source("gaussdb")
@dataclass
class GaussDBSourceConfig(SourceConfig):
    """GaussDB source configuration.

    GaussDB 兼容 PostgreSQL 协议,连接参数与 PostgreSQL 一致。
    """
    _name: str = field(init=True, repr=False)
    connection_string: str = ""
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    user: str = ""
    password: str = ""
    max_open_conns: int = 4

    @property
    def source_type(self) -> str:
        return "gaussdb"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> GaussDBSourceConfig:
        return cls(
            _name=name,
            connection_string=data.get("connectionString", ""),
            host=data.get("host", "localhost"),
            port=data.get("port", 5432),
            database=data.get("database", ""),
            user=data.get("user", ""),
            password=data.get("password", ""),
            max_open_conns=data.get("maxOpenConns", 4),
        )

    def _build_url(self) -> str:
        if self.connection_string:
            url = self.connection_string
            url = url.replace("postgresql://", "postgresql+asyncpg://")
            url = url.replace("postgres://", "postgresql+asyncpg://")
            url = url.replace("gaussdb://", "postgresql+asyncpg://")
            return url
        user = quote_plus(self.user) if self.user else ""
        password = quote_plus(self.password) if self.password else ""
        auth = f"{user}:{password}" if user else ""
        return f"postgresql+asyncpg://{auth}@{self.host}:{self.port}/{self.database}"

    async def initialize(self, tracer=None) -> GaussDBSource:
        url = self._build_url()
        engine = create_async_engine(
            url,
            pool_size=self.max_open_conns,
            echo=False,
        )
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = GaussDBSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
