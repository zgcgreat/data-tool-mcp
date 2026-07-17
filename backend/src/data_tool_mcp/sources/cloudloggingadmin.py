"""Cloud Logging Admin source — google-cloud-logging.

Maps to Go: internal/sources/cloudloggingadmin/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class CloudLoggingAdminSource(Source):
    """Cloud Logging Admin source using google-cloud-logging."""

    def __init__(self, name: str, client: Any, project_id: str):
        """初始化数据源配置。"""
        self._name = name
        self._client = client
        self._project_id = project_id

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-logging-admin"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass

    async def query_logs(self, filter_str: str = "", limit: int = 100) -> list[dict[str, Any]]:
        """按过滤条件查询日志条目。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步查询日志条目。"""
            entries = self._client.list_entries(
                filter_=filter_str,
                max_results=limit,
                order_by="timestamp desc",
            )
            return [{"timestamp": str(e.timestamp), "severity": str(e.severity), "text_payload": e.text_payload} for e in entries]

        return await loop.run_in_executor(None, _run)

    async def list_log_names(self) -> list[str]:
        """列出所有日志资源名称。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[str]:
            """同步获取日志资源名称列表。"""
            return list(self._client.list_resource_names())

        return await loop.run_in_executor(None, _run)

    async def list_resource_types(self) -> list[dict[str, Any]]:
        """列出所有资源类型。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步获取资源类型列表。"""
            try:
                from google.cloud import monitoring_v3
            except ImportError as e:
                raise ImportError(
                    "google-cloud-monitoring is required: pip install google-cloud-monitoring"
                ) from e
            client = monitoring_v3.GroupServiceClient(project=self._project_id)
            return [{"name": g.display_name, "id": g.name} for g in client.list_groups()]

        return await loop.run_in_executor(None, _run)


@register_source("cloud-logging-admin")
@dataclass
class CloudLoggingAdminSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-logging-admin"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudLoggingAdminSourceConfig:
        """从字典构造配置实例。"""
        return cls(_name=name, project_id=data.get("projectId", ""))

    async def initialize(self, tracer=None) -> CloudLoggingAdminSource:
        """创建并初始化数据源实例。"""
        try:
            from google.cloud import logging
        except ImportError as e:
            raise ImportError("google-cloud-logging is required: pip install google-cloud-logging") from e

        client = logging.Client(project=self.project_id)
        source = CloudLoggingAdminSource(name=self._name, client=client, project_id=self.project_id)
        await source.connect()
        return source
