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

    def __init__(
        self, name: str, cluster_client: Any, job_client: Any, project_id: str, region: str
    ):
        """初始化数据源配置。"""
        self._name = name
        self._cluster_client = cluster_client
        self._job_client = job_client
        self._project_id = project_id
        self._region = region
        self._region_path = f"projects/{project_id}/regions/{region}"

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "dataproc"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass  # GCP 无状态客户端：连接已在 initialize() 中建立，此处为有意空实现（no-op）

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass  # GCP 无状态客户端：无需显式关闭，交由垃圾回收（no-op）

    async def _exec(self, fn):
        """在线程池中执行同步调用。"""
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    async def list_jobs(self) -> list[dict[str, Any]]:
        """列出所有 Dataproc 作业。"""
        jobs = await self._exec(lambda: list(self._job_client.list_jobs(region=self._region_path)))
        return [dict(j) for j in jobs]

    async def get_job(self, job_id: str) -> dict[str, Any]:
        """获取指定作业的详细信息。"""
        job = await self._exec(
            lambda: self._job_client.get_job(region=self._region_path, job_id=job_id)
        )
        return dict(job)

    async def list_clusters(self) -> list[dict[str, Any]]:
        """列出所有 Dataproc 集群。"""
        clusters = await self._exec(
            lambda: list(self._cluster_client.list_clusters(region=self._region_path))
        )
        return [dict(c) for c in clusters]

    async def get_cluster(self, cluster_name: str) -> dict[str, Any]:
        """获取指定集群的详细信息。"""
        cluster = await self._exec(
            lambda: self._cluster_client.get_cluster(
                region=self._region_path, cluster_name=cluster_name
            )
        )
        return dict(cluster)


@register_source("dataproc")
@dataclass
class DataprocSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    region: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "dataproc"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataprocSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            region=data.get("region", ""),
        )

    async def initialize(self, tracer=None) -> DataprocSource:
        """创建并初始化数据源实例。"""
        try:
            from google.cloud import dataproc_v1
        except ImportError as e:
            raise ImportError(
                "google-cloud-dataproc is required: pip install google-cloud-dataproc"
            ) from e

        cluster_client = dataproc_v1.ClusterControllerClient()
        job_client = dataproc_v1.JobControllerClient()
        source = DataprocSource(
            name=self._name,
            cluster_client=cluster_client,
            job_client=job_client,
            project_id=self.project_id,
            region=self.region,
        )
        await source.connect()
        return source
