"""Cloud Healthcare source — google-cloud-healthcare REST API.

Maps to Go: internal/sources/cloudhealthcare/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class CloudHealthcareSource(Source):
    """Cloud Healthcare source using google-cloud-healthcare API for FHIR + DICOM."""

    def __init__(self, name: str, client: Any, project_id: str, location: str, dataset_id: str):
        """初始化数据源配置。"""
        self._name = name
        self._client = client
        self._project_id = project_id
        self._location = location
        self._dataset_id = dataset_id
        self._dataset_path = f"projects/{project_id}/locations/{location}/datasets/{dataset_id}"

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-healthcare"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass

    async def _exec(self, fn):
        """在线程池中执行同步调用。"""
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    # FHIR methods
    async def fhir_get_patient(self, fhir_store_id: str, patient_id: str) -> dict[str, Any]:
        """获取 FHIR 患者资源。"""
        return dict(await self._exec(lambda: self._client.fhir_stores().fhir.Patient.read(
            name=f"{self._dataset_path}/fhirStores/{fhir_store_id}/fhir/Patient/{patient_id}").execute()))

    async def fhir_search(self, fhir_store_id: str, resource_type: str, params: dict | None = None) -> list[dict[str, Any]]:
        """搜索 FHIR 资源。"""
        resp = await self._exec(lambda: self._client.fhir_stores().fhir.search(
            name=f"{self._dataset_path}/fhirStores/{fhir_store_id}/fhir/{resource_type}",
            body=params or {}).execute())
        return resp.get("entry", [])

    async def fhir_create_resource(self, fhir_store_id: str, resource_type: str, body: dict) -> dict[str, Any]:
        """创建 FHIR 资源。"""
        return dict(await self._exec(lambda: self._client.fhir_stores().fhir.create(
            name=f"{self._dataset_path}/fhirStores/{fhir_store_id}/fhir/{resource_type}",
            body=body).execute()))

    async def fhir_update_resource(self, fhir_store_id: str, resource_type: str, resource_id: str, body: dict) -> dict[str, Any]:
        """更新 FHIR 资源。"""
        return dict(await self._exec(lambda: self._client.fhir_stores().fhir.update(
            name=f"{self._dataset_path}/fhirStores/{fhir_store_id}/fhir/{resource_type}/{resource_id}",
            body=body).execute()))

    # DICOM methods
    async def dicom_search_studies(self, dicom_store_id: str, params: dict | None = None) -> list[dict[str, Any]]:
        """搜索 DICOM 研究。"""
        resp = await self._exec(lambda: self._client.dicom_stores().studies.search(
            parent=f"{self._dataset_path}/dicomStores/{dicom_store_id}",
            body=params or {}).execute())
        return resp if isinstance(resp, list) else [resp]

    async def dicom_get_study(self, dicom_store_id: str, study_uid: str) -> dict[str, Any]:
        """获取 DICOM 研究详情。"""
        return dict(await self._exec(lambda: self._client.dicom_stores().studies.get(
            name=f"{self._dataset_path}/dicomStores/{dicom_store_id}/dicomWeb/studies/{study_uid}").execute()))


@register_source("cloud-healthcare")
@dataclass
class CloudHealthcareSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    location: str = ""
    dataset_id: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-healthcare"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudHealthcareSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            location=data.get("location", ""),
            dataset_id=data.get("datasetId", ""),
        )

    async def initialize(self, tracer=None) -> CloudHealthcareSource:
        """创建并初始化数据源实例。"""
        try:
            from googleapiclient.discovery import build
        except ImportError as e:
            raise ImportError("google-api-python-client is required: pip install google-api-python-client") from e

        client = build("healthcare", "v1")
        source = CloudHealthcareSource(
            name=self._name, client=client,
            project_id=self.project_id, location=self.location, dataset_id=self.dataset_id,
        )
        await source.connect()
        return source
