"""DB ConfigReader — 从 MySQL 数据库读取配置。

Aligns with Go: internal/dbconfigreader/reader.go
Expected table schema: see docker/init-mysql.sql

  departments (id, name, display_name, created_at, updated_at)
  sources     (id, dept_id, name, type, host, port, database, username, password, params TEXT)
  tools       (id, dept_id, name, type, source_name, description, params TEXT)
  toolsets    (id, dept_id, name, tool_names TEXT, created_at, updated_at)
  api_keys    (id, dept_id, key_hash, description, ...)

Usage:
  1. Set TOOLBOX_CONFIG_DB_URL=mysql://user:pass@host:3306/configdb
  2. (Optional) Set ENV_PASSWORDS='{"MYSQL_PASSWORD":"realpass"}'
  3. Pass --config-db-url <url> to toolbox serve, or leave in env var
"""

from __future__ import annotations

import asyncio
import hashlib
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


def _normalize_dept_name(name: str) -> str:
    """Normalize a filePath-style name to department name.

    Maps to Go: dbconfigreader.normalizeDeptName()
    - "dept-orders.yaml" → "dept-orders"
    - "configs/dept-orders.yml" → "dept-orders"
    - "dept-orders" → "dept-orders"
    - "all" or "" → "" (means load all departments)
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
    dept_name: str | None = None,
) -> dict[str, Any]:
    """Load configuration from MySQL database.

    Returns a ToolboxFile-compatible dict:
      {"sources": {...}, "tools": {...}, "toolsets": {...}}

    Maps to Go: dbconfigreader.Reader.read()
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

    # Normalize dept_name
    search_dept = _normalize_dept_name(dept_name or "")

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
            if search_dept:
                # Load a single department
                await _load_dept(session, search_dept, sources, tools, toolsets, env_passwords)
            else:
                # Load ALL departments
                rows = await session.execute(text("SELECT name FROM departments ORDER BY name"))
                for row in rows.fetchall():
                    try:
                        await _load_dept(session, row[0], sources, tools, toolsets, env_passwords)
                    except Exception as exc:
                        logger.warning("skipping department %r: %s", row[0], exc)
    finally:
        await engine.dispose()

    return {"sources": sources, "tools": tools, "toolsets": toolsets}


async def _load_dept(
    session: AsyncSession,
    dept_name: str,
    sources: dict[str, Any],
    tools: dict[str, Any],
    toolsets: dict[str, Any],
    env_passwords: dict[str, str],
) -> None:
    """Load sources, tools, and toolset for a single department.

    Maps to Go: dbconfigreader.readDept()
    """
    # Look up department
    row = await session.execute(
        text("SELECT id FROM departments WHERE name = :name"),
        {"name": dept_name},
    )
    dept_row = row.fetchone()
    if dept_row is None:
        raise ValueError(f"department {dept_name!r} not found")
    dept_id = dept_row[0]

    # -- Sources --
    src_rows = await session.execute(
        text("""
            SELECT name, type, host, port, database, username, password, params
            FROM sources
            WHERE dept_id = :dept_id
            ORDER BY name
        """),
        {"dept_id": dept_id},
    )
    for src_row in src_rows.fetchall():
        name, src_type, host, port, database, username, password, params_json = src_row
        src_config: dict[str, Any] = {
            "kind": "source",
            "name": name,
            "type": src_type,
            "host": host,
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
    tool_rows = await session.execute(
        text("""
            SELECT name, type, source_name, description, params
            FROM tools
            WHERE dept_id = :dept_id
            ORDER BY name
        """),
        {"dept_id": dept_id},
    )
    for tool_row in tool_rows.fetchall():
        name, tool_type, source_name, description, params_json = tool_row
        tool_config: dict[str, Any] = {
            "kind": "tool",
            "name": name,
            "type": tool_type,
            "source": source_name or "",
            "description": description or "",
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
    ts_row = await session.execute(
        text("""
            SELECT name, tool_names
            FROM toolsets
            WHERE dept_id = :dept_id
        """),
        {"dept_id": dept_id},
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


async def resolve_dept_by_api_key(db_url: str, api_key: str) -> str | None:
    """Resolve a department name from an api_key.

    Looks up ``api_keys.key_hash = SHA256(api_key)`` — the exact same hashing
    the Admin API uses when storing keys — joins to ``departments``, and returns
    the department name. Expired keys (``expires_at < NOW()``) are rejected.
    Returns ``None`` if the key is unknown or expired.

    This is the consumer side of the ``api_keys`` table: pass an api_key at
    Toolbox startup (``--api-key`` / ``TOOLBOX_API_KEY``) to bind the instance
    to a single department, enforcing department-level isolation. The Admin API
    issues these keys; the Toolbox never sees the plaintext again.

    Args:
        db_url: MySQL URL (env ``TOOLBOX_CONFIG_DB_URL``).
        api_key: the raw api_key string (e.g. from ``X-API-Key`` or env).
    """
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    async_url = _to_async_url(db_url)

    engine = create_async_engine(async_url, pool_recycle=3600, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            row = await session.execute(
                text("""
                    SELECT d.name
                    FROM api_keys k
                    JOIN departments d ON d.id = k.dept_id
                    WHERE k.key_hash = :key_hash
                      AND (k.expires_at IS NULL OR k.expires_at > NOW())
                """),
                {"key_hash": key_hash},
            )
            result = row.fetchone()
            return result[0] if result else None
    finally:
        await engine.dispose()


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

    Args:
        db_url: MySQL URL (env ``TOOLBOX_CONFIG_DB_URL``).
        on_change: coroutine to invoke (debounced) when a change is detected.
        env_passwords_json: JSON mapping for ``${VAR}`` resolution (unused here,
            kept for signature parity with ``load_config_from_db``).
        poll_interval: 轮询间隔（秒），默认 5 秒。
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
                    tables = ["departments", "sources", "tools", "toolsets", "api_keys"]
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
