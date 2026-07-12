"""Dataproc source — google-cloud-dataproc.

Maps to Go: internal/sources/dataproc/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class DataprocSource(Source):
    """Dataproc source using google-cloud-dataproc API."""

    def __init__(self, name: str, cluster_client: Any, job_client: Any, project_id: str, region: str):
        self._name = name
        self._cluster_client = cluster_client
        self._job_client = job_client
        self._project_id = project_id
        self._region = region
        self._region_path = f"projects/{project_id}/regions/{region}"

    @property
    def source_type(self) -> str:
        return "dataproc"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def _exec(self, fn):
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    async def list_jobs(self) -> list[dict[str, Any]]:
        jobs = await self._exec(lambda: list(self._job_client.list_jobs(region=self._region_path)))
        return [dict(j) for j in jobs]

    async def get_job(self, job_id: str) -> dict[str, Any]:
        job = await self._exec(lambda: self._job_client.get_job(region=self._region_path, job_id=job_id))
        return dict(job)

    async def list_clusters(self) -> list[dict[str, Any]]:
        clusters = await self._exec(lambda: list(self._cluster_client.list_clusters(region=self._region_path)))
        return [dict(c) for c in clusters]

    async def get_cluster(self, cluster_name: str) -> dict[str, Any]:
        cluster = await self._exec(lambda: self._cluster_client.get_cluster(region=self._region_path, cluster_name=cluster_name))
        return dict(cluster)


@register_source("dataproc")
@dataclass
class DataprocSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    region: str = ""

    @property
    def source_type(self) -> str:
        return "dataproc"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataprocSourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            region=data.get("region", ""),
        )

    async def initialize(self, tracer=None) -> DataprocSource:
        try:
            from google.cloud import dataproc_v1
        except ImportError as e:
            raise ImportError("google-cloud-dataproc is required: pip install google-cloud-dataproc") from e

        cluster_client = dataproc_v1.ClusterControllerClient()
        job_client = dataproc_v1.JobControllerClient()
        source = DataprocSource(
            name=self._name, cluster_client=cluster_client, job_client=job_client,
            project_id=self.project_id, region=self.region,
        )
        await source.connect()
        return source
