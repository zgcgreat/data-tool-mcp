"""SQLite source — aiosqlite + SQLAlchemy.

Maps to Go: internal/sources/sqlite/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from data_tool_mcp.sources.base import SQLSource, SourceConfig, register_source


class SQLiteSource(SQLSource):
    """SQLite database source."""

    def __init__(self, name: str, engine: Any, session_factory: Any):
        self._name = name
        self._engine = engine
        self._session_factory = session_factory

    @property
    def source_type(self) -> str:
        return "sqlite"

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
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ))
            return [row[0] for row in result.fetchall()]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        # Validate table name against SQL injection (PRAGMA does not support parameters)
        if not table_name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"invalid table name: {table_name}")
        async with self._session_factory() as session:
            result = await session.execute(text(f"PRAGMA table_info({table_name})"))
            return [
                {
                    "column_name": row["name"],
                    "data_type": row["type"],
                    "notnull": row["notnull"],
                    "default": row["dflt_value"],
                    "pk": row["pk"],
                }
                for row in result.mappings().all()
            ]


@register_source("sqlite")
@dataclass
class SQLiteSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    path: str = "test.db"

    @property
    def source_type(self) -> str:
        return "sqlite"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SQLiteSourceConfig:
        path = data.get("path", data.get("database", "test.db"))
        return cls(_name=name, path=path)

    async def initialize(self, tracer=None) -> SQLiteSource:
        url = f"sqlite+aiosqlite:///{self.path}"
        engine = create_async_engine(url, echo=False)
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        source = SQLiteSource(name=self._name, engine=engine, session_factory=session_factory)
        await source.connect()
        return source
