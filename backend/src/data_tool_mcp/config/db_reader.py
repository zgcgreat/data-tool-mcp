"""DB ConfigReader — 从 MySQL 数据库读取配置。

Aligns with Go: internal/dbconfigreader/reader.go
Expected table schema: see docker/init-mysql.sql

  sources     (id, system_id, name, type, host, port, database, username, password, params TEXT)
  tools       (id, system_id, name, type, source_name, description, params TEXT)
  toolsets    (id, system_id, name, tool_names TEXT, created_at, updated_at)

Usage:
  1. Set TOOLBOX_CONFIG_DB_URL=mysql://user:pass@host:3306/configdb
  2. (Optional) Set ENV_PASSWORDS='{"MYSQL_PASSWORD":"realpass"}'
  3. Pass --config-db-url <url> to toolbox serve, or leave in env var
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_password(raw: str, env_passwords: dict[str, str]) -> str:
    """Resolve ${VAR} placeholders using the ENV_PASSWORDS mapping.

    Maps to Go: dbconfigreader.resolvePassword()
    """
    m = _ENV_PATTERN.match(raw)
    if m:
        var_name = m.group(1)
        if var_name in env_passwords:
            return env_passwords[var_name]
        # Fallback to OS env
        return os.environ.get(var_name, raw)
    return raw


def _strip_dir(name: str) -> str:
    """去除路径中的目录部分（同时支持 / 和 \\）。"""
    for sep in ("/", "\\"):
        if sep in name:
            name = name.rsplit(sep, 1)[1]
    return name


def _strip_yaml_ext(name: str) -> str:
    """去除 .yaml / .yml 扩展名。"""
    for ext in (".yaml", ".yml"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def _normalize_system_id(name: str) -> str:
    """Normalize a filePath-style name to system_id.

    - "system-001.yaml" → "system-001"
    - "configs/system-001.yml" → "system-001"
    - "system-001" → "system-001"
    - "all" or "" → "" (means load all systems)
    """
    name = _strip_dir(name)
    name = _strip_yaml_ext(name)
    name = name.strip()
    if name == "all" or not name:
        return ""
    return name


def _normalize_environment(name: str) -> str:
    """归一化 environment 参数。

    - "all" 或 "" → ""（表示加载所有环境）
    - 其他 → 原样返回
    """
    name = name.strip()
    if name == "all" or not name:
        return ""
    return name


def _to_async_url(db_url: str) -> str:
    """将 MySQL URL 转换为 SQLAlchemy 异步驱动 URL。"""
    if db_url.startswith("mysql+aiomysql://"):
        return db_url
    return _convert_to_async_url(db_url)


def _convert_to_async_url(db_url: str) -> str:
    """将非 async 的 mysql URL 转换为 aiomysql 驱动 URL；兜底按裸 URL 处理。"""
    for src, dst in (
        ("mysql+pymysql://", "mysql+aiomysql://"),
        ("mysql://", "mysql+aiomysql://"),
    ):
        if db_url.startswith(src):
            return db_url.replace(src, dst, 1)
    return f"mysql+aiomysql://{db_url}"


def _resolve_db_url(db_url: str | None) -> str:
    """获取并校验数据库 URL。"""
    db_url = db_url or os.environ.get("TOOLBOX_CONFIG_DB_URL", "")
    if not db_url:
        raise ValueError(
            "TOOLBOX_CONFIG_DB_URL not set. "
            "Provide --config-db-url or set the TOOLBOX_CONFIG_DB_URL environment variable."
        )
    return db_url


def _safe_parse_json(ep_json: str) -> dict[str, str]:
    """解析 JSON 字符串；失败时抛出 ValueError。"""
    try:
        return json.loads(ep_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ENV_PASSWORDS is not valid JSON: {exc}") from exc


def _parse_env_passwords_json(ep_json: str) -> dict[str, str]:
    """解析 ENV_PASSWORDS JSON 字符串；空字符串返回空 dict。"""
    if not ep_json:
        return {}
    return _safe_parse_json(ep_json)


def _parse_env_passwords(env_passwords_json: str | None) -> dict[str, str]:
    """解析 ENV_PASSWORDS JSON 字符串为 dict。"""
    ep_json = env_passwords_json or os.environ.get("ENV_PASSWORDS", "{}")
    return _parse_env_passwords_json(ep_json)


async def _load_all_systems(
    session: AsyncSession,
    sources: dict[str, Any],
    tools: dict[str, Any],
    toolsets: dict[str, Any],
    env_passwords: dict[str, str],
    search_env: str,
) -> None:
    """加载所有系统配置；单个系统加载失败仅记录日志。"""
    rows = await session.execute(
        text("SELECT DISTINCT system_id FROM sources WHERE system_id != '' ORDER BY system_id")
    )
    for row in rows.fetchall():
        try:
            await _load_system(session, row[0], sources, tools, toolsets, env_passwords, search_env)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skipping system %r: %s", row[0], exc)


async def _load_configs_from_session(
    session: AsyncSession,
    search_system: str,
    sources: dict[str, Any],
    tools: dict[str, Any],
    toolsets: dict[str, Any],
    env_passwords: dict[str, str],
    search_env: str,
) -> None:
    """根据 search_system 加载单个或全部系统配置。"""
    if search_system:
        await _load_system(session, search_system, sources, tools, toolsets, env_passwords, search_env)
        return
    await _load_all_systems(session, sources, tools, toolsets, env_passwords, search_env)


async def load_config_from_db(
    db_url: str | None = None,
    env_passwords_json: str | None = None,
    system_id: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    """Load configuration from MySQL database.

    Returns a ToolboxFile-compatible dict:
      {"sources": {...}, "tools": {...}, "toolsets": {...}}

    Maps to Go: dbconfigreader.Reader.read()

    加载范围说明：
      - system_id + environment：加载单个系统的单个环境
      - 仅 system_id：加载该系统所有环境
      - 都没有：加载所有系统的所有环境
    """
    db_url = _resolve_db_url(db_url)
    env_passwords = _parse_env_passwords(env_passwords_json)
    search_system = _normalize_system_id(system_id or "")
    search_env = _normalize_environment(environment or "")
    async_url = _to_async_url(db_url)

    # MySQL 连接池配置：wait_timeout 默认 8 小时，但生产环境可能更短
    pool_size = int(os.environ.get("TOOLBOX_DB_POOL_SIZE", "2"))
    engine = create_async_engine(
        async_url,
        pool_size=pool_size,
        pool_recycle=3600,  # 1 小时回收，避免 MySQL 连接超时
        pool_pre_ping=True,  # 连接前检测有效性
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sources: dict[str, Any] = {}
    tools: dict[str, Any] = {}
    toolsets: dict[str, Any] = {}

    try:
        async with session_factory() as session:
            await _load_configs_from_session(
                session, search_system, sources, tools, toolsets, env_passwords, search_env
            )
    finally:
        await engine.dispose()

    return {"sources": sources, "tools": tools, "toolsets": toolsets}


def _build_env_filter(environment: str) -> str:
    """构造 environment 过滤的 SQL 片段。"""
    if environment:
        return "AND environment = :environment"
    return ""


def _build_query_params(system_id: str, environment: str) -> dict[str, Any]:
    """构造系统级查询的参数 dict。"""
    params: dict[str, Any] = {"system_id": system_id}
    if environment:
        params["environment"] = environment
    return params


def _parse_params_payload(params_json: Any) -> Any:
    """解析 params JSON 字符串或返回原对象；解析失败返回 None。"""
    try:
        return json.loads(params_json) if isinstance(params_json, str) else params_json
    except (json.JSONDecodeError, TypeError):
        return None


def _merge_params_json(params_json: Any, config: dict[str, Any]) -> None:
    """解析 params JSON 并合并到 config；非 dict 或解析失败时静默忽略。"""
    if not params_json:
        return
    parsed = _parse_params_payload(params_json)
    if isinstance(parsed, dict):
        config.update(parsed)


def _set_if_truthy(config: dict[str, Any], key: str, value: Any) -> None:
    """当 value 为真值时设置到 config。"""
    if value:
        config[key] = value


def _set_port_if_valid(config: dict[str, Any], port: Any) -> None:
    """port 为正数时设置。"""
    if port and port > 0:
        config["port"] = port


def _populate_source_password(
    src_config: dict[str, Any],
    password: Any,
    env_passwords: dict[str, str],
) -> None:
    """解析 ${VAR} 占位符并填充密码字段。"""
    if not password:
        return
    resolved = _resolve_password(password, env_passwords)
    if resolved:
        src_config["password"] = resolved


def _populate_source_optional_fields(
    src_config: dict[str, Any],
    port: Any,
    database: Any,
    username: Any,
    password: Any,
    env_passwords: dict[str, str],
) -> None:
    """填充数据源的可选结构化字段。"""
    _set_port_if_valid(src_config, port)
    _set_if_truthy(src_config, "database", database)
    _set_if_truthy(src_config, "user", username)
    _populate_source_password(src_config, password, env_passwords)


def _build_source_config(row: tuple, system_id: str, env_passwords: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """从 sources 表行构造 (name, config_dict)。"""
    name, src_type, host, port, database, username, password, params_json, environment_val = row
    src_config: dict[str, Any] = {
        "kind": "source",
        "name": name,
        "type": src_type,
        "host": host,
        "systemId": system_id,
        "environment": environment_val,
    }
    _populate_source_optional_fields(src_config, port, database, username, password, env_passwords)
    _merge_params_json(params_json, src_config)
    return name, src_config


def _build_tool_config(row: tuple) -> tuple[str, dict[str, Any]]:
    """从 tools 表行构造 (name, config_dict)。"""
    name, tool_type, source_name, description, params_json, environment_val = row
    tool_config: dict[str, Any] = {
        "kind": "tool",
        "name": name,
        "type": tool_type,
        "source": source_name or "",
        "description": description or "",
        "environment": environment_val,
    }
    _merge_params_json(params_json, tool_config)
    return name, tool_config


def _split_comma_separated(value: str) -> list[str]:
    """将逗号分隔字符串拆分为去空白项列表。"""
    return [t.strip() for t in value.split(",") if t.strip()]


def _parse_tool_names(tool_names: Any) -> list[str]:
    """将 tool_names 字段解析为字符串列表（逗号分隔字符串或可迭代对象）。"""
    if not tool_names:
        return []
    if isinstance(tool_names, str):
        return _split_comma_separated(tool_names)
    return list(tool_names)


async def _load_system_sources(
    session: AsyncSession,
    system_id: str,
    sources: dict[str, Any],
    env_passwords: dict[str, str],
    environment: str,
) -> None:
    """加载单个系统的所有 sources。"""
    env_clause = _build_env_filter(environment)
    sql = f"""
        SELECT src_name, src_type, db_host, db_port, db_name, db_user, db_password, params, environment
        FROM sources
        WHERE system_id = :system_id {env_clause}
        ORDER BY src_name
    """
    rows = await session.execute(text(sql), _build_query_params(system_id, environment))
    for row in rows.fetchall():
        name, src_config = _build_source_config(row, system_id, env_passwords)
        sources[name] = src_config


async def _load_system_tools(
    session: AsyncSession,
    system_id: str,
    tools: dict[str, Any],
    environment: str,
) -> None:
    """加载单个系统的所有 tools。"""
    env_clause = _build_env_filter(environment)
    sql = f"""
        SELECT tool_name, tool_type, src_name, tool_desc, params, environment
        FROM tools
        WHERE system_id = :system_id {env_clause}
        ORDER BY tool_name
    """
    rows = await session.execute(text(sql), _build_query_params(system_id, environment))
    for row in rows.fetchall():
        name, tool_config = _build_tool_config(row)
        tools[name] = tool_config


async def _load_system_toolsets(
    session: AsyncSession,
    system_id: str,
    toolsets: dict[str, Any],
) -> None:
    """加载单个系统的 toolset。"""
    ts_row = await session.execute(
        text("""
            SELECT set_name, tool_names
            FROM toolsets
            WHERE system_id = :system_id
        """),
        {"system_id": system_id},
    )
    ts_row_data = ts_row.fetchone()
    if not ts_row_data:
        return
    ts_name = ts_row_data[0]
    tool_names = _parse_tool_names(ts_row_data[1])
    toolsets[ts_name] = {
        "kind": "toolset",
        "name": ts_name,
        "tools": [{"name": tn} for tn in tool_names],
    }


async def _load_system(
    session: AsyncSession,
    system_id: str,
    sources: dict[str, Any],
    tools: dict[str, Any],
    toolsets: dict[str, Any],
    env_passwords: dict[str, str],
    environment: str = "",
) -> None:
    """Load sources, tools, and toolset for a single system_id.

    Maps to Go: dbconfigreader.readDept()

    environment 为空字符串时加载该系统所有环境；非空时仅加载指定环境。
    """
    await _load_system_sources(session, system_id, sources, env_passwords, environment)
    await _load_system_tools(session, system_id, tools, environment)
    await _load_system_toolsets(session, system_id, toolsets)


_WATCH_TABLES = ["sources", "tools", "toolsets"]


async def _collect_table_signatures(session: AsyncSession, tables: list[str]) -> dict[str, str]:
    """查询各表的 MAX(updated_at) 作为变更指纹。"""
    signature: dict[str, str] = {}
    for table_name in tables:
        row = await session.execute(
            text(f"SELECT COALESCE(MAX(updated_at), '1970-01-01') FROM {table_name}")
        )
        result = row.fetchone()
        signature[table_name] = str(result[0]) if result else ""
    return signature


def _detect_changed_tables(
    tables: list[str],
    current: dict[str, str],
    last: dict[str, str],
) -> list[str]:
    """对比当前与上次指纹，返回发生变更的表名。"""
    return [t for t in tables if current.get(t) != last.get(t)]


async def _safe_on_change(on_change: Callable[[], Awaitable[None]]) -> None:
    """执行 on_change 回调；失败时仅记录日志。"""
    try:
        await on_change()
    except Exception as exc:  # noqa: BLE001
        logger.error("DB config reload failed: %s", exc)


async def _trigger_on_change(
    on_change: Callable[[], Awaitable[None]],
    tables: list[str],
    current: dict[str, str],
    last: dict[str, str],
) -> None:
    """检测变更并触发回调；首次运行（last 为空）或无变更时不触发。"""
    if not last:
        return
    changed_tables = _detect_changed_tables(tables, current, last)
    if not changed_tables:
        return
    logger.info("检测到配置变更（表: %s）— 重新加载资源", ", ".join(changed_tables))
    await _safe_on_change(on_change)


async def _watch_iteration_body(
    session_factory: async_sessionmaker,
    tables: list[str],
    last_signature: dict[str, str],
    on_change: Callable[[], Awaitable[None]],
) -> dict[str, str]:
    """单次轮询迭代的核心逻辑（不捕获异常）。"""
    async with session_factory() as session:
        current_signature = await _collect_table_signatures(session, tables)
        await _trigger_on_change(on_change, tables, current_signature, last_signature)
    return current_signature


async def _watch_iteration_safe(
    session_factory: async_sessionmaker,
    tables: list[str],
    last_signature: dict[str, str],
    on_change: Callable[[], Awaitable[None]],
) -> dict[str, str]:
    """执行一次轮询迭代；CancelledError 透传，其他异常吞掉以继续轮询。"""
    try:
        return await _watch_iteration_body(session_factory, tables, last_signature, on_change)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB config watch error (%s); retrying", exc)
        return last_signature


async def _run_watch_loop(
    session_factory: async_sessionmaker,
    tables: list[str],
    on_change: Callable[[], Awaitable[None]],
    poll_interval: float,
) -> None:
    """主轮询循环；CancelledError 透传给上层。"""
    last_signature: dict[str, str] = {}
    while True:
        last_signature = await _watch_iteration_safe(
            session_factory, tables, last_signature, on_change
        )
        await asyncio.sleep(poll_interval)


async def watch_config_changes(
    db_url: str,
    on_change: Callable[[], Awaitable[None]],
    env_passwords_json: str | None = None,
    poll_interval: float = 5.0,
) -> None:
    """轮询 MySQL 数据库检测配置变更并触发热重载。

    MySQL 不支持 LISTEN/NOTIFY，改用轮询机制：
    定期查询各表的 MAX(updated_at)，与上次记录的值比较，检测到变更则触发 on_change。

    Runs forever until the surrounding task is cancelled.
    """
    async_url = _to_async_url(db_url)
    pool_size = int(os.environ.get("TOOLBOX_DB_WATCH_POOL_SIZE", "1"))
    engine = create_async_engine(
        async_url,
        pool_size=pool_size,
        pool_recycle=3600,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    logger.info("DB config watch started (MySQL 轮询模式，间隔 %.1fs)", poll_interval)

    try:
        await _run_watch_loop(session_factory, _WATCH_TABLES, on_change, poll_interval)
    except asyncio.CancelledError:
        logger.info("DB config watch stopped")
    finally:
        await engine.dispose()
