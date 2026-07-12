"""Spanner source — google-cloud-spanner.

Maps to Go: internal/sources/spanner/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class SpannerSource(Source):
    """Spanner source using google-cloud-spanner with asyncio wrapper."""

    def __init__(self, name: str, client: Any, instance: Any, database: Any):
        self._name = name
        self._client = client
        self._instance = instance
        self._database = database

    @property
    def source_type(self) -> str:
        return "spanner"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._database.execute_sql("SELECT 1").__iter__())

    async def close(self) -> None:
        pass

    async def execute_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            with self._database.snapshot() as snapshot:
                rows = snapshot.execute_sql(sql, params=params)
                return [dict(row) for row in rows]

        return await loop.run_in_executor(None, _run)

    async def list_tables(self) -> list[str]:
        rows = await self.execute_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ''"
        )
        return [r["table_name"] for r in rows]

    async def list_graphs(self) -> list[str]:
        rows = await self.execute_sql(
            "SELECT graph_name FROM information_schema.property_graphs"
        )
        return [r["graph_name"] for r in rows]

    async def search_catalog(self, query: str) -> list[dict[str, Any]]:
        return await self.execute_sql(query)


@register_source("spanner")
@dataclass
class SpannerSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    instance_id: str = ""
    database_id: str = ""

    @property
    def source_type(self) -> str:
        return "spanner"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SpannerSourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            instance_id=data.get("instanceId", ""),
            database_id=data.get("databaseId", ""),
        )

    async def initialize(self, tracer=None) -> SpannerSource:
        try:
            from google.cloud import spanner
        except ImportError as e:
            raise ImportError("google-cloud-spanner is required: pip install google-cloud-spanner") from e

        client = spanner.Client(project=self.project_id)
        instance = client.instance(self.instance_id)
        database = instance.database(self.database_id)
        source = SpannerSource(name=self._name, client=client, instance=instance, database=database)
        await source.connect()
        return source
