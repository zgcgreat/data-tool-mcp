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
        self._name = name
        self._client = client
        self._project_id = project_id
        self._location = location
        self._parent = f"projects/{project_id}/locations/{location}"

    @property
    def source_type(self) -> str:
        return "dataplex"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def _exec(self, fn):
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    # Lakes
    async def list_lakes(self) -> list[dict[str, Any]]:
        lakes = await self._exec(lambda: list(self._client.list_lakes(parent=self._parent)))
        return [dict(l) for l in lakes]

    async def get_lake(self, lake_id: str) -> dict[str, Any]:
        name = f"{self._parent}/lakes/{lake_id}"
        return dict(await self._exec(lambda: self._client.get_lake(name=name)))

    async def create_lake(self, lake_id: str, lake: dict) -> Any:
        return await self._exec(lambda: self._client.create_lake(parent=self._parent, lake_id=lake_id, lake=lake))

    async def delete_lake(self, lake_id: str) -> Any:
        name = f"{self._parent}/lakes/{lake_id}"
        return await self._exec(lambda: self._client.delete_lake(name=name))

    # Zones
    async def list_zones(self, lake_id: str) -> list[dict[str, Any]]:
        parent = f"{self._parent}/lakes/{lake_id}"
        zones = await self._exec(lambda: list(self._client.list_zones(parent=parent)))
        return [dict(z) for z in zones]

    async def get_zone(self, lake_id: str, zone_id: str) -> dict[str, Any]:
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        return dict(await self._exec(lambda: self._client.get_zone(name=name)))

    async def create_zone(self, lake_id: str, zone_id: str, zone: dict) -> Any:
        parent = f"{self._parent}/lakes/{lake_id}"
        return await self._exec(lambda: self._client.create_zone(parent=parent, zone_id=zone_id, zone=zone))

    async def delete_zone(self, lake_id: str, zone_id: str) -> Any:
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        return await self._exec(lambda: self._client.delete_zone(name=name))

    # Assets
    async def list_assets(self, lake_id: str, zone_id: str) -> list[dict[str, Any]]:
        parent = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        assets = await self._exec(lambda: list(self._client.list_assets(parent=parent)))
        return [dict(a) for a in assets]

    async def get_asset(self, lake_id: str, zone_id: str, asset_id: str) -> dict[str, Any]:
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}/assets/{asset_id}"
        return dict(await self._exec(lambda: self._client.get_asset(name=name)))

    async def create_asset(self, lake_id: str, zone_id: str, asset_id: str, asset: dict) -> Any:
        parent = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}"
        return await self._exec(lambda: self._client.create_asset(parent=parent, asset_id=asset_id, asset=asset))

    async def delete_asset(self, lake_id: str, zone_id: str, asset_id: str) -> Any:
        name = f"{self._parent}/lakes/{lake_id}/zones/{zone_id}/assets/{asset_id}"
        return await self._exec(lambda: self._client.delete_asset(name=name))

    # Tasks
    async def list_tasks(self, lake_id: str) -> list[dict[str, Any]]:
        parent = f"{self._parent}/lakes/{lake_id}"
        tasks = await self._exec(lambda: list(self._client.list_tasks(parent=parent)))
        return [dict(t) for t in tasks]

    async def get_task(self, lake_id: str, task_id: str) -> dict[str, Any]:
        name = f"{self._parent}/lakes/{lake_id}/tasks/{task_id}"
        return dict(await self._exec(lambda: self._client.get_task(name=name)))

    async def create_task(self, lake_id: str, task_id: str, task: dict) -> Any:
        parent = f"{self._parent}/lakes/{lake_id}"
        return await self._exec(lambda: self._client.create_task(parent=parent, task_id=task_id, task=task))

    async def delete_task(self, lake_id: str, task_id: str) -> Any:
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
        return "dataplex"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataplexSourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", ""),
        )

    async def initialize(self, tracer=None) -> DataplexSource:
        try:
            from google.cloud import dataplex_v1
        except ImportError as e:
            raise ImportError("google-cloud-dataplex is required: pip install google-cloud-dataplex") from e

        client = dataplex_v1.DataplexServiceClient()
        source = DataplexSource(name=self._name, client=client, project_id=self.project_id, location=self.location)
        await source.connect()
        return source
