"""配置持久化存储层 — 以 system_id（系统编号）为业务隔离维度。

表结构与 docker/init-mysql.sql 完全对齐：
  - sources      (id, system_id, name, type, host, port, database, username, password, params, ...)
  - tools        (id, system_id, name, type, source_name, description, params, ...)
  - toolsets     (id, system_id, name, tool_names, ...)

system_id 为 VARCHAR(10) 字符串，由用户在创建数据源时指定，
替代了原 Go 版本中基于 departments 表的多租户隔离设计。

通过 store_url 的 URL scheme 自动选择后端：
  - 未配置（空字符串） → 默认在当前工作目录创建 SQLite 文件 toolbox_data.db（零配置）
  - sqlite:///path/to/data.db    → SQLite 文件（指定路径）
  - mysql://host:3306/db         → MySQL（企业部署，与 Config DB 完全兼容）
    · 推荐三段式：store_url 仅含 mysql://host:port/db，账号密码用 store_username / store_password 单独传入
    · 兼容旧式：也可直接 mysql://user:pass@host:3306/db 把凭据写进 URL

当 store_url 指向 MySQL 时，与 Config DB 使用同一套表，
独立部署的 Admin UI 和 Config DB 操作同一份数据，彻底消除割裂。

类型说明：
  - params: TEXT（存 JSON 字符串，读取时解析）
  - tool_names: TEXT（存逗号分隔字符串，读取时解析为列表）
  - updated_at: 应用层 onupdate=func.now() 维护
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    # 仅用于类型注解,运行时避免循环导入
    from data_tool_mcp.config.models import ToolboxFile

# 加解密统一入口 — 企业部署时可替换 utils/crypto.py 为 SM4/KMS 实现
from data_tool_mcp.utils.crypto import (
    decrypt_password,
    normalize_password_for_storage,
)

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class SourceRecord(Base):
    """数据源表 — 用户添加的数据库连接配置。

    结构化字段（host/port/database/username/password）+ params（JSON 扩展参数）。
    system_id 为业务隔离维度（系统编号，10 位字符串）。
    environment 为环境标识（dev/st/uat/prd），同一系统在不同环境下有独立数据源实例。

    注意：数据库列名加 `src_` / `db_` 前缀避开 MySQL/PG 保留字
    （name/type/database/host/password 等都是保留字），Python 属性名保持简洁。
    """

    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(String(10), nullable=False, default="", index=True)  # 系统编号
    environment = Column(
        String(16), nullable=False, default="", index=True
    )  # 环境（dev/st/uat/prd）
    name = Column("src_name", String(128), nullable=False, index=True)
    type = Column("src_type", String(64), nullable=False)
    host = Column("db_host", String(255), nullable=False, default="")
    port = Column("db_port", Integer, default=0)
    database = Column("db_name", String(128), default="")
    username = Column("db_user", String(128), default="")
    password = Column("db_password", String(512), default="")
    params = Column(Text, default="{}")  # JSON 字符串
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ToolRecord(Base):
    """工具表 — MCP 工具定义。

    source_name 引用 sources.name，params 存额外工具参数。
    system_id + environment 冗余存储，便于按系统+环境查询工具。

    注意：数据库列名加 `tool_` 前缀避开保留字（name/type/description）。
    """

    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(String(10), nullable=False, default="", index=True)  # 系统编号
    environment = Column(
        String(16), nullable=False, default="", index=True
    )  # 环境（dev/st/uat/prd）
    name = Column("tool_name", String(128), nullable=False, index=True)
    type = Column("tool_type", String(64), nullable=False)
    source_name = Column("src_name", String(128), nullable=False, default="")
    description = Column("tool_desc", Text, default="")
    params = Column(Text, default="{}")  # JSON 字符串
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ToolsetRecord(Base):
    """工具集表 — 将工具聚合为 toolset。

    tool_names 用逗号分隔字符串存储。
    system_id + environment 为业务隔离维度。

    注意：数据库列名 `set_name` 避开保留字 `name`。
    """

    __tablename__ = "toolsets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(String(10), nullable=False, default="", index=True)
    environment = Column(String(16), nullable=False, default="", index=True)
    name = Column("set_name", String(128), nullable=False)
    tool_names = Column(Text, default="")  # 逗号分隔
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class McpRequestLogRecord(Base):
    """MCP 请求日志表 — 记录每次 MCP 协议调用，用于统计审计。

    每条记录对应一次 tools/list 或 tools/call 请求。
    system_id / environment / source_name / tool_name 为请求上下文维度。
    """

    __tablename__ = "mcp_request_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(String(10), nullable=False, default="", index=True)
    environment = Column(String(16), nullable=False, default="", index=True)
    source_name = Column(String(128), nullable=False, default="", index=True)
    tool_name = Column(String(128), nullable=False, default="")
    method = Column(String(32), nullable=False, index=True)  # tools/list, tools/call 等
    success = Column(Integer, nullable=False, default=1)  # 1 成功 0 失败
    latency_ms = Column(Integer, nullable=False, default=0)
    client_addr = Column(String(64), nullable=False, default="")
    error_msg = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now(), index=True)


# --- 模块级辅助函数（无状态，纯函数）---


def _parse_params_or_empty(params_str: str | None) -> dict[str, Any]:
    """解析 params JSON 字符串；空/解析失败返回 {}。非 dict 时原样返回（保持 update 语义）。"""
    if not params_str:
        return {}
    try:
        return json.loads(params_str)
    except json.JSONDecodeError:
        return {}


def _try_parse_json(value: str) -> Any:
    """尝试解析 JSON 字符串，失败返回 None。"""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_params_dict_or_empty(params_str: str | None) -> dict[str, Any]:
    """解析 params JSON 字符串；空/解析失败/非 dict 时均返回 {}。"""
    if not params_str:
        return {}
    parsed = _try_parse_json(params_str)
    return parsed if isinstance(parsed, dict) else {}


def _merge_params_setdefault(src: dict[str, Any], params_str: str | None) -> None:
    """将 params JSON 合并到 src（setdefault 语义：结构化字段优先）。"""
    for k, v in _parse_params_dict_or_empty(params_str).items():
        src.setdefault(k, v)


def _set_system_env_if_truthy(src: dict[str, Any], r: Any) -> None:
    """如果 r.system_id / r.environment 非空，写入 src['systemId'] / src['environment']。"""
    if r.system_id:
        src["systemId"] = r.system_id
    if r.environment:
        src["environment"] = r.environment


def _set_if_truthy(src: dict[str, Any], key: str, value: Any) -> None:
    """value 非空时写入 src[key]。"""
    if value:
        src[key] = value


def _set_source_database(src: dict[str, Any], database: Any, src_type: str) -> None:
    """sqlite 类型用 path 字段，其它用 database 字段。"""
    if not database:
        return
    if src_type == "sqlite":
        src["path"] = database
    else:
        src["database"] = database


def _set_password_decrypted(src: dict[str, Any], password: Any) -> None:
    """将解密后的密码写入 src['password']。"""
    if password:
        src["password"] = decrypt_password(password)


def _set_port_if_valid(src: dict[str, Any], port: Any) -> None:
    """port 为正整数时写入 src['port']。"""
    if port and port > 0:
        src["port"] = port


def _set_source_load_fields(src: dict[str, Any], r: SourceRecord) -> None:
    """load_sources 专用：按需填充 host/port/database/user/password（密码解密）。"""
    _set_if_truthy(src, "host", r.host)
    _set_port_if_valid(src, r.port)
    _set_source_database(src, r.database, r.type)
    _set_if_truthy(src, "user", r.username)
    _set_password_decrypted(src, r.password)


def _row_to_source_dict(r: SourceRecord) -> dict[str, Any]:
    """SourceRecord -> dict（密文密码，params 通过 update 合并：params 覆盖结构化字段）。"""
    src: dict[str, Any] = {
        "name": r.name,
        "type": r.type,
        "host": r.host,
        "port": r.port,
        "database": r.database,
        "user": r.username,
        "password": r.password,
    }
    src.update(_parse_params_or_empty(r.params))
    _set_system_env_if_truthy(src, r)
    return src


def _source_row_to_load_dict(r: SourceRecord) -> dict[str, Any]:
    """SourceRecord -> dict（load_sources 专用：条件字段、密码解密、params 通过 setdefault 合并）。"""
    src: dict[str, Any] = {"name": r.name, "type": r.type}
    _set_system_env_if_truthy(src, r)
    _set_source_load_fields(src, r)
    _merge_params_setdefault(src, r.params)
    return src


def _row_to_tool_dict(r: ToolRecord) -> dict[str, Any]:
    """ToolRecord -> dict（params 通过 update 合并：params 覆盖结构化字段）。"""
    tool: dict[str, Any] = {
        "name": r.name,
        "type": r.type,
        "source": r.source_name,
        "description": r.description,
    }
    tool.update(_parse_params_or_empty(r.params))
    _set_system_env_if_truthy(tool, r)
    return tool


def _tool_row_to_load_dict(r: ToolRecord) -> dict[str, Any]:
    """ToolRecord -> dict（load_tools 专用：空值强制为 ''，params 通过 setdefault 合并）。"""
    tool: dict[str, Any] = {
        "name": r.name,
        "type": r.type,
        "source": r.source_name or "",
        "description": r.description or "",
    }
    _set_system_env_if_truthy(tool, r)
    _merge_params_setdefault(tool, r.params)
    return tool


def _safe_split_commas(value: str | None) -> list[str]:
    """按逗号分割字符串，None 视为空串。"""
    return (value or "").split(",")


def _parse_tool_names(tool_names_str: str | None) -> list[dict[str, str]]:
    """逗号分隔字符串 -> [{name: ...}, ...]（过滤空值）。"""
    result: list[dict[str, str]] = []
    for tn in _safe_split_commas(tool_names_str):
        stripped = tn.strip()
        if stripped:
            result.append({"name": stripped})
    return result


def _row_to_toolset_dict(r: ToolsetRecord) -> dict[str, Any]:
    """ToolsetRecord -> dict。"""
    ts: dict[str, Any] = {
        "name": r.name,
        "tools": _parse_tool_names(r.tool_names),
    }
    _set_system_env_if_truthy(ts, r)
    return ts


def _apply_system_env_filters(stmt: Any, model: Any, system_id: str, environment: str) -> Any:
    """对 select 语句追加 system_id / environment 过滤（空值跳过）。"""
    if system_id:
        stmt = stmt.where(model.system_id == system_id)
    if environment:
        stmt = stmt.where(model.environment == environment)
    return stmt


def _get_str_field(config_data: dict[str, Any], key: str, default: str = "") -> str:
    """从 config_data 取字符串字段，None 安全（None 视为 default）。"""
    return str(config_data.get(key, default) or default)


def _get_int_field(config_data: dict[str, Any], key: str, default: int = 0) -> int:
    """从 config_data 取 int 字段，None 安全。"""
    return int(config_data.get(key, default) or default)


def _get_coalesced_str_field(
    config_data: dict[str, Any], primary: str, fallback: str, default: str = ""
) -> str:
    """优先取 primary 键，缺失时取 fallback，再 None 安全。"""
    value = config_data.get(primary, config_data.get(fallback, default))
    return str(value or default)


# SourceRecord 结构化字段集合 — 这些字段不进入 params JSON
_SOURCE_STRUCTURED_KEYS = frozenset(
    {
        "systemId",
        "environment",
        "host",
        "port",
        "database",
        "path",
        "user",
        "username",
        "password",
        "name",
        "type",
    }
)


def _build_params_json(config_data: dict[str, Any], structured_keys: frozenset[str]) -> str:
    """从 config_data 中过滤掉结构化字段，剩余字段序列化为 params JSON。"""
    params = {k: v for k, v in config_data.items() if k not in structured_keys}
    return json.dumps(params, ensure_ascii=False, default=str)


def _source_to_row_params(name: str, src_type: str, config_data: dict[str, Any]) -> dict[str, Any]:
    """从 config_data 提取 SourceRecord 列参数（含密码加密、params JSON 序列化）。"""
    system_id = _get_str_field(config_data, "systemId").strip()
    environment = _get_str_field(config_data, "environment").strip()
    host = str(config_data.get("host", ""))
    port = _get_int_field(config_data, "port", 0)
    database = _get_coalesced_str_field(config_data, "database", "path")
    username = _get_coalesced_str_field(config_data, "user", "username")
    password = normalize_password_for_storage(_get_str_field(config_data, "password"))
    params = _build_params_json(config_data, _SOURCE_STRUCTURED_KEYS)
    return {
        "system_id": system_id,
        "environment": environment,
        "name": name,
        "type": src_type,
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password,
        "params": params,
    }


def _apply_source_updates(existing: SourceRecord, row_params: dict[str, Any]) -> None:
    """用 row_params 更新已存在的 SourceRecord（不含 system_id/environment/name 这几个主键维度）。"""
    existing.type = row_params["type"]
    existing.host = row_params["host"]
    existing.port = row_params["port"]
    existing.database = row_params["database"]
    existing.username = row_params["username"]
    existing.password = row_params["password"]
    existing.params = row_params["params"]


# ToolRecord 结构化字段集合 — 这些字段不进入 params JSON
_TOOL_STRUCTURED_KEYS = frozenset(
    {
        "systemId",
        "environment",
        "name",
        "type",
        "source",
        "source_name",
        "description",
        "kind",
    }
)


def _tool_to_row_params(
    name: str,
    tool_type: str,
    source: str | None,
    description: str | None,
    config_data: dict[str, Any],
) -> dict[str, Any]:
    """从 config_data 提取 ToolRecord 列参数。"""
    system_id = _get_str_field(config_data, "systemId").strip()
    environment = _get_str_field(config_data, "environment").strip()
    params = _build_params_json(config_data, _TOOL_STRUCTURED_KEYS)
    return {
        "system_id": system_id,
        "environment": environment,
        "name": name,
        "type": tool_type,
        "source_name": source or "",
        "description": description or "",
        "params": params,
    }


def _apply_tool_updates(existing: ToolRecord, row_params: dict[str, Any]) -> None:
    """用 row_params 更新已存在的 ToolRecord。"""
    existing.type = row_params["type"]
    existing.source_name = row_params["source_name"]
    existing.description = row_params["description"]
    existing.params = row_params["params"]
    existing.system_id = row_params["system_id"]
    existing.environment = row_params["environment"]


def _toolset_to_row_params(
    name: str,
    tool_names: list[str],
    config_data: dict[str, Any],
) -> dict[str, Any]:
    """从 config_data 提取 ToolsetRecord 列参数。"""
    return {
        "system_id": _get_str_field(config_data, "systemId").strip(),
        "environment": _get_str_field(config_data, "environment").strip(),
        "name": name,
        "tool_names": ",".join(tool_names),
    }


def _extract_tool_names(ts_data: dict[str, Any]) -> list[str]:
    """从 toolset 配置中提取工具名列表。"""
    return [t["name"] for t in ts_data.get("tools", []) if "name" in t]


def _build_userinfo_when_no_username(password: str, quote: Any) -> str:
    """username 为空时构造 userinfo（仅密码或空串）。"""
    if not password:
        return ""
    return f":{quote(password, safe='')}"


def _build_userinfo(username: str, password: str, quote: Any) -> str:
    """构造 URL userinfo（user:pass 形式），空值返回空字符串。"""
    if not username:
        return _build_userinfo_when_no_username(password, quote)
    if not password:
        return quote(username, safe="")
    return f"{quote(username, safe='')}:{quote(password, safe='')}"


def _safe_url_for(url: str) -> str:
    """脱敏后的 URL（隐藏账号密码），用于日志。"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"


