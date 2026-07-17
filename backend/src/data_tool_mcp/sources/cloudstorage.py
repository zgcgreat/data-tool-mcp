"""Cloud Storage source — google-cloud-storage.

Maps to Go: internal/sources/cloudstorage/
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class CloudStorageSource(Source):
    """Cloud Storage source using google-cloud-storage."""

    def __init__(self, name: str, client: Any, project_id: str):
        """初始化数据源配置。"""
        self._name = name
        self._client = client
        self._project_id = project_id

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-storage"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        self._client.close()

    async def _exec(self, fn):
        """在线程池中执行同步调用。"""
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    async def list_buckets(self) -> list[str]:
        """列出所有存储桶名称。"""
        buckets = await self._exec(lambda: list(self._client.list_buckets()))
        return [b.name for b in buckets]

    async def create_bucket(self, bucket_name: str, location: str = "US") -> str:
        """创建存储桶并返回其名称。"""
        bucket = await self._exec(lambda: self._client.create_bucket(bucket_name, location=location))
        return bucket.name

    async def delete_bucket(self, bucket_name: str) -> None:
        """删除指定存储桶。"""
        bucket = self._client.bucket(bucket_name)
        await self._exec(lambda: bucket.delete(force=True))

    async def get_bucket_metadata(self, bucket_name: str) -> dict[str, Any]:
        """获取存储桶元数据。"""
        bucket = await self._exec(lambda: self._client.get_bucket(bucket_name))
        return {"name": bucket.name, "location": bucket.location, "storage_class": bucket.storage_class}

    async def get_bucket_iam_policy(self, bucket_name: str) -> dict[str, Any]:
        """获取存储桶 IAM 策略。"""
        bucket = self._client.bucket(bucket_name)
        policy = await self._exec(lambda: bucket.get_iam_policy())
        return {"bindings": [{"role": b["role"], "members": b["members"]} for b in policy.bindings]}

    async def list_objects(self, bucket_name: str, prefix: str = "") -> list[str]:
        """列出存储桶中的对象名称。"""
        blobs = await self._exec(lambda: list(self._client.list_blobs(bucket_name, prefix=prefix or None)))
        return [b.name for b in blobs]

    async def read_object(self, bucket_name: str, object_name: str) -> bytes:
        """读取对象内容为字节数据。"""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        return await self._exec(lambda: blob.download_as_bytes())

    async def write_object(self, bucket_name: str, object_name: str, data: bytes) -> None:
        """将字节数据写入对象。"""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        await self._exec(lambda: blob.upload_from_file(io.BytesIO(data)))

    async def upload_object(self, bucket_name: str, object_name: str, source_path: str) -> None:
        """从本地文件上传对象。"""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        await self._exec(lambda: blob.upload_from_filename(source_path))

    async def download_object(self, bucket_name: str, object_name: str, dest_path: str) -> None:
        """下载对象到本地文件。"""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        await self._exec(lambda: blob.download_to_filename(dest_path))

    async def copy_object(self, src_bucket: str, src_obj: str, dst_bucket: str, dst_obj: str) -> None:
        """复制对象到目标存储桶。"""
        src = self._client.bucket(src_bucket).blob(src_obj)
        dst = self._client.bucket(dst_bucket).blob(dst_obj)
        await self._exec(lambda: self._client.copy_blob(src, self._client.bucket(dst_bucket), dst_obj))

    async def move_object(self, src_bucket: str, src_obj: str, dst_bucket: str, dst_obj: str) -> None:
        """移动对象到目标存储桶。"""
        await self.copy_object(src_bucket, src_obj, dst_bucket, dst_obj)
        await self.delete_object(src_bucket, src_obj)

    async def delete_object(self, bucket_name: str, object_name: str) -> None:
        """删除指定对象。"""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        await self._exec(lambda: blob.delete())

    async def get_object_metadata(self, bucket_name: str, object_name: str) -> dict[str, Any]:
        """获取对象元数据。"""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        await self._exec(lambda: blob.reload())
        return {"name": blob.name, "size": blob.size, "content_type": blob.content_type, "updated": str(blob.updated)}


@register_source("cloud-storage")
@dataclass
class CloudStorageSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-storage"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudStorageSourceConfig:
        """从字典构造配置实例。"""
        return cls(_name=name, project_id=data.get("projectId", ""))

    async def initialize(self, tracer=None) -> CloudStorageSource:
        """创建并初始化数据源实例。"""
        try:
            from google.cloud import storage
        except ImportError as e:
            raise ImportError("google-cloud-storage is required: pip install google-cloud-storage") from e

        client = storage.Client(project=self.project_id)
        source = CloudStorageSource(name=self._name, client=client, project_id=self.project_id)
        await source.connect()
        return source
