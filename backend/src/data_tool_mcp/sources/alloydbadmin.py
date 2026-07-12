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
        self._name = name
        self._client = client
        self._project_id = project_id
        self._location = location
        self._parent = f"projects/{project_id}/locations/{location}"

    @property
    def source_type(self) -> str:
        return "alloydb-admin"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def _execute(self, fn):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)

    async def list_clusters(self) -> list[dict[str, Any]]:
        resp = await self._execute(lambda: self._client.list_clusters(parent=self._parent))
        return [dict(c) for c in resp.clusters]

    async def get_cluster(self, cluster_id: str) -> dict[str, Any]:
        name = f"{self._parent}/clusters/{cluster_id}"
        return dict(await self._execute(lambda: self._client.get_cluster(name=name)))

    async def create_cluster(self, cluster_id: str, cluster: dict) -> Any:
        return await self._execute(lambda: self._client.create_cluster(parent=self._parent, cluster_id=cluster_id, cluster=cluster))

    async def list_instances(self, cluster_id: str) -> list[dict[str, Any]]:
        parent = f"{self._parent}/clusters/{cluster_id}"
        resp = await self._execute(lambda: self._client.list_instances(parent=parent))
        return [dict(i) for i in resp.instances]

    async def get_instance(self, cluster_id: str, instance_id: str) -> dict[str, Any]:
        name = f"{self._parent}/clusters/{cluster_id}/instances/{instance_id}"
        return dict(await self._execute(lambda: self._client.get_instance(name=name)))

    async def create_instance(self, cluster_id: str, instance_id: str, instance: dict) -> Any:
        parent = f"{self._parent}/clusters/{cluster_id}"
        return await self._execute(lambda: self._client.create_instance(parent=parent, instance_id=instance_id, instance=instance))

    async def list_users(self, cluster_id: str) -> list[dict[str, Any]]:
        parent = f"{self._parent}/clusters/{cluster_id}"
        resp = await self._execute(lambda: self._client.list_users(parent=parent))
        return [dict(u) for u in resp.users]

    async def get_user(self, cluster_id: str, user_id: str) -> dict[str, Any]:
        name = f"{self._parent}/clusters/{cluster_id}/users/{user_id}"
        return dict(await self._execute(lambda: self._client.get_user(name=name)))

    async def create_user(self, cluster_id: str, user_id: str, user: dict) -> Any:
        parent = f"{self._parent}/clusters/{cluster_id}"
        return await self._execute(lambda: self._client.create_user(parent=parent, user_id=user_id, user=user))

    async def wait_for_operation(self, operation_name: str) -> Any:
        return await self._execute(lambda: self._client.wait_for_operation(name=operation_name))


@register_source("alloydb-admin")
@dataclass
class AlloyDBAdminSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    location: str = "us-central1"

    @property
    def source_type(self) -> str:
        return "alloydb-admin"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AlloyDBAdminSourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", "us-central1"),
        )

    async def initialize(self, tracer=None) -> AlloyDBAdminSource:
        try:
            from google.cloud import alloydb_v1
        except ImportError as e:
            raise ImportError("google-cloud-alloydb is required: pip install google-cloud-alloydb") from e

        client = alloydb_v1.AlloyDBAdminClient()
        source = AlloyDBAdminSource(name=self._name, client=client, project_id=self.project_id, location=self.location)
        await source.connect()
        return source
