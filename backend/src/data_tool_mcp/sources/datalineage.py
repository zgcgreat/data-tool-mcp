"""Data Lineage source — google-cloud-datalineage.

Maps to Go: internal/sources/datalineage/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class DataLineageSource(Source):
    """Data Lineage source using google-cloud-datalineage API."""

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
        return "datalineage"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass

    async def search_lineage(self, query: str, page_size: int = 100) -> list[dict[str, Any]]:
        """搜索数据血缘事件并返回结果。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步执行血缘事件搜索并收集结果。"""
            request = {"parent": self._parent, "query": query, "page_size": page_size}
            results = []
            for lineage in self._client.search_lineage_events(request=request):
                results.append(dict(lineage))
            return results

        return await loop.run_in_executor(None, _run)


@register_source("datalineage")
@dataclass
class DataLineageSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    location: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "datalineage"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> DataLineageSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", ""),
        )

    async def initialize(self, tracer=None) -> DataLineageSource:
        """创建并初始化数据源实例。"""
        try:
            from google.cloud import datalineage_v1
        except ImportError as e:
            raise ImportError(
                "google-cloud-datalineage is required: pip install google-cloud-datalineage"
            ) from e

        client = datalineage_v1.LineageClient()
        source = DataLineageSource(
            name=self._name, client=client, project_id=self.project_id, location=self.location
        )
        await source.connect()
        return source