# MCP 日志查询过滤条件规约：(参数名, SQL 片段, 值转换函数)
_LOG_FILTER_SPEC: list[tuple[str, str, Any]] = [
    ("start_date", "created_at >= :start_date", lambda v: f"{v} 00:00:00"),
    ("end_date", "created_at <= :end_date", lambda v: f"{v} 23:59:59"),
    ("system_id", "system_id = :system_id", lambda v: v),
    ("environment", "environment = :environment", lambda v: v),
    ("source_name", "source_name = :source_name", lambda v: v),
]


def _join_where_clause(conditions: list[str]) -> str:
    """将条件列表拼接为 WHERE 子句；空列表返回空串。"""
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)


def _build_log_filter_clause(
    *,
    start_date: str | None,
    end_date: str | None,
    system_id: str,
    environment: str,
    source_name: str,
) -> tuple[str, dict[str, Any]]:
    """构建 MCP 日志查询的 WHERE 子句和参数字典。"""
    values = {
        "start_date": start_date,
        "end_date": end_date,
        "system_id": system_id,
        "environment": environment,
        "source_name": source_name,
    }
    conditions: list[str] = []
    params: dict[str, Any] = {}
    for key, sql, transform in _LOG_FILTER_SPEC:
        value = values[key]
        if not value:
            continue
        conditions.append(sql)
        params[key] = transform(value)
    return _join_where_clause(conditions), params


