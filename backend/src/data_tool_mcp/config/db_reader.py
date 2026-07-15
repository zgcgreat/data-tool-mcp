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


def _normalize_system_id(name: str) -> str:
    """Normalize a filePath-style name to system_id.

    - "system-001.yaml" → "system-001"
    - "configs/system-001.yml" → "system-001"
    - "system-001" → "system-001"
    - "all" or "" → "" (means load all systems)
    """
    # Strip directory
    if "/" in name:
        name = name.rsplit("/", 1)[1]
    if "\\" in name:
        name = name.rsplit("\\", 1)[1]
    # Strip .yaml/.yml extension
    if name.endswith(".yaml"):
        name = name[:-5]
    elif name.endswith(".yml"):
        name = name[:-4]
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
    if db_url.startswith("mysql://"):
        return db_url.replace("mysql://", "mysql+aiomysql://", 1)
    if db_url.startswith("mysql+pymysql://"):
        return db_url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
    # 兜底：假设是裸 URL
    return f"mysql+aiomysql://{db_url}"


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
    db_url = db_url or os.environ.get("TOOLBOX_CONFIG_DB_URL", "")
    if not db_url:
        raise ValueError(
            "TOOLBOX_CONFIG_DB_URL not set. "
            "Provide --config-db-url or set the TOOLBOX_CONFIG_DB_URL environment variable."
        )

    # Parse ENV_PASSWORDS
    env_passwords: dict[str, str] = {}
    ep_json = env_passwords_json or os.environ.get("ENV_PASSWORDS", "{}")
    if ep_json:
        try:
            env_passwords = json.loads(ep_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ENV_PASSWORDS is not valid JSON: {exc}") from exc

    # Normalize system_id
    search_system = _normalize_system_id(system_id or "")
    # Normalize environment
    search_env = _normalize_environment(environment or "")

    # Convert to async URL
    async_url = _to_async_url(db_url)

    # MySQL 连接池配置：wait_timeout 默认 8 小时，但生产环境可能更短
    engine = create_async_engine(
        async_url,
        pool_size=2,
        pool_recycle=3600,  # 1 小时回收，避免 MySQL 连接超时
        pool_pre_ping=True,  # 连接前检测有效性
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sources: dict[str, Any] = {}
    tools: dict[str, Any] = {}
    toolsets: dict[str, Any] = {}

    try:
        async with session_factory() as session:
            if search_system:
                # Load a single system
                await _load_system(session, search_system, sources, tools, toolsets, env_passwords, search_env)
            else:
                # Load ALL systems — 查询 distinct system_id
                rows = await session.execute(
                    text("SELECT DISTINCT system_id FROM sources WHERE system_id != '' ORDER BY system_id")
                )
                for row in rows.fetchall():
                    try:
                        await _load_system(session, row[0], sources, tools, toolsets, env_passwords, search_env)
                    except Exception as exc:
                        logger.warning("skipping system %r: %s", row[0], exc)
    finally:
        await engine.dispose()

    return {"sources": sources, "tools": tools, "toolsets": toolsets}


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
    # -- Sources --
    # 注意：列名加前缀避开 MySQL 保留字（name/type/database/host/password）
    if environment:
        src_rows = await session.execute(
            text("""
                SELECT src_name, src_type, db_host, db_port, db_name, db_user, db_password, params, environment
                FROM sources
                WHERE system_id = :system_id AND environment = :environment
                ORDER BY src_name
            """),
            {"system_id": system_id, "environment": environment},
        )
    else:
        src_rows = await session.execute(
            text("""
                SELECT src_name, src_type, db_host, db_port, db_name, db_user, db_password, params, environment
                FROM sources
                WHERE system_id = :system_id
                ORDER BY src_name
            """),
            {"system_id": system_id},
        )
    for src_row in src_rows.fetchall():
        name, src_type, host, port, database, username, password, params_json, environment_val = src_row
        src_config: dict[str, Any] = {
            "kind": "source",
            "name": name,
            "type": src_type,
            "host": host,
            "systemId": system_id,
            "environment": environment_val,
        }
        if port and port > 0:
            src_config["port"] = port
        if database:
            src_config["database"] = database
        if username:
            src_config["user"] = username
        # Resolve password: ${VAR} → real value via ENV_PASSWORDS
        if password:
            resolved = _resolve_password(password, env_passwords)
            if resolved:
                src_config["password"] = resolved
        # Merge JSON params (e.g., {"sslmode": "require", "protocol": "..."})
        if params_json:
            try:
                parsed = json.loads(params_json) if isinstance(params_json, str) else params_json
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        src_config[k] = v
            except (json.JSONDecodeError, TypeError):
                pass

        sources[name] = src_config

    # -- Tools --
    # 列名加 tool_ 前缀避开保留字
    if environment:
        tool_rows = await session.execute(
            text("""
                SELECT tool_name, tool_type, src_name, tool_desc, params, environment
                FROM tools
                WHERE system_id = :system_id AND environment = :environment
                ORDER BY tool_name
            """),
            {"system_id": system_id, "environment": environment},
        )
    else:
        tool_rows = await session.execute(
            text("""
                SELECT tool_name, tool_type, src_name, tool_desc, params, environment
                FROM tools
                WHERE system_id = :system_id
                ORDER BY tool_name
            """),
            {"system_id": system_id},
        )
    for tool_row in tool_rows.fetchall():
        name, tool_type, source_name, description, params_json, environment_val = tool_row
        tool_config: dict[str, Any] = {
            "kind": "tool",
            "name": name,
            "type": tool_type,
            "source": source_name or "",
            "description": description or "",
            "environment": environment_val,
        }
        if params_json:
            try:
                parsed = json.loads(params_json) if isinstance(params_json, str) else params_json
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        tool_config[k] = v
            except (json.JSONDecodeError, TypeError):
                pass
        tools[name] = tool_config

    # -- Toolset --
    # 列名 set_name 避开保留字 name
    ts_row = await session.execute(
        text("""
            SELECT set_name, tool_names
            FROM toolsets
            WHERE system_id = :system_id
        """),
        {"system_id": system_id},
    )
    ts_row_data = ts_row.fetchone()
    if ts_row_data:
        ts_name = ts_row_data[0]
        tool_names = ts_row_data[1] or ""
        # MySQL TEXT 存逗号分隔字符串，解析为列表
        if isinstance(tool_names, str):
            tool_names = [t.strip() for t in tool_names.split(",") if t.strip()]
        else:
            tool_names = list(tool_names)
        toolsets[ts_name] = {
            "kind": "toolset",
            "name": ts_name,
            "tools": [{"name": tn} for tn in tool_names],
        }


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
    engine = create_async_engine(
        async_url,
        pool_size=1,
        pool_recycle=3600,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 记录上次各表的最大 updated_at
    last_signature: dict[str, str] = {}

    logger.info("DB config watch started (MySQL 轮询模式，间隔 %.1fs)", poll_interval)

    try:
        while True:
            try:
                async with session_factory() as session:
                    # 查询各表的 MAX(updated_at) 作为变更指纹
                    tables = ["sources", "tools", "toolsets"]
                    current_signature: dict[str, str] = {}
                    for table_name in tables:
                        row = await session.execute(
                            text(f"SELECT COALESCE(MAX(updated_at), '1970-01-01') FROM {table_name}")
                        )
                        result = row.fetchone()
                        current_signature[table_name] = str(result[0]) if result else ""

                    # 首次运行只记录，不触发
                    if last_signature:
                        changed = current_signature != last_signature
                        if changed:
                            changed_tables = [
                                t for t in tables
                                if current_signature.get(t) != last_signature.get(t)
                            ]
                            logger.info(
                                "检测到配置变更（表: %s）— 重新加载资源",
                                ", ".join(changed_tables),
                            )
                            try:
                                await on_change()
                            except Exception as exc:  # noqa: BLE001
                                logger.error("DB config reload failed: %s", exc)

                    last_signature = current_signature

            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("DB config watch error (%s); retrying", exc)

            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        logger.info("DB config watch stopped")
    finally:
        await engine.dispose()
