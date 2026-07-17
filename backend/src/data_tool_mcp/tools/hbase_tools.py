"""HBase tools — list_tables, describe_table, scan, get, put, delete。

参考实现: cassandra_tools.py (NoSQL 工具模式)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.hbase import HBaseSource
from data_tool_mcp.tools.base import (
    BaseTool,
    ConfigBase,
    ParameterManifest,
    SourceProvider,
    ToolAnnotations,
    ToolConfig,
    ToolManifest,
    _get_typed_source_async,
    register_tool,
)


def _split_columns_string(columns_str: str) -> list[str]:
    """将逗号分隔的列字符串解析为 list[str],去除空白项。"""
    return [c.strip() for c in columns_str.split(",") if c.strip()]


def _parse_columns(columns: Any) -> list[str] | None:
    """将 columns 参数解析为 list[str];字符串按逗号分隔,list 原样返回,None 返回 None。"""
    if not isinstance(columns, str):
        return columns
    return _split_columns_string(columns)


def _require_param(params: dict[str, Any], name: str) -> Any:
    """从 params 中取出必填字段,为空时抛出 ValueError。"""
    value = params.get(name)
    if not value:
        raise ValueError(f"missing {name!r} parameter")
    return value


# ---------------------------------------------------------------------------
# hbase-list-tables
# ---------------------------------------------------------------------------

class HBaseListTablesTool(BaseTool):
    """列出 HBase 中的所有表。"""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, HBaseSource)
        try:
            tables = await source.list_tables()
            return {"tables": tables, "count": len(tables)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=[], auth_required=self.auth_required)


@register_tool("hbase-list-tables")
@dataclass
class HBaseListTablesToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "列出 HBase 中的所有表"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "hbase-list-tables"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBaseListTablesToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "列出 HBase 中的所有表"))

    async def initialize(self) -> HBaseListTablesTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return HBaseListTablesTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# hbase-describe-table
# ---------------------------------------------------------------------------

class HBaseDescribeTableTool(BaseTool):
    """描述 HBase 表的列族结构。"""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, HBaseSource)
        try:
            table_name = params.get("table_name", "")
            if not table_name:
                raise ValueError("missing 'table_name' parameter")
            families = await source.describe_table(table_name)
            return {"table_name": table_name, "column_families": families}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[ParameterManifest(name="table_name", type="string", description="HBase 表名", required=True)],
            auth_required=self.auth_required,
        )


@register_tool("hbase-describe-table")
@dataclass
class HBaseDescribeTableToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "描述 HBase 表的列族结构"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "hbase-describe-table"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBaseDescribeTableToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "描述 HBase 表的列族结构"))

    async def initialize(self) -> HBaseDescribeTableTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return HBaseDescribeTableTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# hbase-scan
# ---------------------------------------------------------------------------

class HBaseScanTool(BaseTool):
    """扫描 HBase 表数据(只读)。"""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, HBaseSource)
        try:
            table_name = params.get("table_name", "")
            if not table_name:
                raise ValueError("missing 'table_name' parameter")
            prefix = params.get("prefix")
            limit = int(params.get("limit", 100))
            columns = _parse_columns(params.get("columns"))
            rows = await source.scan(table_name, prefix=prefix, limit=limit, columns=columns)
            return {"rows": rows, "rowCount": len(rows)}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="table_name", type="string", description="HBase 表名", required=True),
                ParameterManifest(name="prefix", type="string", description="行键前缀过滤(可选)", required=False),
                ParameterManifest(name="limit", type="integer", description="返回行数上限(默认 100)", required=False, default=100),
                ParameterManifest(name="columns", type="array", description="要返回的列(格式: cf:qualifier),省略则返回全部", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("hbase-scan")
@dataclass
class HBaseScanToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "扫描 HBase 表数据(只读)"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "hbase-scan"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBaseScanToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "扫描 HBase 表数据"))

    async def initialize(self) -> HBaseScanTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return HBaseScanTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# hbase-get-row
# ---------------------------------------------------------------------------

class HBaseGetRowTool(BaseTool):
    """获取 HBase 表中指定行键的数据(只读)。"""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, HBaseSource)
        try:
            table_name = params.get("table_name", "")
            row_key = params.get("row_key", "")
            if not table_name or not row_key:
                raise ValueError("missing 'table_name' or 'row_key' parameter")
            row = await source.get_row(table_name, row_key)
            return {"row": row}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="table_name", type="string", description="HBase 表名", required=True),
                ParameterManifest(name="row_key", type="string", description="行键(Row Key)", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("hbase-get-row")
@dataclass
class HBaseGetRowToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "获取 HBase 表中指定行键的数据"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "hbase-get-row"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBaseGetRowToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "获取 HBase 表中指定行键的数据"))

    async def initialize(self) -> HBaseGetRowTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return HBaseGetRowTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# hbase-put-row
# ---------------------------------------------------------------------------

class HBasePutRowTool(BaseTool):
    """向 HBase 表写入一行数据(可能修改数据)。"""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, HBaseSource)
        try:
            table_name = _require_param(params, "table_name")
            row_key = _require_param(params, "row_key")
            data = _require_param(params, "data")
            if not isinstance(data, dict):
                raise ValueError("'data' must be an object mapping column_family:qualifier -> value")
            await source.put_row(table_name, row_key, data)
            return {"ok": True, "table_name": table_name, "row_key": row_key}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="table_name", type="string", description="HBase 表名", required=True),
                ParameterManifest(name="row_key", type="string", description="行键(Row Key)", required=True),
                ParameterManifest(name="data", type="object", description="列数据映射,格式: {\"cf:qualifier\": \"value\"}", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("hbase-put-row")
@dataclass
class HBasePutRowToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "向 HBase 表写入一行数据"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "hbase-put-row"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBasePutRowToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "向 HBase 表写入一行数据"))

    async def initialize(self) -> HBasePutRowTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return HBasePutRowTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# hbase-delete-row
# ---------------------------------------------------------------------------

class HBaseDeleteRowTool(BaseTool):
    """删除 HBase 表中的行或指定列(破坏性操作)。"""

    def __init__(self, cfg: ConfigBase, source_name: str):
        """初始化工具配置。"""
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, HBaseSource)
        try:
            table_name = _require_param(params, "table_name")
            row_key = _require_param(params, "row_key")
            columns = _parse_columns(params.get("columns"))
            await source.delete_row(table_name, row_key, columns=columns)
            return {"ok": True, "table_name": table_name, "row_key": row_key, "deleted_columns": columns}
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="table_name", type="string", description="HBase 表名", required=True),
                ParameterManifest(name="row_key", type="string", description="行键(Row Key)", required=True),
                ParameterManifest(name="columns", type="array", description="要删除的列(格式: cf:qualifier),省略则删除整行", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("hbase-delete-row")
@dataclass
class HBaseDeleteRowToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "删除 HBase 表中的行或指定列"

    @property
    def tool_type(self) -> str:
        """返回工具类型标识符。"""
        return "hbase-delete-row"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> HBaseDeleteRowToolConfig:
        """从字典创建配置实例。"""
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "删除 HBase 表中的行或指定列"))

    async def initialize(self) -> HBaseDeleteRowTool:
        """创建并初始化工具实例。"""
        cfg = ConfigBase(name=self._name, description=self.description)
        return HBaseDeleteRowTool(cfg=cfg, source_name=self.source)
