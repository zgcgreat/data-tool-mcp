"""Firestore source — google-cloud-firestore.

Maps to Go: internal/sources/firestore/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class FirestoreSource(Source):
    """Firestore source using google-cloud-firestore async client."""

    def __init__(self, name: str, client: Any):
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        return "firestore"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        self._client.close()

    async def list_collections(self) -> list[str]:
        cols = await self._client.collections()
        return [c.id for c in cols]

    async def get_documents(self, collection: str, limit: int = 100) -> list[dict[str, Any]]:
        docs = self._client.collection(collection).limit(limit)
        results = []
        async for doc in docs.stream():
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            results.append(data)
        return results

    async def add_documents(self, collection: str, documents: list[dict[str, Any]]) -> list[str]:
        col_ref = self._client.collection(collection)
        ids = []
        for doc_data in documents:
            _, doc_ref = await col_ref.add(doc_data)
            ids.append(doc_ref.id)
        return ids

    async def update_document(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        doc_ref = self._client.collection(collection).document(doc_id)
        await doc_ref.update(data)

    async def delete_documents(self, collection: str, doc_ids: list[str]) -> None:
        for doc_id in doc_ids:
            await self._client.collection(collection).document(doc_id).delete()

    async def query(self, collection: str, field_path: str, op: str, value: Any, limit: int = 100) -> list[dict[str, Any]]:
        query = self._client.collection(collection).where(field_path, op, value).limit(limit)
        results = []
        async for doc in query.stream():
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            results.append(data)
        return results

    async def query_collection(self, collection: str, queries: list[dict[str, Any]], limit: int = 100) -> list[dict[str, Any]]:
        col_ref = self._client.collection(collection)
        for q in queries:
            col_ref = col_ref.where(q["field"], q["op"], q["value"])
        col_ref = col_ref.limit(limit)
        results = []
        async for doc in col_ref.stream():
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            results.append(data)
        return results

    async def get_rules(self) -> str:
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
        return {"valid": True, "message": "Rules validation not yet implemented"}


@register_source("firestore")
@dataclass
class FirestoreSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""
    database: str = "(default)"

    @property
    def source_type(self) -> str:
        return "firestore"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> FirestoreSourceConfig:
        return cls(
            _name=name,
            project_id=data.get("projectId", ""),
            database=data.get("database", "(default)"),
        )

    async def initialize(self, tracer=None) -> FirestoreSource:
        try:
            from google.cloud import firestore
        except ImportError as e:
            raise ImportError("google-cloud-firestore is required: pip install google-cloud-firestore") from e

        client = firestore.AsyncClient(project=self.project_id, database=self.database)
        source = FirestoreSource(name=self._name, client=client)
        await source.connect()
        return source