def _append_method_filter(
    where_clause: str, method: str = "tools/call"
) -> tuple[str, dict[str, Any]]:
    """在 where_clause 上追加 method 过滤；返回 (新 where_clause, 额外参数)。

    使用绑定参数而非字符串拼接,防止 SQL 注入风险。
    调用方需将返回的参数合并到 execute() 的 params 中。
    """
    method_param = {"method_filter": method}
    if where_clause:
        return where_clause + " AND method = :method_filter", method_param
    return " WHERE method = :method_filter", method_param


def _row_to_summary_dict(row: Any) -> dict[str, Any]:
    """汇总统计行转 dict；row 为空时返回零值。"""
    if not row:
        return {"total": 0, "success": 0, "fail": 0, "avg_latency_ms": 0}
    return {
        "total": row.total,
        "success": row.success,
        "fail": row.fail,
        "avg_latency_ms": row.avg_latency_ms,
    }


def _row_to_grouped_dict(
    row: Any,
    column: str,
    label: str,
    empty_default: str = "(未指定)",
) -> dict[str, Any]:
    """分组统计行转 dict，空值用 empty_default 填充。"""
    value = getattr(row, column) or empty_default
    return {label: value, "total": row.total, "success": row.success, "fail": row.fail}


def _row_to_timeline_dict(row: Any) -> dict[str, Any]:
    """时间线统计行转 dict。"""
    return {"date": str(row.date), "total": row.total, "success": row.success, "fail": row.fail}


