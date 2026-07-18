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


def _snowflake_param(name: str, value: str) -> str:
    """构造单个 Snowflake 查询参数,值为空则返回空字符串。"""
    return f"{name}={value}" if value else ""


def _join_query_params(params: list[str]) -> str:
    """将参数列表拼接为查询字符串,空列表返回空字符串。"""
    return "?" + "&".join(params) if params else ""


def _build_snowflake_query_params(warehouse: str, role: str) -> str:
    """构造 Snowflake URL 的查询参数字符串 (warehouse/role),无参数则返回空。"""
    parts = [_snowflake_param("warehouse", warehouse), _snowflake_param("role", role)]
    params = [p for p in parts if p]
    return _join_query_params(params)


class SnowflakeSource(SQLSource):
    """Snowflake database source using snowflake connector via SQLAlchemy."""

    def __init__(self, name: str, engine: Any, session_factory: Any):
        """初始化数据源配置。"""
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "snowflake"

    async def connect(self) -> None:
        """建立数据库连接。"""
        async with self._engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

    async def close(self) -> None:
        """关闭数据库连接。"""
        await self._engine.dispose()

    async def execute_sql(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
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
            result = await session.execute(text("SHOW TABLES"))
            return [row[1] for row in result.fetchall()]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """描述表结构,返回列信息列表。"""
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_name = :table_name "
                    "ORDER BY ordinal_position"
                ),
                {"table_name": table_name},
            )
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
        """返回数据源类型标识符。"""
        return "snowflake"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SnowflakeSourceConfig:
        """从字典构造配置实例。"""
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
        """构造 SQLAlchemy 异步连接 URL。"""
        if self.connection_string:
            return self.connection_string
        url = (
            f"snowflake://{self.user}:{self.password}@{self.account}/{self.database}/{self.schema}"
        )
        return url + _build_snowflake_query_params(self.warehouse, self.role)

    async def initialize(self, tracer=None) -> SnowflakeSource:
        """创建并初始化数据源实例。"""
        url = self._build_url()
        engine = create_async_engine(
            url,
            pool_size=self.max_open_conns,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = SnowflakeSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
