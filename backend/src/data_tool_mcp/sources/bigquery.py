"""BigQuery source — google-cloud-bigquery.

Maps to Go: internal/sources/bigquery/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class BigQuerySource(Source):
    """BigQuery source using google-cloud-bigquery with asyncio wrapper."""

    def __init__(self, name: str, client: Any, project_id: str):
        self._name = name
        self._client = client
        self._project_id = project_id

    @property
    def source_type(self) -> str:
        return "bigquery"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: list(self._client.query("SELECT 1").result()))

    async def close(self) -> None:
        self._client.close()

    async def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            rows = self._client.query(sql).result()
            return [dict(row) for row in rows]

        return await loop.run_in_executor(None, _run)

    async def list_dataset_ids(self) -> list[str]:
        loop = asyncio.get_event_loop()
        datasets = await loop.run_in_executor(None, lambda: list(self._client.list_datasets()))
        return [d.dataset_id for d in datasets]

    async def list_table_ids(self, dataset_id: str) -> list[str]:
        loop = asyncio.get_event_loop()
        tables = await loop.run_in_executor(None, lambda: list(self._client.list_tables(dataset_id)))
        return [t.table_id for t in tables]

    async def get_dataset_info(self, dataset_id: str) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        ds = await loop.run_in_executor(None, lambda: self._client.get_dataset(dataset_id))
        return {"dataset_id": ds.dataset_id, "description": ds.description}

    async def get_table_info(self, dataset_id: str, table_id: str) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        tbl = await loop.run_in_executor(None, lambda: self._client.get_table(f"{dataset_id}.{table_id}"))
        return {"table_id": tbl.table_id, "schema": [f"{s.name}:{s.field_type}" for s in tbl.schema]}

    async def search_catalog(self, query: str) -> list[dict[str, Any]]:
        return await self.execute_sql(query)


@register_source("bigquery")
@dataclass
class BigQuerySourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    location: str = "US"
    write_mode: bool = False

    @property
    def source_type(self) -> str:
        return "bigquery"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> BigQuerySourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", "US"),
            write_mode=data.get("writeMode", False),
        )

    async def initialize(self, tracer=None) -> BigQuerySource:
        try:
            from google.cloud import bigquery
        except ImportError as e:
            raise ImportError("google-cloud-bigquery is required: pip install google-cloud-bigquery") from e

        client = bigquery.Client(project=self.project_id, location=self.location)
        source = BigQuerySource(name=self._name, client=client, project_id=self.project_id)
        source._write_mode = self.write_mode
        await source.connect()
        return source