def _or_empty(value: Any) -> str:
    """value 为假值时返回空串。"""
    return value or ""


def _format_log_time(value: Any) -> str:
    """格式化日志时间，空值返回空串。"""
    return str(value) if value else ""


def _row_to_log_dict(row: Any) -> dict[str, Any]:
    """MCP 日志行转 dict。"""
    return {
        "id": row.id,
        "system_id": _or_empty(row.system_id),
        "environment": _or_empty(row.environment),
        "source_name": _or_empty(row.source_name),
        "tool_name": _or_empty(row.tool_name),
        "method": row.method,
        "success": bool(row.success),
        "latency_ms": row.latency_ms,
        "client_addr": _or_empty(row.client_addr),
        "error_msg": _or_empty(row.error_msg),
        "created_at": _format_log_time(row.created_at),
    }


def _normalize_pagination(page: int, page_size: int) -> tuple[int, int, int]:
    """规范化分页参数，返回 (page, page_size, offset)。"""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    return page, page_size, (page - 1) * page_size


def _build_logs_response(
    items: list[dict[str, Any]], total: int, page: int, page_size: int
) -> dict[str, Any]:
    """构建分页响应 dict。"""
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def _build_mcp_log_record(
    *,
    system_id: str,
    environment: str,
    source_name: str,
    tool_name: str,
    method: str,
    success: bool,
    latency_ms: int,
    client_addr: str,
    error_msg: str,
) -> McpRequestLogRecord:
    """根据参数构建 McpRequestLogRecord 实例（字段截断保护）。"""
    return McpRequestLogRecord(
        system_id=system_id[:10],
        environment=environment[:16],
        source_name=source_name[:128],
        tool_name=tool_name[:128],
        method=method[:32],
        success=1 if success else 0,
        latency_ms=latency_ms,
        client_addr=client_addr[:64],
        error_msg=error_msg[:2000] if error_msg else "",
    )


def _match_url_prefix(url: str, prefixes: tuple[tuple[str, Any], ...]) -> Any:
    """在 prefixes 中查找 url 匹配的前缀，返回对应值；未匹配返回 None。"""
    for prefix, value in prefixes:
        if url.startswith(prefix):
            return value
    return None


def _format_host_port(parsed: Any) -> tuple[str, str]:
    """从 urlparse 结果提取 (host, port_str)，port_str 为 ':NN' 或 ''。"""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return host, port


def _build_netloc(userinfo: str, host: str, port: str) -> str:
    """拼接 netloc：有 userinfo 时加 'userinfo@' 前缀。"""
    if not userinfo:
        return f"{host}{port}"
    return f"{userinfo}@{host}{port}"


