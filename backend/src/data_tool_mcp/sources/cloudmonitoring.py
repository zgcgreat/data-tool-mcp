"""Cloud Monitoring source — google-cloud-monitoring.

Maps to Go: internal/sources/cloudmonitoring/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class CloudMonitoringSource(Source):
    """Cloud Monitoring source using google-cloud-monitoring with Prometheus query support."""

    def __init__(self, name: str, client: Any, project_id: str):
        self._name = name
        self._client = client
        self._project_id = project_id
        self._project_path = f"projects/{project_id}"

    @property
    def source_type(self) -> str:
        return "cloud-monitoring"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def query_prometheus(self, query: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            try:
                from google.cloud import monitoring_v1
            except ImportError as e:
                raise ImportError(
                    "google-cloud-monitoring is required: pip install google-cloud-monitoring"
                ) from e
            query_service = monitoring_v1.QueryServiceClient()
            request = monitoring_v1.QueryTimeSeriesRequest(
                name=self._project_path,
                query=query,
            )
            results = []
            for ts in query_service.query_time_series(request=request):
                results.append({"labels": dict(ts.label_values), "points": [dict(p) for p in ts.point_data]})
            return results

        return await loop.run_in_executor(None, _run)


@register_source("cloud-monitoring")
@dataclass
class CloudMonitoringSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""

    @property
    def source_type(self) -> str:
        return "cloud-monitoring"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudMonitoringSourceConfig:
        return cls(_name=name, project_id=data.get("projectId", ""))

    async def initialize(self, tracer=None) -> CloudMonitoringSource:
        try:
            from google.cloud import monitoring_v1
        except ImportError as e:
            raise ImportError("google-cloud-monitoring is required: pip install google-cloud-monitoring") from e

        client = monitoring_v1.MetricServiceClient()
        source = CloudMonitoringSource(name=self._name, client=client, project_id=self.project_id)
        await source.connect()
        return source
