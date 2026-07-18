"""MongoDB source — pymongo wrapped with asyncio.

pymongo 是 MongoDB 官方推荐的 Python 驱动,属于同步库,
因此用 run_in_executor 包装为异步,与 hbase.py 使用 happybase 的模式一致。

Maps to Go: internal/sources/mongodb/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class MongoDBSource(NoSQLSource):
    """MongoDB source using pymongo (sync) wrapped with asyncio.run_in_executor."""

    def __init__(self, name: str, client: Any, database: str):
        """初始化数据源配置。"""
        self._name = name
        self._client = client
        self._database_name = database
        self._db = client[database]

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "mongodb"

    async def connect(self) -> None:
        """建立数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.admin.command("ping"))

    async def close(self) -> None:
        """关闭数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.close())

    async def find(
        self, collection: str, query: dict[str, Any] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询集合中匹配条件的文档列表。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步执行查询并收集文档列表。"""
            cursor = self._db[collection].find(query or {}).limit(limit)
            results: list[dict[str, Any]] = []
            for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)
            return results

        return await loop.run_in_executor(None, _run)

    async def aggregate(
        self, collection: str, pipeline: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """对集合执行聚合管道操作。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步执行聚合管道并收集结果。"""
            cursor = self._db[collection].aggregate(pipeline)
            results: list[dict[str, Any]] = []
            for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)
            return results

        return await loop.run_in_executor(None, _run)

    async def find_one(
        self, collection: str, query: dict[str, Any], projection: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """查询单个匹配文档。"""
        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any] | None:
            """同步查询单个文档。"""
            doc = self._db[collection].find_one(query, projection)
            if doc is not None:
                doc.pop("_id", None)
            return doc

        return await loop.run_in_executor(None, _run)

    async def insert_one(self, collection: str, document: dict[str, Any]) -> dict[str, Any]:
        """向集合插入单个文档。"""
        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            """同步插入单个文档。"""
            result = self._db[collection].insert_one(document)
            return {"inserted_id": str(result.inserted_id), "acknowledged": result.acknowledged}

        return await loop.run_in_executor(None, _run)

    async def insert_many(self, collection: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
        """向集合批量插入多个文档。"""
        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            """同步批量插入多个文档。"""
            result = self._db[collection].insert_many(documents)
            return {
                "inserted_ids": [str(iid) for iid in result.inserted_ids],
                "inserted_count": result.inserted_count,
                "acknowledged": result.acknowledged,
            }

        return await loop.run_in_executor(None, _run)

    async def delete_one(self, collection: str, query: dict[str, Any]) -> dict[str, Any]:
        """删除集合中单个匹配文档。"""
        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            """同步删除单个匹配文档。"""
            result = self._db[collection].delete_one(query)
            return {"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}

        return await loop.run_in_executor(None, _run)

    async def delete_many(self, collection: str, query: dict[str, Any]) -> dict[str, Any]:
        """删除集合中所有匹配文档。"""
        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            """同步删除所有匹配文档。"""
            result = self._db[collection].delete_many(query)
            return {"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}

        return await loop.run_in_executor(None, _run)

    async def update_one(
        self, collection: str, query: dict[str, Any], update: dict[str, Any]
    ) -> dict[str, Any]:
        """更新集合中单个匹配文档。"""
        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            """同步更新单个匹配文档。"""
            result = self._db[collection].update_one(query, update)
            return {
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
                "acknowledged": result.acknowledged,
            }

        return await loop.run_in_executor(None, _run)

    async def update_many(
        self, collection: str, query: dict[str, Any], update: dict[str, Any]
    ) -> dict[str, Any]:
        """更新集合中所有匹配文档。"""
        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            """同步更新所有匹配文档。"""
            result = self._db[collection].update_many(query, update)
            return {
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
                "acknowledged": result.acknowledged,
            }

        return await loop.run_in_executor(None, _run)

    async def list_collections(self) -> list[str]:
        """列出数据库中所有集合名称。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[str]:
            """同步获取集合名称列表。"""
            return sorted(self._db.list_collection_names())

        return await loop.run_in_executor(None, _run)


@register_source("mongodb")
@dataclass
class MongoDBSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    connection_string: str = "mongodb://localhost:27017"
    database: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "mongodb"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongoDBSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            connection_string=data.get("connectionString", "mongodb://localhost:27017"),
            database=data.get("database", ""),
        )

    async def initialize(self, tracer=None) -> MongoDBSource:
        """创建并初始化数据源实例。"""
        # 延迟导入：pymongo 是可选依赖（[mongodb] extra），只有真正创建
        # MongoDB 连接时才需要，避免未安装该驱动时拖累整个后端启动。
        try:
            from pymongo import MongoClient
        except ImportError as e:
            raise ImportError("pymongo is required for MongoDB support: pip install pymongo") from e

        loop = asyncio.get_event_loop()

        def _connect() -> Any:
            """同步创建 MongoDB 客户端连接。"""
            return MongoClient(self.connection_string)

        client = await loop.run_in_executor(None, _connect)
        source = MongoDBSource(name=self._name, client=client, database=self.database)
        await source.connect()
        return source
