"""Looker source — Looker SDK.

Maps to Go: internal/sources/looker/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class LookerSource(Source):
    """Looker source using Looker SDK with asyncio wrapper."""

    def __init__(self, name: str, sdk: Any):
        self._name = name
        self._sdk = sdk

    @property
    def source_type(self) -> str:
        return "looker"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._sdk.me())

    async def close(self) -> None:
        self._sdk.logout()

    async def _exec(self, fn):
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    # LookML methods
    async def get_lookml_model(self, model_name: str) -> dict[str, Any]:
        return dict(await self._exec(lambda: self._sdk.lookml_model(model_name)))

    async def get_lookml_models(self) -> list[dict[str, Any]]:
        models = await self._exec(lambda: self._sdk.all_lookml_models())
        return [dict(m) for m in models]

    async def get_lookml_explore(self, model: str, explore: str) -> dict[str, Any]:
        return dict(await self._exec(lambda: self._sdk.lookml_explore(model, explore)))

    # Query methods
    async def create_query(self, body: dict) -> dict[str, Any]:
        return dict(await self._exec(lambda: self._sdk.create_query(body)))

    async def run_query(self, query_id: int, result_format: str = "json") -> Any:
        return await self._exec(lambda: self._sdk.run_query(query_id, result_format))

    async def run_inline_query(self, result_format: str, body: dict) -> Any:
        return await self._exec(lambda: self._sdk.run_inline_query(result_format, body))

    # Look/Dashboard methods
    async def get_look(self, look_id: int) -> dict[str, Any]:
        return dict(await self._exec(lambda: self._sdk.look(look_id)))

    async def run_look(self, look_id: int, result_format: str = "json") -> Any:
        return await self._exec(lambda: self._sdk.run_look(look_id, result_format))

    async def get_dashboard(self, dashboard_id: str) -> dict[str, Any]:
        return dict(await self._exec(lambda: self._sdk.dashboard(dashboard_id)))

    async def get_all_dashboards(self) -> list[dict[str, Any]]:
        dashboards = await self._exec(lambda: self._sdk.all_dashboards())
        return [dict(d) for d in dashboards]

    # Connection methods
    async def get_all_connections(self) -> list[dict[str, Any]]:
        conns = await self._exec(lambda: self._sdk.all_connections())
        return [dict(c) for c in conns]

    # User methods
    async def get_all_users(self) -> list[dict[str, Any]]:
        users = await self._exec(lambda: self._sdk.all_users())
        return [dict(u) for u in users]

    # Folder methods
    async def get_all_folders(self) -> list[dict[str, Any]]:
        folders = await self._exec(lambda: self._sdk.all_folders())
        return [dict(f) for f in folders]

    # Project methods
    async def get_all_projects(self) -> list[dict[str, Any]]:
        projects = await self._exec(lambda: self._sdk.all_projects())
        return [dict(p) for p in projects]


@register_source("looker")
@dataclass
class LookerSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    base_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    verify_ssl: bool = True

    @property
    def source_type(self) -> str:
        return "looker"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> LookerSourceConfig:
        return cls(
            _name=name,
            base_url=data.get("baseUrl", ""),
            client_id=data.get("clientId", ""),
            client_secret=data.get("clientSecret", ""),
            verify_ssl=data.get("verifySsl", True),
        )

    async def initialize(self, tracer=None) -> LookerSource:
        try:
            import looker_sdk
        except ImportError as e:
            raise ImportError("looker-sdk is required: pip install looker-sdk") from e

        sdk = looker_sdk.init40(
            base_url=self.base_url,
            client_id=self.client_id,
            client_secret=self.client_secret,
            verify_ssl=self.verify_ssl,
        )
        source = LookerSource(name=self._name, sdk=sdk)
        await source.connect()
        return source
