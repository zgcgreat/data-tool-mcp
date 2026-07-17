"""Couchbase source — couchbase SDK with asyncio wrapper.

Maps to Go: internal/sources/couchbase/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


class CouchbaseSource(NoSQLSource):
    """Couchbase source using the couchbase SDK with asyncio wrapper."""

    def __init__(self, name: str, cluster: Any, bucket_name: str):
        """初始化数据源配置。"""
        self._name = name
        self._cluster = cluster
        self._bucket_name = bucket_name

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "couchbase"

    async def connect(self) -> None:
        """建立数据库连接。"""
        loop = asyncio.get_event_loop()
        bucket = self._cluster.bucket(self._bucket_name)
        await loop.run_in_executor(None, lambda: bucket.default_collection())

    async def close(self) -> None:
        """关闭数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._cluster.close)

    async def execute_sql(self, query: str, params: dict | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询并返回结果。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步执行 N1QL 查询并收集行数据。"""
            result = self._cluster.query(query, **(params or {}))
            return [dict(row) for row in result]

        return await loop.run_in_executor(None, _run)


@register_source("couchbase")
@dataclass
class CouchbaseSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    connection_string: str = "couchbase://localhost"
    username: str = ""
    password: str = ""
    bucket_name: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "couchbase"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CouchbaseSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            connection_string=data.get("connectionString", "couchbase://localhost"),
            username=data.get("username", ""),
            password=data.get("password", ""),
            bucket_name=data.get("bucketName", ""),
        )

    async def initialize(self, tracer=None) -> CouchbaseSource:
        """创建并初始化数据源实例。"""
        try:
            from couchbase.cluster import Cluster
            from couchbase.auth import PasswordAuthenticator
            from couchbase.options import ClusterOptions
        except ImportError as e:
            raise ImportError("couchbase is required: pip install couchbase") from e

        auth = PasswordAuthenticator(self.username, self.password)
        cluster = Cluster(self.connection_string, ClusterOptions(auth))
        source = CouchbaseSource(name=self._name, cluster=cluster, bucket_name=self.bucket_name)
        await source.connect()
        return source
