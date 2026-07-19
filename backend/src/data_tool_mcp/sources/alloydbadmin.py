"""AlloyDB Admin source — google-cloud-alloydb REST API.

Maps to Go: internal/sources/alloydbadmin/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class AlloyDBAdminSource(Source):
    """AlloyDB Admin source using google-cloud-alloydb API."""

    def __init__(self, name: str, client: Any, project_id: str, location: str):
        """初始化数据源配置。"""
        self._name = name
        self._client = client
        self._project_id = project_id
        self._location = location
        self._parent = f"projects/{project_id}/locations/{location}"

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "alloydb-admin"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass  # GCP 无状态客户端：连接已在 initialize() 中建立，此处为有意空实现（no-op）

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass  # GCP 无状态客户端：无需显式关闭，交由垃圾回收（no-op）

    async def _execute(self, fn):
        """在线程池中执行同步调用。"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)

    async def list_clusters(self) -> list[dict[str, Any]]:
        """列出所有 AlloyDB 集群。"""
        resp = await self._execute(lambda: self._client.list_clusters(parent=self._parent))
        return [dict(c) for c in resp.clusters]

    async def get_cluster(self, cluster_id: str) -> dict[str, Any]:
        """获取指定集群的详细信息。"""
        name = f"{self._parent}/clusters/{cluster_id}"
        return dict(await self._execute(lambda: self._client.get_cluster(name=name)))

    async def create_cluster(self, cluster_id: str, cluster: dict) -> Any:
        """创建 AlloyDB 集群。"""
        return await self._execute(
            lambda: self._client.create_cluster(
                parent=self._parent, cluster_id=cluster_id, cluster=cluster
            )
        )

    async def list_instances(self, cluster_id: str) -> list[dict[str, Any]]:
        """列出指定集群下所有实例。"""
        parent = f"{self._parent}/clusters/{cluster_id}"
        resp = await self._execute(lambda: self._client.list_instances(parent=parent))
        return [dict(i) for i in resp.instances]

    async def get_instance(self, cluster_id: str, instance_id: str) -> dict[str, Any]:
        """获取指定实例的详细信息。"""
        name = f"{self._parent}/clusters/{cluster_id}/instances/{instance_id}"
        return dict(await self._execute(lambda: self._client.get_instance(name=name)))

    async def create_instance(self, cluster_id: str, instance_id: str, instance: dict) -> Any:
        """在指定集群下创建实例。"""
        parent = f"{self._parent}/clusters/{cluster_id}"
        return await self._execute(
            lambda: self._client.create_instance(
                parent=parent, instance_id=instance_id, instance=instance
            )
        )

    async def list_users(self, cluster_id: str) -> list[dict[str, Any]]:
        """列出指定集群下所有用户。"""
        parent = f"{self._parent}/clusters/{cluster_id}"
        resp = await self._execute(lambda: self._client.list_users(parent=parent))
        return [dict(u) for u in resp.users]

    async def get_user(self, cluster_id: str, user_id: str) -> dict[str, Any]:
        """获取指定用户的详细信息。"""
        name = f"{self._parent}/clusters/{cluster_id}/users/{user_id}"
        return dict(await self._execute(lambda: self._client.get_user(name=name)))

    async def create_user(self, cluster_id: str, user_id: str, user: dict) -> Any:
        """在指定集群下创建用户。"""
        parent = f"{self._parent}/clusters/{cluster_id}"
        return await self._execute(
            lambda: self._client.create_user(parent=parent, user_id=user_id, user=user)
        )

    async def wait_for_operation(self, operation_name: str) -> Any:
        """等待指定操作完成。"""
        return await self._execute(lambda: self._client.wait_for_operation(name=operation_name))


@register_source("alloydb-admin")
@dataclass
class AlloyDBAdminSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    location: str = "us-central1"

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "alloydb-admin"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AlloyDBAdminSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", "us-central1"),
        )

    async def initialize(self, tracer=None) -> AlloyDBAdminSource:
        """创建并初始化数据源实例。"""
        try:
            from google.cloud import alloydb_v1
        except ImportError as e:
            raise ImportError(
                "google-cloud-alloydb is required: pip install google-cloud-alloydb"
            ) from e

        client = alloydb_v1.AlloyDBAdminClient()
        source = AlloyDBAdminSource(
            name=self._name, client=client, project_id=self.project_id, location=self.location
        )
        await source.connect()
        return source
