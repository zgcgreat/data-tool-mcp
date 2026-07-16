"""Cloud Storage tools — 14 tools for GCS bucket/object management.

Maps to Go: internal/tools/cloudstorage/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.cloudstorage import CloudStorageSource
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


async def _get_gcs_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> CloudStorageSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, CloudStorageSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Cloud Storage source")
    return source


# ---------------------------------------------------------------------------
# Generic GCS tool
# ---------------------------------------------------------------------------

class GCSGenericTool(BaseTool):
    """Generic Cloud Storage tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_gcs_source(source_provider, self._source_name, self.name)
        try:
            if self._tool_type == "cloud-storage-list-buckets":
                buckets = await source.list_buckets()
                return {"buckets": buckets}
            elif self._tool_type == "cloud-storage-create-bucket":
                name = await source.create_bucket(params["bucket_name"], params.get("location", "US"))
                return {"bucket_name": name}
            elif self._tool_type == "cloud-storage-delete-bucket":
                await source.delete_bucket(params["bucket_name"])
                return {"deleted": True}
            elif self._tool_type == "cloud-storage-get-bucket-metadata":
                metadata = await source.get_bucket_metadata(params["bucket_name"])
                return {"metadata": metadata}
            elif self._tool_type == "cloud-storage-get-bucket-iam-policy":
                policy = await source.get_bucket_iam_policy(params["bucket_name"])
                return {"policy": policy}
            elif self._tool_type == "cloud-storage-list-objects":
                objects = await source.list_objects(params["bucket_name"], params.get("prefix", ""))
                return {"objects": objects}
            elif self._tool_type == "cloud-storage-read-object":
                data = await source.read_object(params["bucket_name"], params["object_name"])
                return {"data": data.decode() if isinstance(data, bytes) else data}
            elif self._tool_type == "cloud-storage-write-object":
                data = params.get("data", "")
                await source.write_object(params["bucket_name"], params["object_name"], data.encode() if isinstance(data, str) else data)
                return {"written": True}
            elif self._tool_type == "cloud-storage-upload-object":
                await source.upload_object(params["bucket_name"], params["object_name"], params["source_path"])
                return {"uploaded": True}
            elif self._tool_type == "cloud-storage-download-object":
                await source.download_object(params["bucket_name"], params["object_name"], params["dest_path"])
                return {"downloaded": True}
            elif self._tool_type == "cloud-storage-copy-object":
                await source.copy_object(params["src_bucket"], params["src_obj"], params["dst_bucket"], params["dst_obj"])
                return {"copied": True}
            elif self._tool_type == "cloud-storage-move-object":
                await source.move_object(params["src_bucket"], params["src_obj"], params["dst_bucket"], params["dst_obj"])
                return {"moved": True}
            elif self._tool_type == "cloud-storage-delete-object":
                await source.delete_object(params["bucket_name"], params["object_name"])
                return {"deleted": True}
            elif self._tool_type == "cloud-storage-get-object-metadata":
                metadata = await source.get_object_metadata(params["bucket_name"], params["object_name"])
                return {"metadata": metadata}
            else:
                raise ValueError(f"unknown Cloud Storage tool type: {self._tool_type}")
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_GCS_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("cloud-storage-list-buckets", "List all Cloud Storage buckets", [], True),
    ("cloud-storage-create-bucket", "Create a Cloud Storage bucket",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="location", type="string", description="Bucket location", required=False)], False),
    ("cloud-storage-delete-bucket", "Delete a Cloud Storage bucket",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True)], False),
    ("cloud-storage-get-bucket-metadata", "Get metadata for a Cloud Storage bucket",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True)], True),
    ("cloud-storage-get-bucket-iam-policy", "Get IAM policy for a Cloud Storage bucket",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True)], True),
    ("cloud-storage-list-objects", "List objects in a Cloud Storage bucket",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="prefix", type="string", description="Object prefix filter", required=False)], True),
    ("cloud-storage-read-object", "Read an object from Cloud Storage",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="object_name", type="string", description="Object name", required=True)], True),
    ("cloud-storage-write-object", "Write an object to Cloud Storage",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="object_name", type="string", description="Object name", required=True),
      ParameterManifest(name="data", type="string", description="Data to write", required=True)], False),
    ("cloud-storage-upload-object", "Upload a file to Cloud Storage",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="object_name", type="string", description="Object name", required=True),
      ParameterManifest(name="source_path", type="string", description="Local file path to upload", required=True)], False),
    ("cloud-storage-download-object", "Download an object from Cloud Storage",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="object_name", type="string", description="Object name", required=True),
      ParameterManifest(name="dest_path", type="string", description="Local file path to download to", required=True)], False),
    ("cloud-storage-copy-object", "Copy an object in Cloud Storage",
     [ParameterManifest(name="src_bucket", type="string", description="Source bucket", required=True),
      ParameterManifest(name="src_obj", type="string", description="Source object name", required=True),
      ParameterManifest(name="dst_bucket", type="string", description="Destination bucket", required=True),
      ParameterManifest(name="dst_obj", type="string", description="Destination object name", required=True)], False),
    ("cloud-storage-move-object", "Move an object in Cloud Storage",
     [ParameterManifest(name="src_bucket", type="string", description="Source bucket", required=True),
      ParameterManifest(name="src_obj", type="string", description="Source object name", required=True),
      ParameterManifest(name="dst_bucket", type="string", description="Destination bucket", required=True),
      ParameterManifest(name="dst_obj", type="string", description="Destination object name", required=True)], False),
    ("cloud-storage-delete-object", "Delete an object from Cloud Storage",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="object_name", type="string", description="Object name", required=True)], False),
    ("cloud-storage-get-object-metadata", "Get metadata for a Cloud Storage object",
     [ParameterManifest(name="bucket_name", type="string", description="Bucket name", required=True),
      ParameterManifest(name="object_name", type="string", description="Object name", required=True)], True),
]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_gcs_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    @register_tool(tool_type)
    @dataclass
    class _GCSToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _GCSToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> GCSGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return GCSGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _GCSToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _GCSToolConfig.__qualname__ = _GCSToolConfig.__name__
    return _GCSToolConfig


for _tool_type, _desc, _params, _ro in _GCS_TOOLS:
    _make_gcs_tool_config(_tool_type, _desc, _params, _ro)
