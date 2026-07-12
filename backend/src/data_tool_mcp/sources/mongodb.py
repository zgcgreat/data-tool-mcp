"""MongoDB source — pymongo async.

Maps to Go: internal/sources/mongodb/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class MongoDBSource(NoSQLSource):
    """MongoDB source using motor (async pymongo)."""

    def __init__(self, name: str, client: AsyncIOMotorClient, database: str):
        self._name = name
        self._client = client
        self._database_name = database
        self._db = client[database]

    @property
    def source_type(self) -> str:
        return "mongodb"

    async def connect(self) -> None:
        await self._client.admin.command("ping")

    async def close(self) -> None:
        self._client.close()

    async def find(
        self, collection: str, query: dict[str, Any] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        cursor = self._db[collection].find(query or {})
        results = []
        async for doc in cursor.limit(limit):
            doc.pop("_id", None)
            results.append(doc)
        return results

    async def aggregate(
        self, collection: str, pipeline: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        cursor = self._db[collection].aggregate(pipeline)
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
        return results

    async def find_one(
        self, collection: str, query: dict[str, Any], projection: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        doc = await self._db[collection].find_one(query, projection)
        if doc is not None:
            doc.pop("_id", None)
        return doc

    async def insert_one(
        self, collection: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._db[collection].insert_one(document)
        return {"inserted_id": str(result.inserted_id), "acknowledged": result.acknowledged}

    async def insert_many(
        self, collection: str, documents: list[dict[str, Any]]
    ) -> dict[str, Any]:
        result = await self._db[collection].insert_many(documents)
        return {
            "inserted_ids": [str(iid) for iid in result.inserted_ids],
            "inserted_count": result.inserted_count,
            "acknowledged": result.acknowledged,
        }

    async def delete_one(
        self, collection: str, query: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._db[collection].delete_one(query)
        return {"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}

    async def delete_many(
        self, collection: str, query: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._db[collection].delete_many(query)
        return {"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}

    async def update_one(
        self, collection: str, query: dict[str, Any], update: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._db[collection].update_one(query, update)
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            "acknowledged": result.acknowledged,
        }

    async def update_many(
        self, collection: str, query: dict[str, Any], update: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._db[collection].update_many(query, update)
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            "acknowledged": result.acknowledged,
        }

    async def list_collections(self) -> list[str]:
        collections = await self._db.list_collection_names()
        return sorted(collections)


@register_source("mongodb")
@dataclass
class MongoDBSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    connection_string: str = "mongodb://localhost:27017"
    database: str = ""

    @property
    def source_type(self) -> str:
        return "mongodb"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongoDBSourceConfig:
        return cls(
            _name=name,
            connection_string=data.get("connectionString", "mongodb://localhost:27017"),
            database=data.get("database", ""),
        )

    async def initialize(self, tracer=None) -> MongoDBSource:
        # 延迟导入：motor 是可选依赖（[mongodb] extra），只有真正创建
        # MongoDB 连接时才需要，避免未安装该驱动时拖累整个后端启动。
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(self.connection_string)
        source = MongoDBSource(name=self._name, client=client, database=self.database)
        await source.connect()
        return source
