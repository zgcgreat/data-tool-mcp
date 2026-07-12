"""Bigtable source — google-cloud-bigtable.

Maps to Go: internal/sources/bigtable/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class BigtableSource(Source):
    """Bigtable source using google-cloud-bigtable with BigQuery federated query support."""

    def __init__(self, name: str, admin_client: Any, instance: Any, project_id: str):
        self._name = name
        self._admin_client = admin_client
        self._instance = instance
        self._project_id = project_id

    @property
    def source_type(self) -> str:
        return "bigtable"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        try:
            from google.cloud import bigquery
        except ImportError as e:
            raise ImportError("google-cloud-bigquery is required for federated queries") from e

        def _run() -> list[dict[str, Any]]:
            bq_client = bigquery.Client(project=self._project_id)
            rows = bq_client.query(sql).result()
            return [dict(row) for row in rows]

        return await loop.run_in_executor(None, _run)


@register_source("bigtable")
@dataclass
class BigtableSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    instance_id: str = ""

    @property
    def source_type(self) -> str:
        return "bigtable"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> BigtableSourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            instance_id=data.get("instanceId", ""),
        )

    async def initialize(self, tracer=None) -> BigtableSource:
        try:
            from google.cloud import bigtable
        except ImportError as e:
            raise ImportError("google-cloud-bigtable is required: pip install google-cloud-bigtable") from e

        admin_client = bigtable.Client(project=self.project_id, admin=True)
        instance = admin_client.instance(self.instance_id)
        source = BigtableSource(name=self._name, admin_client=admin_client, instance=instance, project_id=self.project_id)
        await source.connect()
        return source
