"""Cloud SQL MySQL source — Cloud SQL Connector + aiomysql.

Maps to Go: internal/sources/cloudsqlmysql/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class CloudSQLMySQLSource(Source):
    """Cloud SQL MySQL source using Cloud SQL Connector + aiomysql via SQLAlchemy."""

    # SQL safety limits (mirrors SQLSource defaults)
    max_rows: int = 10000
    query_timeout: float = 30.0

    def __init__(self, name: str, engine: Any, session_factory: Any):
        """初始化数据源配置。"""
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-sql-mysql"

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
            result = await session.execute(text("SHOW TABLES"))
            return [row[0] for row in result.fetchall()]


@register_source("cloud-sql-mysql")
@dataclass
class CloudSQLMySQLSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    region: str = ""
    instance_id: str = ""
    database: str = ""
    user: str = ""
    password: str = ""
    iam_auth: bool = False

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-sql-mysql"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudSQLMySQLSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            region=data.get("region", ""),
            instance_id=data.get("instanceId", ""),
            database=data.get("database", ""),
            user=data.get("user", ""),
            password=data.get("password", ""),
            iam_auth=data.get("iamAuth", False),
        )

    async def initialize(self, tracer=None) -> CloudSQLMySQLSource:
        """创建并初始化数据源实例。"""
        try:
            from google.cloud.sql.connector import AsyncConnector
        except ImportError as e:
            raise ImportError("cloud-sql-python-connector[aiomysql] is required") from e

        connector = AsyncConnector()
        instance_conn = f"{self.project_id}:{self.region}:{self.instance_id}"
        engine = create_async_engine(
            "mysql+aiomysql://",
            async_creator=lambda: connector.connect(
                instance_conn, "aiomysql",
                user=self.user, password=self.password, db=self.database,
            ),
        )
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = CloudSQLMySQLSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
