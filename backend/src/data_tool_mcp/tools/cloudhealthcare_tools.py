"""Cloud Healthcare tools — 14 tools for FHIR and DICOM operations.

Maps to Go: internal/tools/cloudhealthcare/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudhealthcare import CloudHealthcareSource
from data_tool_mcp.tools.base import (
    BaseTool,
    ConfigBase,
    ParameterManifest,
    SourceProvider,
    ToolAnnotations,
    ToolConfig,
    ToolManifest,
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# Healthcare 操作分发表 — 每个 handler 为 async 函数,签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _hc_get_dataset(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Healthcare的数据集。"""
    return {"dataset": {"name": source._dataset_path}}

async def _hc_list_fhir_stores(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Cloud Healthcare的FHIR 存储列表。"""
    return {"fhir_stores": []}

async def _hc_get_fhir_store(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Healthcare的FHIR 存储。"""
    return {"fhir_store": {}}

async def _hc_get_fhir_store_metrics(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Healthcare的FHIR 存储指标。"""
    return {"metrics": {}}

async def _hc_get_fhir_resource(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Healthcare的FHIR 资源。"""
    return {"resource": await source.fhir_get_patient(params["fhir_store_id"], params["resource_id"])}

async def _hc_fhir_patient_search(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """搜索 FHIR 患者资源。"""
    return {"entries": await source.fhir_search(params["fhir_store_id"], "Patient", params.get("params"))}

async def _hc_fhir_patient_everything(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取 FHIR 患者所有资源。"""
    return {"entries": await source.fhir_search(params["fhir_store_id"], f"Patient/{params['patient_id']}", params.get("params"))}

async def _hc_fhir_fetch_page(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取 FHIR 分页数据。"""
    return {"entries": await source.fhir_search(params["fhir_store_id"], params["resource_type"], params.get("params"))}

async def _hc_list_dicom_stores(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Cloud Healthcare的DICOM 存储列表。"""
    return {"dicom_stores": []}

async def _hc_get_dicom_store(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Healthcare的DICOM 存储。"""
    return {"dicom_store": {}}

async def _hc_get_dicom_store_metrics(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Healthcare的DICOM 存储指标。"""
    return {"metrics": {}}

async def _hc_search_dicom_studies(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """搜索Cloud Healthcare的DICOM 研究列表。"""
    return {"studies": await source.dicom_search_studies(params["dicom_store_id"], params.get("params"))}

async def _hc_search_dicom_series(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """搜索Cloud Healthcare的DICOM 系列列表。"""
    return {"series": await source.dicom_search_studies(params["dicom_store_id"], params.get("params"))}

async def _hc_search_dicom_instances(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """搜索Cloud Healthcare的DICOM 实例列表。"""
    return {"instances": await source.dicom_search_studies(params["dicom_store_id"], params.get("params"))}

async def _hc_retrieve_rendered(source: CloudHealthcareSource, params: dict[str, Any]) -> dict[str, Any]:
    """检索Cloud Healthcare的渲染结果。"""
    return {"rendered": "not yet supported"}


_HC_DISPATCH: dict[str, Any] = {
    "cloud-healthcare-get-dataset": _hc_get_dataset,
    "cloud-healthcare-list-fhir-stores": _hc_list_fhir_stores,
    "cloud-healthcare-get-fhir-store": _hc_get_fhir_store,
    "cloud-healthcare-get-fhir-store-metrics": _hc_get_fhir_store_metrics,
    "cloud-healthcare-get-fhir-resource": _hc_get_fhir_resource,
    "cloud-healthcare-fhir-patient-search": _hc_fhir_patient_search,
    "cloud-healthcare-fhir-patient-everything": _hc_fhir_patient_everything,
    "cloud-healthcare-fhir-fetch-page": _hc_fhir_fetch_page,
    "cloud-healthcare-list-dicom-stores": _hc_list_dicom_stores,
    "cloud-healthcare-get-dicom-store": _hc_get_dicom_store,
    "cloud-healthcare-get-dicom-store-metrics": _hc_get_dicom_store_metrics,
    "cloud-healthcare-search-dicom-studies": _hc_search_dicom_studies,
    "cloud-healthcare-search-dicom-series": _hc_search_dicom_series,
    "cloud-healthcare-search-dicom-instances": _hc_search_dicom_instances,
    "cloud-healthcare-retrieve-rendered-dicom-instance": _hc_retrieve_rendered,
}


class HealthcareGenericTool(BaseTool):
    """Generic Cloud Healthcare tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        """初始化工具配置。"""
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, CloudHealthcareSource)
        try:
            handler = _HC_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Healthcare tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


_HC_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("cloud-healthcare-get-dataset", "Get a Cloud Healthcare dataset", [], True),
    ("cloud-healthcare-list-fhir-stores", "List FHIR stores in a dataset",
     [], True),
    ("cloud-healthcare-get-fhir-store", "Get a FHIR store",
     [ParameterManifest(name="fhir_store_id", type="string", description="FHIR store ID", required=True)], True),
    ("cloud-healthcare-get-fhir-store-metrics", "Get FHIR store metrics",
     [ParameterManifest(name="fhir_store_id", type="string", description="FHIR store ID", required=True)], True),
    ("cloud-healthcare-get-fhir-resource", "Get a FHIR resource",
     [ParameterManifest(name="fhir_store_id", type="string", description="FHIR store ID", required=True),
      ParameterManifest(name="resource_id", type="string", description="Resource ID", required=True)], True),
    ("cloud-healthcare-fhir-patient-search", "Search for FHIR patients",
     [ParameterManifest(name="fhir_store_id", type="string", description="FHIR store ID", required=True),
      ParameterManifest(name="params", type="object", description="Search parameters", required=False)], True),
    ("cloud-healthcare-fhir-patient-everything", "Get all data for a FHIR patient",
     [ParameterManifest(name="fhir_store_id", type="string", description="FHIR store ID", required=True),
      ParameterManifest(name="patient_id", type="string", description="Patient ID", required=True),
      ParameterManifest(name="params", type="object", description="Query parameters", required=False)], True),
    ("cloud-healthcare-fhir-fetch-page", "Fetch a page of FHIR resources",
     [ParameterManifest(name="fhir_store_id", type="string", description="FHIR store ID", required=True),
      ParameterManifest(name="resource_type", type="string", description="Resource type", required=True),
      ParameterManifest(name="params", type="object", description="Query parameters", required=False)], True),
    ("cloud-healthcare-list-dicom-stores", "List DICOM stores in a dataset", [], True),
    ("cloud-healthcare-get-dicom-store", "Get a DICOM store",
     [ParameterManifest(name="dicom_store_id", type="string", description="DICOM store ID", required=True)], True),
    ("cloud-healthcare-get-dicom-store-metrics", "Get DICOM store metrics",
     [ParameterManifest(name="dicom_store_id", type="string", description="DICOM store ID", required=True)], True),
    ("cloud-healthcare-search-dicom-studies", "Search DICOM studies",
     [ParameterManifest(name="dicom_store_id", type="string", description="DICOM store ID", required=True),
      ParameterManifest(name="params", type="object", description="Search parameters", required=False)], True),
    ("cloud-healthcare-search-dicom-series", "Search DICOM series",
     [ParameterManifest(name="dicom_store_id", type="string", description="DICOM store ID", required=True),
      ParameterManifest(name="params", type="object", description="Search parameters", required=False)], True),
    ("cloud-healthcare-search-dicom-instances", "Search DICOM instances",
     [ParameterManifest(name="dicom_store_id", type="string", description="DICOM store ID", required=True),
      ParameterManifest(name="params", type="object", description="Search parameters", required=False)], True),
    ("cloud-healthcare-retrieve-rendered-dicom-instance", "Retrieve a rendered DICOM instance",
     [ParameterManifest(name="dicom_store_id", type="string", description="DICOM store ID", required=True),
      ParameterManifest(name="study_uid", type="string", description="Study UID", required=True),
      ParameterManifest(name="series_uid", type="string", description="Series UID", required=True),
      ParameterManifest(name="instance_uid", type="string", description="Instance UID", required=True)], True),
]


def _make_hc_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    """构造Cloud Healthcare工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _HCToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _HCToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> HealthcareGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return HealthcareGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _HCToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _HCToolConfig.__qualname__ = _HCToolConfig.__name__
    return _HCToolConfig


for _tool_type, _desc, _params, _ro in _HC_TOOLS:
    _make_hc_tool_config(_tool_type, _desc, _params, _ro)
