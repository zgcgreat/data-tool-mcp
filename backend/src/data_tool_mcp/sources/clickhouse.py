"""ClickHouse source — clickhouse-connect wrapped with asyncio.

clickhouse-connect 是 ClickHouse 官方推荐的 Python 驱动,属于同步库,
因此用 run_in_executor 包装为异步,与 hbase.py 使用 happybase 的模式一致。

Maps to Go: internal/sources/clickhouse/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import SQLSource, SourceConfig, register_source


class ClickHouseSource(SQLSource):
    """ClickHouse source using clickhouse-connect (sync) wrapped with asyncio."""

    def __init__(self, name: str, client: Any):
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        return "clickhouse"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.command("SELECT 1"))

    async def close(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.close())

    async def execute_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            # clickhouse-connect: query_arrow / query_df / query 均支持参数化查询
            # 此处用 query_result 获取 list[dict] 风格的结果
            result = self._client.query(sql, parameters=params or {})
            # result: (rows, columns_with_types) — rows 是 list[tuple]
            rows, columns = result if isinstance(result, tuple) and len(result) == 2 else (result, [])
            col_names = [c[0] if isinstance(c, (tuple, list)) else c for c in columns] if columns else []
            limited = list(rows)[: self.max_rows]
            if col_names:
                return [dict(zip(col_names, row)) for row in limited]
            # 退化情况:无列名,使用索引作为 key
            return [dict(enumerate(row)) for row in limited]

        try:
            return await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=self.query_timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"ClickHouse query exceeded {self.query_timeout}s timeout") from e

    async def list_tables(self) -> list[str]:
        loop = asyncio.get_event_loop()

        def _run() -> list[str]:
            rows = self._client.query("SHOW TABLES")
            # rows 返回 (list[tuple], columns)
            data = rows[0] if isinstance(rows, tuple) and len(rows) == 2 else rows
            return [row[0] for row in data]

        return await loop.run_in_executor(None, _run)

    async def list_databases(self) -> list[str]:
        """List all databases in the ClickHouse instance."""
        loop = asyncio.get_event_loop()

        def _run() -> list[str]:
            rows = self._client.query("SHOW DATABASES")
            data = rows[0] if isinstance(rows, tuple) and len(rows) == 2 else rows
            return [row[0] for row in data]

        return await loop.run_in_executor(None, _run)

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            rows = self._client.query(f"DESCRIBE {table_name}")
            # DESCRIBE 返回 (rows, columns_with_types)
            data, columns = rows if isinstance(rows, tuple) and len(rows) == 2 else (rows, [])
            col_names = [c[0] if isinstance(c, (tuple, list)) else c for c in columns] if columns else []
            if col_names:
                return [dict(zip(col_names, row)) for row in data]
            return [dict(enumerate(row)) for row in data]

        return await loop.run_in_executor(None, _run)


@register_source("clickhouse")
@dataclass
class ClickHouseSourceConfig(SourceConfig):
    """ClickHouse source configuration.

    Maps to Go: internal/sources/clickhouse/ Config struct
    """
    _name: str = field(init=True, repr=False)
    connection_string: str = ""
    host: str = "localhost"
    port: int = 8123  # 默认 HTTP 端口 (clickhouse-connect 使用 HTTP)
    database: str = "default"
    user: str = "default"
    password: str = ""
    secure: bool = False
    max_open_conns: int = 4

    @property
    def source_type(self) -> str:
        return "clickhouse"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ClickHouseSourceConfig:
        return cls(
            _name=name,
            connection_string=data.get("connectionString", ""),
            host=data.get("host", "localhost"),
            port=data.get("port", 8123),
            database=data.get("database", "default"),
            user=data.get("user", "default"),
            password=data.get("password", ""),
            secure=data.get("secure", False),
            max_open_conns=data.get("maxOpenConns", 4),
        )

    async def initialize(self, tracer=None) -> ClickHouseSource:
        # 延迟导入：clickhouse-connect 是可选依赖（[clickhouse] extra），只有真正创建
        # ClickHouse 连接时才需要，避免未安装该驱动时拖累整个后端启动。
        try:
            import clickhouse_connect
        except ImportError as e:
            raise ImportError(
                "clickhouse-connect is required for ClickHouse support: pip install clickhouse-connect"
            ) from e

        loop = asyncio.get_event_loop()

        def _connect() -> Any:
            # clickhouse-connect 使用 HTTP 协议,端口默认 8123 (HTTP) / 8443 (HTTPS)
            # 如果配置了 connection_string,则忽略 host/port 等独立字段
            if self.connection_string:
                # 连接字符串格式: clickhouse://user:password@host:port/database?secure=true
                # clickhouse-connect 提供 from_url 帮助方法
                return clickhouse_connect.get_client(connection_str=self.connection_string)
            return clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                database=self.database,
                secure=self.secure,
                connect_timeout=30,
                send_receive_timeout=300,
            )

        client = await loop.run_in_executor(None, _connect)
        source = ClickHouseSource(name=self._name, client=client)
        await source.connect()
        return source
