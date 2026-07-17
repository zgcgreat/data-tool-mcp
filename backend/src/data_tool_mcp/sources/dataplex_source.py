"""Dataplex source — google-cloud-dataplex.

Maps to Go: internal/sources/dataplex/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class DataplexSource(Source):
    """Dataplex source using google-cloud-dataplex API."""

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
        return "dataplex"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass

    async def _exec(self, fn):
        """在线程池中执行同步调用。"""
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    # Lakes
    async def list_lakes(self) -> list[dict[str, Any]]:
        """列出所有 Dataplex 湖。"""
        lakes = await self._exec(lambda: list(self._client.list_lakes(parent=self._parent)))
        return [dict(l) for l in lakes]

    async def get_lake(self, lake_id: str) -> dict[str, Any]:
        """获取指定湖的详细信息。"""
        name = f"{self._parent}/lakes/{lake_id}"
        return dict(await self._exec(lambda: self._client.get_lake(name=name)))

    async def create_lake(self, lake_id: str, lake: dict) -> Any:
        """创建 Dataplex 湖。"""
        return await self._exec(lambda: self._client.create_lake(parent=self._parent, lake_id=lake_id, lake=lake))

    async def delete_lake(self, lake_id: str) -> Any:
        """删除指定湖。"""
        name = f"{self._parent}/lakes/{lake_id}"
        return await self._exec(lambda: self._client.delete_lake(name=name))

    # Zones
    async def list_zones(self, lake_id: str) -> list[dict[str, Any]]:
        """列出指定湖下所有分区。"""
        parent = f"{self._parent}/lakes/{lake_id}"
        zones = await self._exec(lambda: list(self._client.list_zones(parent=parent)))
        return [dict(z) for z in zones]

    async def get_zone(self, lake_id: str, zone_id: str) -> dict[str, Any]:
        """获取指定分区的详细信息。"""
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        return dict(await self._exec(lambda: self._client.get_zone(name=name)))

    async def create_zone(self, lake_id: str, zone_id: str, zone: dict) -> Any:
        """在指定湖下创建分区。"""
        parent = f"{self._parent}/lakes/{lake_id}"
        return await self._exec(lambda: self._client.create_zone(parent=parent, zone_id=zone_id, zone=zone))

    async def delete_zone(self, lake_id: str, zone_id: str) -> Any:
        """删除指定分区。"""
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        return await self._exec(lambda: self._client.delete_zone(name=name))

    # Assets
    async def list_assets(self, lake_id: str, zone_id: str) -> list[dict[str, Any]]:
        """列出指定分区下所有资产。"""
        parent = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        assets = await self._exec(lambda: list(self._client.list_assets(parent=parent)))
        return [dict(a) for a in assets]

    async def get_asset(self, lake_id: str, zone_id: str, asset_id: str) -> dict[str, Any]:
        """获取指定资产的详细信息。"""
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}/assets/{asset_id}"
        return dict(await self._exec(lambda: self._client.get_asset(name=name)))

    async def create_asset(self, lake_id: str, zone_id: str, asset_id: str, asset: dict) -> Any:
        """在指定分区下创建资产。"""
        parent = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        return await self._exec(lambda: self._client.create_asset(parent=parent, asset_id=asset_id, asset=asset))

    async def delete_asset(self, lake_id: str, zone_id: str, asset_id: str) -> Any:
        """删除指定资产。"""
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}/assets/{asset_id}"
        return await self._exec(lambda: self._client.delete_asset(name=name))

    # Tasks
    async def list_tasks(self, lake_id: str) -> list[dict[str, Any]]:
        """列出指定湖下所有任务。"""
        parent = f"{self._parent}/lakes/{lake_id}"
        tasks = await self._exec(lambda: list(self._client.list_tasks(parent=parent)))
        return [dict(t) for t in tasks]

    async def get_task(self, lake_id: str, task_id: str) -> dict[str, Any]:
        """获取指定任务的详细信息。"""
        name = f"{self._parent}/lakes/{lake_id}/tasks/{task_id}"
        return dict(await self._exec(lambda: self._client.get_task(name=name)))

    async def create_task(self, lake_id: str, task_id: str, task: dict) -> Any:
        """在指定湖下创建任务。"""
        parent = f"{self._parent}/lakes/{lake_id}"
        return await self._exec(lambda: self._client.create_task(parent=parent, task_id=task_id, task=task))

    async def delete_task(self, lake_id: str, task_id: str) -> Any:
        """删除指定任务。"""
        name = f"{self._parent}/lakes/{lake_id}/tasks/{task_id}"
        return await self._exec(lambda: self._client.delete_task(name=name))


@register_source("dataplex")
@dataclass
class DataplexSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    location: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "dataplex"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataplexSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", ""),
        )

    async def initialize(self, tracer=None) -> DataplexSource:
        """创建并初始化数据源实例。"""
        try:
            from google.cloud import dataplex_v1
        except ImportError as e:
            raise ImportError("google-cloud-dataplex is required: pip install google-cloud-dataplex") from e

        client = dataplex_v1.DataplexServiceClient()
        source = DataplexSource(name=self._name, client=client, project_id=self.project_id, location=self.location)
        await source.connect()
        return source
