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


def _extract_rows_columns(result: Any) -> tuple[list, list]:
    """从 clickhouse-connect 查询结果中分离 (rows, columns_with_types)。"""
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], result[1]
    return result, []


def _extract_col_name(col) -> str:
    """从单个 column 定义中提取列名。"""
    return col[0] if isinstance(col, (tuple, list)) else col


def _extract_col_names(columns: list) -> list[str]:
    """从 columns_with_types 中提取列名列表。"""
    if not columns:
        return []
    return [_extract_col_name(c) for c in columns]


def _rows_to_dicts(rows: list, col_names: list[str]) -> list[dict[str, Any]]:
    """将行数据转换为 list[dict],有列名用列名,无列名用索引。"""
    key_fn = (lambda row: dict(zip(col_names, row))) if col_names else (lambda row: dict(enumerate(row)))
    return [key_fn(row) for row in rows]


def _import_clickhouse_connect() -> Any:
    """延迟导入 clickhouse-connect,未安装时抛出带提示的 ImportError。"""
    try:
        import clickhouse_connect
    except ImportError as e:
        raise ImportError(
            "clickhouse-connect is required for ClickHouse support: pip install clickhouse-connect"
        ) from e
    return clickhouse_connect


class ClickHouseSource(SQLSource):
    """ClickHouse source using clickhouse-connect (sync) wrapped with asyncio."""

    def __init__(self, name: str, client: Any):
        """初始化数据源配置。"""
        self._name = name
        self._client = client

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "clickhouse"

    async def connect(self) -> None:
        """建立数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.command("SELECT 1"))

    async def close(self) -> None:
        """关闭数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.close())

    async def execute_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询并返回结果。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步执行查询并转换为字典列表。"""
            result = self._client.query(sql, parameters=params or {})
            rows, columns = _extract_rows_columns(result)
            col_names = _extract_col_names(columns)
            limited = list(rows)[: self.max_rows]
            return _rows_to_dicts(limited, col_names)

        try:
            return await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=self.query_timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"ClickHouse query exceeded {self.query_timeout}s timeout") from e

    async def list_tables(self) -> list[str]:
        """列出数据库中所有表。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[str]:
            """同步查询所有表名。"""
            rows = self._client.query("SHOW TABLES")
            data, _ = _extract_rows_columns(rows)
            return [row[0] for row in data]

        return await loop.run_in_executor(None, _run)

    async def list_databases(self) -> list[str]:
        """List all databases in the ClickHouse instance."""
        loop = asyncio.get_event_loop()

        def _run() -> list[str]:
            """同步查询所有数据库名。"""
            rows = self._client.query("SHOW DATABASES")
            data, _ = _extract_rows_columns(rows)
            return [row[0] for row in data]

        return await loop.run_in_executor(None, _run)

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """描述表结构，返回列信息列表。"""
        loop = asyncio.get_event_loop()

        def _run() -> list[dict[str, Any]]:
            """同步查询表结构信息。"""
            rows = self._client.query(f"DESCRIBE {table_name}")
            data, columns = _extract_rows_columns(rows)
            col_names = _extract_col_names(columns)
            return _rows_to_dicts(data, col_names)

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
        """返回数据源类型标识符。"""
        return "clickhouse"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ClickHouseSourceConfig:
        """从字典构造配置实例。"""
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
        """创建并初始化数据源实例。"""
        # 延迟导入：clickhouse-connect 是可选依赖（[clickhouse] extra），只有真正创建
        # ClickHouse 连接时才需要，避免未安装该驱动时拖累整个后端启动。
        clickhouse_connect = _import_clickhouse_connect()

        loop = asyncio.get_event_loop()

        def _connect() -> Any:
            """同步创建 ClickHouse 客户端连接。"""
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
