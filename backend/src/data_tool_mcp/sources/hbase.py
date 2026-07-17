"""HBase source — happybase (Thrift protocol) wrapped with asyncio.

HBase 是 Apache Hadoop 数据库,通过 Thrift 接口提供服务。
happybase 是 Python HBase 客户端,基于 Thrift 协议,属于同步库,
因此用 run_in_executor 包装为异步。

参考实现: cassandra.py (NoSQLSource + 延迟导入)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import NoSQLSource, SourceConfig, register_source


def _decode_bytes(value: Any) -> Any:
    """将 bytes 解码为 str,其他类型原样返回。"""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _decode_cf_opts(cf_opts: Any) -> dict[str, Any]:
    """将列族选项中的 bytes 键值解码为 str。"""
    if hasattr(cf_opts, "items"):
        return {_decode_bytes(k): _decode_bytes(v) for k, v in cf_opts.items()}
    return {"max_versions": getattr(cf_opts, "max_versions", None)}


def _decode_row(row_key: Any, row_data: dict[str, Any]) -> dict[str, Any]:
    """将 scan/get 返回的行数据解码为 str 键值。"""
    row_dict: dict[str, Any] = {"row_key": _decode_bytes(row_key)}
    for col_qual, val in row_data.items():
        row_dict[_decode_bytes(col_qual)] = _decode_bytes(val)
    return row_dict


def _encode_str(value: Any) -> Any:
    """将 str 编码为 bytes,其他类型原样返回。"""
    return value.encode("utf-8") if isinstance(value, str) else value


class HBaseSource(NoSQLSource):
    """HBase source using happybase with asyncio wrapper."""

    def __init__(self, name: str, connection: Any):
        """初始化数据源配置。"""
        self._name = name
        self._connection = connection

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "hbase"

    async def connect(self) -> None:
        """建立数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._connection.tables())

    async def close(self) -> None:
        """关闭数据库连接。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._connection.close())

    async def list_tables(self) -> list[str]:
        """返回所有表名(happybase 返回 bytes 列表,需解码为 str)。"""
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, lambda: self._connection.tables())
        return [_decode_bytes(t) for t in raw]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """返回表的列族信息。"""
        loop = asyncio.get_event_loop()
        table = self._connection.table(table_name)
        families = await loop.run_in_executor(None, lambda: table.families())
        return [
            {"column_family": _decode_bytes(cf_name), "options": _decode_cf_opts(cf_opts)}
            for cf_name, cf_opts in families.items()
        ]

    async def scan(
        self,
        table_name: str,
        prefix: str | None = None,
        limit: int = 100,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """扫描表数据。"""
        loop = asyncio.get_event_loop()
        table = self._connection.table(table_name)
        col_tuple = tuple(columns) if columns else None

        def _do_scan() -> list[dict[str, Any]]:
            """同步扫描表并解码行数据。"""
            row_prefix = prefix.encode("utf-8") if prefix else None
            scanner = table.scan(
                row_prefix=row_prefix,
                limit=limit,
                columns=col_tuple,
            )
            return [_decode_row(row_key, row_data) for row_key, row_data in scanner]

        return await loop.run_in_executor(None, _do_scan)

    async def get_row(self, table_name: str, row_key: str) -> dict[str, Any]:
        """获取单行数据。"""
        loop = asyncio.get_event_loop()
        table = self._connection.table(table_name)

        def _do_get() -> dict[str, Any]:
            """同步获取单行数据并解码。"""
            row_data = table.row(row_key.encode("utf-8"))
            result: dict[str, Any] = {"row_key": row_key}
            for col_qual, val in row_data.items():
                result[_decode_bytes(col_qual)] = _decode_bytes(val)
            return result

        return await loop.run_in_executor(None, _do_get)

    async def put_row(
        self,
        table_name: str,
        row_key: str,
        data: dict[str, str],
    ) -> None:
        """写入单行数据。data 为 {column_family:qualifier: value} 映射。"""
        loop = asyncio.get_event_loop()
        table = self._connection.table(table_name)
        encoded_data = {_encode_str(k): _encode_str(v) for k, v in data.items()}
        await loop.run_in_executor(None, lambda: table.put(row_key.encode("utf-8"), encoded_data))

    async def delete_row(self, table_name: str, row_key: str, columns: list[str] | None = None) -> None:
        """删除行或指定列。"""
        loop = asyncio.get_event_loop()
        table = self._connection.table(table_name)
        col_tuple = tuple(columns) if columns else None
        await loop.run_in_executor(
            None,
            lambda: table.delete(row_key.encode("utf-8"), columns=col_tuple),
        )


@register_source("hbase")
@dataclass
class HBaseSourceConfig(SourceConfig):
    """HBase source configuration.

    通过 Thrift 协议连接 HBase,默认端口 9090。
    """
    _name: str = field(init=True, repr=False)
    host: str = "localhost"
    port: int = 9090
    table_prefix: str = ""
    protocol: str = "binary"
    transport: str = "buffered"
    timeout: int = 10000

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "hbase"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBaseSourceConfig:
        """从字典构造配置实例。"""
        return cls(
            _name=name,
            host=data.get("host", "localhost"),
            port=data.get("port", 9090),
            table_prefix=data.get("tablePrefix", ""),
            protocol=data.get("protocol", "binary"),
            transport=data.get("transport", "buffered"),
            timeout=data.get("timeout", 10000),
        )

    async def initialize(self, tracer=None) -> HBaseSource:
        """创建并初始化数据源实例。"""
        try:
            import happybase  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "happybase is required for HBase support: pip install happybase"
            ) from e

        loop = asyncio.get_event_loop()

        def _connect() -> Any:
            """同步创建 HBase Thrift 连接。"""
            return happybase.Connection(
                host=self.host,
                port=self.port,
                table_prefix=self.table_prefix or None,
                protocol=self.protocol,
                transport=self.transport,
                timeout=self.timeout,
            )

        connection = await loop.run_in_executor(None, _connect)
        source = HBaseSource(name=self._name, connection=connection)
        await source.connect()
        return source
