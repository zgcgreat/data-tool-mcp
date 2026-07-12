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
    register_tool,
)


def _get_healthcare_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> CloudHealthcareSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, CloudHealthcareSource):
        raise TypeError(f"source {source_name!r} is not a Cloud Healthcare source")
    return source


class HealthcareGenericTool(BaseTool):
    """Generic Cloud Healthcare tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_healthcare_source(source_provider, self._source_name, self.name)
        tt = self._tool_type

        if tt == "cloud-healthcare-get-dataset":
            return {"dataset": {"name": source._dataset_path}}
        elif tt == "cloud-healthcare-list-fhir-stores":
            return {"fhir_stores": []}
        elif tt == "cloud-healthcare-get-fhir-store":
            return {"fhir_store": {}}
        elif tt == "cloud-healthcare-get-fhir-store-metrics":
            return {"metrics": {}}
        elif tt == "cloud-healthcare-get-fhir-resource":
            result = await source.fhir_get_patient(params["fhir_store_id"], params["resource_id"])
            return {"resource": result}
        elif tt == "cloud-healthcare-fhir-patient-search":
            entries = await source.fhir_search(params["fhir_store_id"], "Patient", params.get("params"))
            return {"entries": entries}
        elif tt == "cloud-healthcare-fhir-patient-everything":
            entries = await source.fhir_search(params["fhir_store_id"], f"Patient/{params['patient_id']}", params.get("params"))
            return {"entries": entries}
        elif tt == "cloud-healthcare-fhir-fetch-page":
            entries = await source.fhir_search(params["fhir_store_id"], params["resource_type"], params.get("params"))
            return {"entries": entries}
        elif tt == "cloud-healthcare-list-dicom-stores":
            return {"dicom_stores": []}
        elif tt == "cloud-healthcare-get-dicom-store":
            return {"dicom_store": {}}
        elif tt == "cloud-healthcare-get-dicom-store-metrics":
            return {"metrics": {}}
        elif tt == "cloud-healthcare-search-dicom-studies":
            studies = await source.dicom_search_studies(params["dicom_store_id"], params.get("params"))
            return {"studies": studies}
        elif tt == "cloud-healthcare-search-dicom-series":
            studies = await source.dicom_search_studies(params["dicom_store_id"], params.get("params"))
            return {"series": studies}
        elif tt == "cloud-healthcare-search-dicom-instances":
            studies = await source.dicom_search_studies(params["dicom_store_id"], params.get("params"))
            return {"instances": studies}
        elif tt == "cloud-healthcare-retrieve-rendered-dicom-instance":
            return {"rendered": "not yet supported"}
        else:
            raise ValueError(f"unknown Healthcare tool type: {tt}")

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
    @register_tool(tool_type)
    @dataclass
    class _HCToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _HCToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> HealthcareGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return HealthcareGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _HCToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _HCToolConfig.__qualname__ = _HCToolConfig.__name__
    return _HCToolConfig


for _tool_type, _desc, _params, _ro in _HC_TOOLS:
    _make_hc_tool_config(_tool_type, _desc, _params, _ro)
