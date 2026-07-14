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


class HBaseSource(NoSQLSource):
    """HBase source using happybase with asyncio wrapper."""

    def __init__(self, name: str, connection: Any):
        self._name = name
        self._connection = connection

    @property
    def source_type(self) -> str:
        return "hbase"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._connection.tables())

    async def close(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._connection.close())

    async def list_tables(self) -> list[str]:
        """返回所有表名(happybase 返回 bytes 列表,需解码为 str)。"""
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, lambda: self._connection.tables())
        return [t.decode("utf-8") if isinstance(t, bytes) else t for t in raw]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """返回表的列族信息。"""
        loop = asyncio.get_event_loop()
        table = self._connection.table(table_name)
        families = await loop.run_in_executor(None, lambda: table.families())
        result: list[dict[str, Any]] = []
        for cf_name, cf_opts in families.items():
            cf_name_str = cf_name.decode("utf-8") if isinstance(cf_name, bytes) else cf_name
            opts: dict[str, Any] = {}
            if hasattr(cf_opts, "items"):
                for k, v in cf_opts.items():
                    k_str = k.decode("utf-8") if isinstance(k, bytes) else k
                    v_str = v.decode("utf-8") if isinstance(v, bytes) else v
                    opts[k_str] = v_str
            else:
                opts["max_versions"] = getattr(cf_opts, "max_versions", None)
            result.append({"column_family": cf_name_str, "options": opts})
        return result

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
            rows: list[dict[str, Any]] = []
            scanner = table.scan(
                row_prefix=prefix.encode("utf-8") if prefix else None,
                limit=limit,
                columns=col_tuple,
            )
            for row_key, row_data in scanner:
                row_dict: dict[str, Any] = {"row_key": row_key.decode("utf-8") if isinstance(row_key, bytes) else row_key}
                for col_qual, val in row_data.items():
                    col_str = col_qual.decode("utf-8") if isinstance(col_qual, bytes) else col_qual
                    val_str = val.decode("utf-8") if isinstance(val, bytes) else val
                    row_dict[col_str] = val_str
                rows.append(row_dict)
            return rows

        return await loop.run_in_executor(None, _do_scan)

    async def get_row(self, table_name: str, row_key: str) -> dict[str, Any]:
        """获取单行数据。"""
        loop = asyncio.get_event_loop()
        table = self._connection.table(table_name)

        def _do_get() -> dict[str, Any]:
            row_data = table.row(row_key.encode("utf-8"))
            result: dict[str, Any] = {"row_key": row_key}
            for col_qual, val in row_data.items():
                col_str = col_qual.decode("utf-8") if isinstance(col_qual, bytes) else col_qual
                val_str = val.decode("utf-8") if isinstance(val, bytes) else val
                result[col_str] = val_str
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
        encoded_data = {
            k.encode("utf-8") if isinstance(k, str) else k: v.encode("utf-8") if isinstance(v, str) else v
            for k, v in data.items()
        }
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
        return "hbase"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBaseSourceConfig:
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
        try:
            import happybase  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "happybase is required for HBase support: pip install happybase"
            ) from e

        loop = asyncio.get_event_loop()

        def _connect() -> Any:
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