class ConfigStore:
    """配置存储层，封装所有持久化操作。

    表结构与 Config DB 完全统一，支持 SQLite/MySQL 两后端。
    """

    def __init__(self, store_url: str = "", username: str = "", password: str = ""):
        """初始化实例。"""
        # 若单独传入 username/password，则注入到 URL 的 netloc（覆盖 URL 中可能内联的凭据）
        url = store_url
        if username or password:
            url = self._inject_credentials(url, username, password)
        self._url = self._resolve_url_scheme(url)
        self._engine = None
        self._session_factory = None

    @staticmethod
    def _resolve_url_scheme(url: str) -> str:
        """根据 URL scheme 规范化 driver（注入 aiosqlite/aiomysql），未配置时回退默认 SQLite。"""
        if not url:
            return ConfigStore._default_sqlite_url()
        normalizer = _match_url_prefix(
            url,
            (
                ("sqlite", ConfigStore._normalize_sqlite_url),
                ("mysql", ConfigStore._normalize_mysql_url),
            ),
        )
        if normalizer is None:
            raise ValueError(f"不支持的 store_url scheme: {url}（仅支持 sqlite:// / mysql://）")
        return normalizer(url)

    @staticmethod
    def _default_sqlite_url() -> str:
        """返回默认 SQLite 文件 URL，并记录警告日志。"""
        import os

        db_path = os.path.join(os.getcwd(), "toolbox_data.db")
        logger.warning(
            "ConfigStore: 未配置 store_url，默认使用 SQLite 文件: %s。"
            "多实例部署时必须配置 --store-url 指向共享 MySQL，"
            "否则各实例数据隔离且不一致。",
            db_path,
        )
        return f"sqlite+aiosqlite:///{db_path}"

    @staticmethod
    def _normalize_sqlite_url(url: str) -> str:
        """规范化 SQLite URL，注入 aiosqlite driver。"""
        if "aiosqlite" not in url:
            url = url.replace("sqlite://", "sqlite+aiosqlite://")
        logger.info("ConfigStore: 使用 SQLite 文件存储: %s", url)
        return url

    @staticmethod
    def _normalize_mysql_url(url: str) -> str:
        """规范化 MySQL URL，注入 aiomysql driver。"""
        if "aiomysql" not in url:
            url = url.replace("mysql://", "mysql+aiomysql://")
        logger.info("ConfigStore: 使用 MySQL 存储: %s", _safe_url_for(url))
        return url

    @staticmethod
    def _inject_credentials(url: str, username: str, password: str) -> str:
        """将 username/password 注入 URL 的 netloc；若 URL 已内联凭据则覆盖。"""
        from urllib.parse import urlparse, urlunparse, quote

        parsed = urlparse(url)
        host, port = _format_host_port(parsed)
        userinfo = _build_userinfo(username, password, quote)
        netloc = _build_netloc(userinfo, host, port)
        return urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )

    def _safe_url(self) -> str:
        """返回脱敏后的 store URL，用于日志输出。"""
        return _safe_url_for(self._url)

    async def initialize(self) -> None:
        """初始化数据库引擎和会话工厂，创建表结构。"""
        import os

        pool_size = int(os.environ.get("TOOLBOX_DB_POOL_SIZE", "5"))
        self._engine = create_async_engine(
            self._url,
            echo=False,
            pool_size=pool_size,
            max_overflow=int(os.environ.get("TOOLBOX_DB_MAX_OVERFLOW", "10")),
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("ConfigStore: 初始化完成，表已就绪")

    async def close(self) -> None:
        """关闭并释放数据库引擎资源。"""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @property
    def is_persistent(self) -> bool:
        """是否为持久化存储（文件/MySQL）。内存 SQLite 视为非持久化。"""
        return ":memory:" not in self._url

    @property
    def is_sqlite(self) -> bool:
        """是否为 SQLite 后端。"""
        return "sqlite" in self._url

    async def _commit_with_integrity_check(self, session: AsyncSession, error_msg: str) -> None:
        """提交事务，捕获唯一键冲突转为 ValueError，其它异常重新抛出。"""
        from sqlalchemy.exc import IntegrityError

        try:
            await session.commit()
        except Exception as exc:
            if isinstance(exc, IntegrityError):
                raise ValueError(error_msg) from exc
            raise

    # --- Source CRUD ---

    async def save_source(self, name: str, src_type: str, config_data: dict[str, Any]) -> None:
        """保存或更新数据源配置。

        从 config_data 中提取结构化字段（system_id/environment/host/port/database/username/password），
        剩余字段存入 params JSON。密码在落库前加密。

        幂等处理: 如果传入的 password 已经是有效密文(能被 decrypt_password 解密),
        说明是编辑时未修改的原密文, 直接保留不重复加密; 否则视为新密码加密后落库。
        """
        row_params = _source_to_row_params(name, src_type, config_data)
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(SourceRecord).where(
                    SourceRecord.name == name,
                    SourceRecord.system_id == row_params["system_id"],
                    SourceRecord.environment == row_params["environment"],
                )
            )
            if existing:
                _apply_source_updates(existing, row_params)
            else:
                session.add(SourceRecord(**row_params))
            await self._commit_with_integrity_check(
                session,
                f"数据源 {name!r} 在系统 {row_params['system_id']} 环境 {row_params['environment']} 下已存在（并发冲突）",
            )

    async def get_source_password(
        self, name: str, system_id: str = "", environment: str = ""
    ) -> str:
        """读取数据源在数据库中存储的密码密文。

        用于编辑场景: _source_to_dict 返回密文给前端, 前端原样回传即可保持密码不变。
        未启用持久化或记录不存在时返回空字符串。
        可通过 system_id + environment 精确定位（不同环境下同名数据源密码可能不同）。
        """
        if not self.is_persistent:
            return ""
        async with self._session_factory() as session:
            stmt = select(SourceRecord).where(SourceRecord.name == name)
            stmt = _apply_system_env_filters(stmt, SourceRecord, system_id, environment)
            record = await session.scalar(stmt)
            return record.password if record else ""

    async def count_sources(self) -> int:
        """返回数据源总数，用于判断是否需要首次导入预置配置。"""
        from sqlalchemy import func as sa_func

        async with self._session_factory() as session:
            return await session.scalar(select(sa_func.count(SourceRecord.id))) or 0

    async def save_toolset(
        self,
        name: str,
        tool_names: list[str],
        config_data: dict[str, Any] | None = None,
    ) -> None:
        """保存或更新工具集配置。

        tool_names 用逗号分隔字符串存储。system_id / environment 从 config_data 提取。
        """
        config_data = config_data or {}
        row_params = _toolset_to_row_params(name, tool_names, config_data)

        async with self._session_factory() as session:
            existing = await session.scalar(
                select(ToolsetRecord).where(
                    ToolsetRecord.name == name,
                    ToolsetRecord.system_id == row_params["system_id"],
                    ToolsetRecord.environment == row_params["environment"],
                )
            )
            if existing:
                existing.tool_names = row_params["tool_names"]
            else:
                session.add(ToolsetRecord(**row_params))
            await self._commit_with_integrity_check(
                session,
                f"工具集 {name!r} 在系统 {row_params['system_id']} 环境 {row_params['environment']} 下已存在（并发冲突）",
            )

    async def count_toolsets(self) -> int:
        """返回工具集总数。"""
        from sqlalchemy import func as sa_func

        async with self._session_factory() as session:
            return await session.scalar(select(sa_func.count(ToolsetRecord.id))) or 0

    async def count_tools(self) -> int:
        """返回工具总数。"""
        from sqlalchemy import func as sa_func

        async with self._session_factory() as session:
            return await session.scalar(select(sa_func.count(ToolRecord.id))) or 0

    async def get_source(
        self, name: str, system_id: str = "", environment: str = ""
    ) -> dict[str, Any] | None:
        """按名查询单个数据源配置，返回合并后的 dict（含结构化字段和 params）。
        可选 system_id + environment 精确定位。
        不存在时返回 None。
        """
        async with self._session_factory() as session:
            stmt = select(SourceRecord).where(SourceRecord.name == name)
            stmt = _apply_system_env_filters(stmt, SourceRecord, system_id, environment)
            r = await session.scalar(stmt)
            return _row_to_source_dict(r) if r else None

    async def get_tool(
        self, name: str, system_id: str = "", environment: str = ""
    ) -> dict[str, Any] | None:
        """按名查询单个工具配置，返回合并后的 dict。
        不存在时返回 None。
        """
        async with self._session_factory() as session:
            stmt = select(ToolRecord).where(ToolRecord.name == name)
            stmt = _apply_system_env_filters(stmt, ToolRecord, system_id, environment)
            r = await session.scalar(stmt)
            return _row_to_tool_dict(r) if r else None

    async def load_tools_by_source(self, source_name: str) -> list[dict[str, Any]]:
        """按数据源名查询其所有工具配置。"""
        async with self._session_factory() as session:
            result = await session.scalars(
                select(ToolRecord).where(ToolRecord.source_name == source_name)
            )
            return [_row_to_tool_dict(r) for r in result]

    async def count_tools_by_source(self, source_name: str) -> int:
        """按数据源名统计工具数量。"""
        from sqlalchemy import func as sa_func

        async with self._session_factory() as session:
            return (
                await session.scalar(
                    select(sa_func.count(ToolRecord.id)).where(
                        ToolRecord.source_name == source_name
                    )
                )
                or 0
            )

    async def load_sources_by_system(self, system_id: str) -> list[dict[str, Any]]:
        """按系统编号查询数据源列表。"""
        async with self._session_factory() as session:
            result = await session.scalars(
                select(SourceRecord).where(SourceRecord.system_id == system_id)
            )
            sources = []
            for r in result:
                src = _row_to_source_dict(r)
                src["systemId"] = r.system_id
                sources.append(src)
            return sources

    async def get_toolset(
        self, name: str, system_id: str = "", environment: str = ""
    ) -> dict[str, Any] | None:
        """按名查询单个工具集配置。不存在时返回 None。"""
        async with self._session_factory() as session:
            stmt = select(ToolsetRecord).where(ToolsetRecord.name == name)
            stmt = _apply_system_env_filters(stmt, ToolsetRecord, system_id, environment)
            r = await session.scalar(stmt)
            return _row_to_toolset_dict(r) if r else None

    async def load_toolsets(self) -> list[dict[str, Any]]:
        """加载所有工具集。"""
        async with self._session_factory() as session:
            result = await session.scalars(select(ToolsetRecord))
            return [_row_to_toolset_dict(r) for r in result]

    async def delete_source(self, name: str, system_id: str = "", environment: str = "") -> None:
        """删除指定数据源配置。"""
        async with self._session_factory() as session:
            stmt = select(SourceRecord).where(SourceRecord.name == name)
            stmt = _apply_system_env_filters(stmt, SourceRecord, system_id, environment)
            record = await session.scalar(stmt)
            if record:
                await session.delete(record)
                await session.commit()

    async def delete_source_and_tools(
        self, name: str, system_id: str = "", environment: str = ""
    ) -> None:
        """原子删除数据源及其关联工具（单事务）。

        相比先调用 delete_source 再调用 delete_tools_by_source 的两次提交,
        该方法在单个 session/transaction 中完成 source 与 tools 的删除,
        避免出现中间状态（source 已删但 tools 残留,或反之）。
        用于 Admin API 的删除数据源流程。
        """
        async with self._session_factory() as session:
            # 先删工具,再删数据源(避免外键语义上的引用悬空)
            tool_stmt = select(ToolRecord).where(ToolRecord.source_name == name)
            tool_stmt = _apply_system_env_filters(tool_stmt, ToolRecord, system_id, environment)
            tool_records = list(await session.scalars(tool_stmt))
            for record in tool_records:
                await session.delete(record)

            source_stmt = select(SourceRecord).where(SourceRecord.name == name)
            source_stmt = _apply_system_env_filters(
                source_stmt, SourceRecord, system_id, environment
            )
            source_record = await session.scalar(source_stmt)
            if source_record:
                await session.delete(source_record)

            await session.commit()

    # --- 批量导入（YAML/Prebuilt → DB 一次性导入）---

    async def import_toolbox_file(self, tf: "ToolboxFile") -> dict[str, int]:
        """将 ToolboxFile（YAML/Prebuilt 解析结果）批量导入到 store。

        用于 `toolbox import` 子命令和首次启动时自动导入预置配置。
        幂等：同 (system_id, name) 的记录会更新而非重复创建。

        返回: {"sources": N, "tools": N, "toolsets": N} 导入计数。
        """
        counts = {"sources": 0, "tools": 0, "toolsets": 0}
        counts["sources"] = await self._import_sources(tf.sources)
        counts["tools"] = await self._import_tools(tf.tools)
        counts["toolsets"] = await self._import_toolsets(tf.toolsets)
        logger.info(
            "ToolboxFile 导入完成: %d sources, %d tools, %d toolsets",
            counts["sources"],
            counts["tools"],
            counts["toolsets"],
        )
        return counts

    async def _import_sources(self, sources: dict[str, Any]) -> int:
        """批量导入数据源配置(单 session 批量提交,避免 N+1 次往返)。"""
        count = 0
        async with self._session_factory() as session:
            for name, src_data in sources.items():
                src_type = src_data.get("type", "")
                if not src_type:
                    continue
                await self._save_source_in_session(session, name, src_type, src_data)
                count += 1
            await session.commit()
        return count

    async def _save_source_in_session(
        self, session: AsyncSession, name: str, src_type: str, config_data: dict[str, Any]
    ) -> None:
        """在已有 session 中保存数据源(不提交,由调用方统一提交)。"""
        row_params = _source_to_row_params(name, src_type, config_data)
        existing = await session.scalar(
            select(SourceRecord).where(
                SourceRecord.name == name,
                SourceRecord.system_id == row_params["system_id"],
                SourceRecord.environment == row_params["environment"],
            )
        )
        if existing:
            _apply_source_updates(existing, row_params)
        else:
            session.add(SourceRecord(**row_params))

    async def _import_tools(self, tools: dict[str, Any]) -> int:
        """批量导入工具配置(单 session 批量提交,避免 N+1 次往返)。"""
        count = 0
        async with self._session_factory() as session:
            for name, tool_data in tools.items():
                tool_type = tool_data.get("type", "")
                if not tool_type:
                    continue
                source = tool_data.get("source", "")
                description = tool_data.get("description", "")
                await self._save_tool_in_session(
                    session, name, tool_type, source, description, tool_data
                )
                count += 1
            await session.commit()
        return count

    async def _save_tool_in_session(
        self,
        session: AsyncSession,
        name: str,
        tool_type: str,
        source: str | None,
        description: str | None,
        config_data: dict[str, Any],
    ) -> None:
        """在已有 session 中保存工具(不提交,由调用方统一提交)。"""
        row_params = _tool_to_row_params(name, tool_type, source, description, config_data)
        existing = await session.scalar(
            select(ToolRecord).where(
                ToolRecord.name == name,
                ToolRecord.system_id == row_params["system_id"],
                ToolRecord.environment == row_params["environment"],
            )
        )
        if existing:
            _apply_tool_updates(existing, row_params)
        else:
            session.add(ToolRecord(**row_params))

    async def _import_toolsets(self, toolsets: dict[str, Any]) -> int:
        """批量导入工具集配置(单 session 批量提交,避免 N+1 次往返)。"""
        count = 0
        async with self._session_factory() as session:
            for name, ts_data in toolsets.items():
                tool_names = _extract_tool_names(ts_data)
                await self._save_toolset_in_session(session, name, tool_names, ts_data)
                count += 1
            await session.commit()
        return count

    async def _save_toolset_in_session(
        self,
        session: AsyncSession,
        name: str,
        tool_names: list[str],
        config_data: dict[str, Any],
    ) -> None:
        """在已有 session 中保存工具集(不提交,由调用方统一提交)。"""
        row_params = _toolset_to_row_params(name, tool_names, config_data)
        existing = await session.scalar(
            select(ToolsetRecord).where(
                ToolsetRecord.name == name,
                ToolsetRecord.system_id == row_params["system_id"],
                ToolsetRecord.environment == row_params["environment"],
            )
        )
        if existing:
            # toolset 仅 tool_names 字段可更新(system_id/environment 为键不可变)
            existing.tool_names = row_params["tool_names"]
        else:
            session.add(ToolsetRecord(**row_params))

    async def load_sources(self) -> list[dict[str, Any]]:
        """加载所有数据源，合并结构化字段和 params。"""
        async with self._session_factory() as session:
            result = await session.scalars(select(SourceRecord))
            return [_source_row_to_load_dict(r) for r in result]

    # --- Tool CRUD ---

    async def save_tool(
        self,
        name: str,
        tool_type: str,
        source: str | None,
        description: str | None,
        config_data: dict[str, Any],
    ) -> None:
        """保存或更新工具配置。

        从 config_data 中提取结构化字段（含 systemId / environment），剩余存入 params JSON。
        systemId / environment 冗余存储到 tools 对应列，便于按系统编号+环境查询。
        """
        row_params = _tool_to_row_params(name, tool_type, source, description, config_data)

        async with self._session_factory() as session:
            existing = await session.scalar(
                select(ToolRecord).where(
                    ToolRecord.name == name,
                    ToolRecord.system_id == row_params["system_id"],
                    ToolRecord.environment == row_params["environment"],
                )
            )
            if existing:
                _apply_tool_updates(existing, row_params)
            else:
                session.add(ToolRecord(**row_params))
            await self._commit_with_integrity_check(
                session,
                f"工具 {name!r} 在系统 {row_params['system_id']} 环境 {row_params['environment']} 下已存在（并发冲突）",
            )

    async def delete_tool(self, name: str, system_id: str = "", environment: str = "") -> None:
        """删除指定工具配置。"""
        async with self._session_factory() as session:
            stmt = select(ToolRecord).where(ToolRecord.name == name)
            stmt = _apply_system_env_filters(stmt, ToolRecord, system_id, environment)
            record = await session.scalar(stmt)
            if record:
                await session.delete(record)
                await session.commit()

    async def delete_tools_by_source(
        self, source_name: str, system_id: str = "", environment: str = ""
    ) -> None:
        """删除指定数据源下的所有工具配置。"""
        async with self._session_factory() as session:
            stmt = select(ToolRecord).where(ToolRecord.source_name == source_name)
            stmt = _apply_system_env_filters(stmt, ToolRecord, system_id, environment)
            result = await session.scalars(stmt)
            for record in result:
                await session.delete(record)
            await session.commit()

    async def load_tools(self) -> list[dict[str, Any]]:
        """加载所有工具，合并结构化字段和 params。"""
        async with self._session_factory() as session:
            result = await session.scalars(select(ToolRecord))
            return [_tool_row_to_load_dict(r) for r in result]

    # --- MCP 请求日志 ---

    async def log_mcp_request(
        self,
        *,
        system_id: str = "",
        environment: str = "",
        source_name: str = "",
        tool_name: str = "",
        method: str,
        success: bool = True,
        latency_ms: int = 0,
        client_addr: str = "",
        error_msg: str = "",
    ) -> None:
        """异步写入一条 MCP 请求日志（失败时静默，不影响主流程）。"""
        try:
            record = _build_mcp_log_record(
                system_id=system_id,
                environment=environment,
                source_name=source_name,
                tool_name=tool_name,
                method=method,
                success=success,
                latency_ms=latency_ms,
                client_addr=client_addr,
                error_msg=error_msg,
            )
            async with self._session_factory() as session:
                session.add(record)
                await session.commit()
        except Exception as exc:
            logger.warning("写入 MCP 请求日志失败: %s", exc)

    async def query_mcp_stats(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        system_id: str = "",
        environment: str = "",
        source_name: str = "",
    ) -> dict[str, Any]:
        """聚合查询 MCP 请求统计。

        参数:
            start_date: 起始日期 YYYY-MM-DD（含），None 表示不限
            end_date:   截止日期 YYYY-MM-DD（含），None 表示不限
            system_id:  筛选系统编号，空串表示不限
            environment: 筛选环境标识，空串表示不限
            source_name: 筛选数据源名称，空串表示不限

        返回:
            {
              "summary": {"total": N, "success": N, "fail": N, "avg_latency_ms": N},
              "by_system": [{"system_id": "...", "total": N, "success": N, "fail": N}],
              "by_environment": [{"environment": "...", "total": N, "success": N, "fail": N}],
              "by_source": [{"source_name": "...", "total": N, "success": N, "fail": N}],
              "by_tool":   [{"tool_name": "...", "total": N, "success": N, "fail": N}],
              "timeline":  [{"date": "YYYY-MM-DD", "total": N, "success": N, "fail": N}],
            }
        """
        where_clause, params = _build_log_filter_clause(
            start_date=start_date,
            end_date=end_date,
            system_id=system_id,
            environment=environment,
            source_name=source_name,
        )
        async with self._session_factory() as session:
            summary = await self._query_stats_summary(session, where_clause, params)
            by_system = await self._query_stats_grouped(
                session, where_clause, params, "system_id", "system_id"
            )
            by_environment = await self._query_stats_grouped(
                session, where_clause, params, "environment", "environment"
            )
            by_source = await self._query_stats_grouped(
                session, where_clause, params, "source_name", "source_name"
            )
            by_tool = await self._query_stats_by_tool(session, where_clause, params)
            timeline = await self._query_stats_timeline(session, where_clause, params)
            return {
                "summary": summary,
                "by_system": by_system,
                "by_environment": by_environment,
                "by_source": by_source,
                "by_tool": by_tool,
                "timeline": timeline,
            }

    async def _query_stats_summary(
        self, session: AsyncSession, where_clause: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """查询统计汇总（总数/成功/失败/平均延迟）。"""
        from sqlalchemy import text

        row = (
            await session.execute(
                text(f"""
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                    COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail,
                    COALESCE(ROUND(AVG(latency_ms), 0), 0) AS avg_latency_ms
                FROM mcp_request_logs{where_clause}
            """),
                params,
            )
        ).fetchone()
        return _row_to_summary_dict(row)

    async def _query_stats_grouped(
        self,
        session: AsyncSession,
        where_clause: str,
        params: dict[str, Any],
        column: str,
        label: str,
    ) -> list[dict[str, Any]]:
        """按指定列分组查询统计。"""
        from sqlalchemy import text

        rows = (
            await session.execute(
                text(f"""
                SELECT {column},
                       COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                       COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail
                FROM mcp_request_logs{where_clause}
                GROUP BY {column}
                ORDER BY total DESC
            """),
                params,
            )
        ).fetchall()
        return [_row_to_grouped_dict(r, column, label) for r in rows]

    async def _query_stats_by_tool(
        self, session: AsyncSession, where_clause: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """按工具名查询调用统计（仅 tools/call）。"""
        # by_tool 只统计 tools/call，tools/list 不分工具
        from sqlalchemy import text

        tool_where, method_param = _append_method_filter(where_clause)
        merged_params = {**params, **method_param}
        rows = (
            await session.execute(
                text(f"""
                SELECT tool_name,
                       COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                       COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail
                FROM mcp_request_logs{tool_where}
                GROUP BY tool_name
                ORDER BY total DESC
                LIMIT 50
            """),
                merged_params,
            )
        ).fetchall()
        return [_row_to_grouped_dict(r, "tool_name", "tool_name", "(未知)") for r in rows]

    async def _query_stats_timeline(
        self, session: AsyncSession, where_clause: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """按日期查询调用时间线统计。"""
        # SQLite 用 DATE()，MySQL 用 DATE()，两者都支持
        from sqlalchemy import text

        rows = (
            await session.execute(
                text(f"""
                SELECT DATE(created_at) AS date,
                       COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                       COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail
                FROM mcp_request_logs{where_clause}
                GROUP BY DATE(created_at)
                ORDER BY date ASC
            """),
                params,
            )
        ).fetchall()
        return [_row_to_timeline_dict(r) for r in rows]

    async def query_mcp_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        start_date: str | None = None,
        end_date: str | None = None,
        system_id: str = "",
        environment: str = "",
        source_name: str = "",
    ) -> dict[str, Any]:
        """分页查询 MCP 请求记录明细（最新记录排在最前面）。

        返回:
            {
              "items": [{id, system_id, environment, source_name, tool_name, method,
                         success, latency_ms, client_addr, error_msg, created_at}],
              "total": N,
              "page": N,
              "page_size": N,
              "total_pages": N,
            }
        """
        where_clause, params = _build_log_filter_clause(
            start_date=start_date,
            end_date=end_date,
            system_id=system_id,
            environment=environment,
            source_name=source_name,
        )
        page, page_size, offset = _normalize_pagination(page, page_size)
        async with self._session_factory() as session:
            total = await self._query_logs_total(session, where_clause, params)
            items = await self._query_logs_items(session, where_clause, params, page_size, offset)
            return _build_logs_response(items, total, page, page_size)

    async def _query_logs_total(
        self, session: AsyncSession, where_clause: str, params: dict[str, Any]
    ) -> int:
        """查询日志总数。"""
        from sqlalchemy import text

        row = (
            await session.execute(
                text(f"SELECT COUNT(*) AS cnt FROM mcp_request_logs{where_clause}"),
                params,
            )
        ).fetchone()
        return row.cnt if row else 0

    async def _query_logs_items(
        self,
        session: AsyncSession,
        where_clause: str,
        params: dict[str, Any],
        page_size: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """查询日志明细列表（分页）。"""
        from sqlalchemy import text

        rows = (
            await session.execute(
                text(f"""
                SELECT id, system_id, environment, source_name, tool_name, method,
                       success, latency_ms, client_addr, error_msg, created_at
                FROM mcp_request_logs{where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
            """),
                {**params, "limit": page_size, "offset": offset},
            )
        ).fetchall()
        return [_row_to_log_dict(r) for r in rows]


# 全局单例
_store: ConfigStore | None = None


def get_store() -> ConfigStore | None:
    """获取全局 ConfigStore 实例。"""
    return _store


def set_store(store: ConfigStore) -> None:
    """设置全局 ConfigStore 实例。"""
    global _store
    _store = store


async def init_store(store_url: str = "", username: str = "", password: str = "") -> ConfigStore:
    """创建并初始化 ConfigStore，注册为全局单例。"""
    store = ConfigStore(store_url, username, password)
    await store.initialize()
    set_store(store)
    return store
