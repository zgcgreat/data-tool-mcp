"""Firestore source — google-cloud-firestore.

Maps to Go: internal/sources/firestore/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


def _import_firestore() -> Any:
    """延迟导入 google-cloud-firestore,未安装时抛出带提示的 ImportError。"""
    try:
        from google.cloud import firestore
    except ImportError as e:
        raise ImportError(
            "google-cloud-firestore is required: pip install google-cloud-firestore"
        ) from e
    return firestore


async def _stream_to_dicts(stream: Any) -> list[dict[str, Any]]:
    """将 Firestore 异步文档流转换为 list[dict],注入 _id 字段。"""
    results: list[dict[str, Any]] = []
    async for doc in stream:
        data = doc.to_dict() or {}
        data["_id"] = doc.id
        results.append(data)
    return results


class FirestoreSource(Source):
    """Firestore source using google-cloud-firestore async client."""

    def __init__(self, name: str, client: Any):
        """初始化数据源配置。"""
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "firestore"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass

    async def close(self) -> None:
        """关闭数据库连接。"""
        self._client.close()

    async def list_collections(self) -> list[str]:
        """列出所有集合名称。"""
        cols = await self._client.collections()
        return [c.id for c in cols]

    async def get_documents(self, collection: str, limit: int = 100) -> list[dict[str, Any]]:
        """获取集合中的文档列表。"""
        docs = self._client.collection(collection).limit(limit)
        return await _stream_to_dicts(docs.stream())

    async def add_documents(self, collection: str, documents: list[dict[str, Any]]) -> list[str]:
        """向集合添加多个文档并返回文档 ID 列表。"""
        col_ref = self._client.collection(collection)
        ids = []
        for doc_data in documents:
            _, doc_ref = await col_ref.add(doc_data)
            ids.append(doc_ref.id)
        return ids

    async def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        """更新指定文档。"""
        doc_ref = self._client.collection(collection).document(doc_id)
        await doc_ref.update(data)

    async def delete_documents(self, collection: str, doc_ids: list[str]) -> None:
        """删除指定文档。"""
        for doc_id in doc_ids:
            await self._client.collection(collection).document(doc_id).delete()

    async def query(self, collection: str, field_path: str, op: str, value: Any, limit: int = 100) -> list[dict[str, Any]]:
        """按条件查询集合中的文档。"""
        query = self._client.collection(collection).where(field_path, op, value).limit(limit)
        return await _stream_to_dicts(query.stream())

    async def query_collection(self, collection: str, queries: list[dict[str, Any]], limit: int = 100) -> list[dict[str, Any]]:
        """按多条件组合查询集合中的文档。"""
        col_ref = self._client.collection(collection)
        for q in queries:
            col_ref = col_ref.where(q["field"], q["op"], q["value"])
        return await _stream_to_dicts(col_ref.limit(limit).stream())

    async def get_rules(self) -> str:
        """获取 Firestore 安全规则。"""
        try:
            from google.cloud import firestore_admin_v1
        except ImportError as e:
            raise ImportError(
                "google-cloud-firestore is required: pip install google-cloud-firestore"
            ) from e
        admin = firestore_admin_v1.FirestoreAdminClient()
        name = f"projects/{self._client.project}/databases/(default)/securityRules"
        try:
            rules = admin.get_security_rules(name)
            return str(rules)
        except Exception:
            return ""

    async def validate_rules(self, rules_text: str) -> dict[str, Any]:
        """校验安全规则文本。"""
        return {"valid": True, "message": "Rules validation not yet implemented"}


@register_source("firestore")
@dataclass
class FirestoreSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    database: str = "(default)"

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "firestore"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> FirestoreSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            database=data.get("database", "(default)"),
        )

    async def initialize(self, tracer=None) -> FirestoreSource:
        """创建并初始化数据源实例。"""
        firestore = _import_firestore()
        client = firestore.AsyncClient(project=self.project_id, database=self.database)
        source = FirestoreSource(name=self._name, client=client)
        await source.connect()
        return source
