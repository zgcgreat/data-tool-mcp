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
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# GCS 操作分发表 — 每个 handler 为 async 函数,签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _gcs_list_buckets(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Cloud Storage的存储桶列表。"""
    return {"buckets": await source.list_buckets()}

async def _gcs_create_bucket(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """创建Cloud Storage的存储桶。"""
    return {"bucket_name": await source.create_bucket(params["bucket_name"], params.get("location", "US"))}

async def _gcs_delete_bucket(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """删除Cloud Storage的存储桶。"""
    await source.delete_bucket(params["bucket_name"])
    return {"deleted": True}

async def _gcs_get_bucket_metadata(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Storage的存储桶元数据。"""
    return {"metadata": await source.get_bucket_metadata(params["bucket_name"])}

async def _gcs_get_bucket_iam_policy(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Storage的存储桶 IAM 策略。"""
    return {"policy": await source.get_bucket_iam_policy(params["bucket_name"])}

async def _gcs_list_objects(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Cloud Storage的对象列表。"""
    return {"objects": await source.list_objects(params["bucket_name"], params.get("prefix", ""))}

async def _gcs_read_object(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """读取Cloud Storage的对象。"""
    data = await source.read_object(params["bucket_name"], params["object_name"])
    return {"data": data.decode() if isinstance(data, bytes) else data}

async def _gcs_write_object(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """写入Cloud Storage的对象。"""
    data = params.get("data", "")
    await source.write_object(params["bucket_name"], params["object_name"], data.encode() if isinstance(data, str) else data)
    return {"written": True}

async def _gcs_upload_object(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """上传Cloud Storage的对象。"""
    await source.upload_object(params["bucket_name"], params["object_name"], params["source_path"])
    return {"uploaded": True}

async def _gcs_download_object(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """下载Cloud Storage的对象。"""
    await source.download_object(params["bucket_name"], params["object_name"], params["dest_path"])
    return {"downloaded": True}

async def _gcs_copy_object(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """复制Cloud Storage的对象。"""
    await source.copy_object(params["src_bucket"], params["src_obj"], params["dst_bucket"], params["dst_obj"])
    return {"copied": True}

async def _gcs_move_object(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """移动Cloud Storage的对象。"""
    await source.move_object(params["src_bucket"], params["src_obj"], params["dst_bucket"], params["dst_obj"])
    return {"moved": True}

async def _gcs_delete_object(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """删除Cloud Storage的对象。"""
    await source.delete_object(params["bucket_name"], params["object_name"])
    return {"deleted": True}

async def _gcs_get_object_metadata(source: CloudStorageSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Cloud Storage的对象元数据。"""
    return {"metadata": await source.get_object_metadata(params["bucket_name"], params["object_name"])}


_GCS_DISPATCH: dict[str, Any] = {
    "cloud-storage-list-buckets": _gcs_list_buckets,
    "cloud-storage-create-bucket": _gcs_create_bucket,
    "cloud-storage-delete-bucket": _gcs_delete_bucket,
    "cloud-storage-get-bucket-metadata": _gcs_get_bucket_metadata,
    "cloud-storage-get-bucket-iam-policy": _gcs_get_bucket_iam_policy,
    "cloud-storage-list-objects": _gcs_list_objects,
    "cloud-storage-read-object": _gcs_read_object,
    "cloud-storage-write-object": _gcs_write_object,
    "cloud-storage-upload-object": _gcs_upload_object,
    "cloud-storage-download-object": _gcs_download_object,
    "cloud-storage-copy-object": _gcs_copy_object,
    "cloud-storage-move-object": _gcs_move_object,
    "cloud-storage-delete-object": _gcs_delete_object,
    "cloud-storage-get-object-metadata": _gcs_get_object_metadata,
}


# ---------------------------------------------------------------------------
# Generic GCS tool
# ---------------------------------------------------------------------------

class GCSGenericTool(BaseTool):
    """Generic Cloud Storage tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        """初始化工具配置。"""
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, CloudStorageSource)
        try:
            handler = _GCS_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Cloud Storage tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
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
    """构造Cloud Storage工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _GCSToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _GCSToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> GCSGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return GCSGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _GCSToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _GCSToolConfig.__qualname__ = _GCSToolConfig.__name__
    return _GCSToolConfig


for _tool_type, _desc, _params, _ro in _GCS_TOOLS:
    _make_gcs_tool_config(_tool_type, _desc, _params, _ro)
