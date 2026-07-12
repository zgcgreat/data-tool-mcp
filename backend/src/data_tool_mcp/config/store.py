"""配置持久化存储层 — 与 MCP 协议表（Config DB）统一的 Schema。

表结构与 docker/init-mysql.sql 完全对齐：
  - departments  (id, name, display_name, created_at, updated_at)
  - sources      (id, dept_id, name, type, host, port, database, username, password, params, ...)
  - tools        (id, dept_id, name, type, source_name, description, params, ...)
  - toolsets     (id, dept_id, name, tool_names, ...)
  - api_keys     (id, dept_id, key_hash, description, created_at, expires_at)

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

import base64
import json
import logging
import os
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Password encryption — application-level Fernet encryption for source passwords.
# The encryption key is derived from TOOLBOX_ENCRYPTION_KEY env var (or a
# default development key). In production, set TOOLBOX_ENCRYPTION_KEY to a
# strong random value (32+ bytes, base64-encoded for Fernet).
# ---------------------------------------------------------------------------
_ENCRYPTION_KEY_ENV = "TOOLBOX_ENCRYPTION_KEY"
_DEFAULT_KEY_FALLBACK = "dev-only-key-do-not-use-in-production-0123456789"
_fernet = None


def _get_fernet():
    """Lazy-initialize Fernet cipher for password encryption."""
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
        key_env = os.environ.get(_ENCRYPTION_KEY_ENV, "")
        if key_env:
            # Use provided key (must be valid base64 32-byte key)
            _fernet = Fernet(key_env.encode() if isinstance(key_env, str) else key_env)
        else:
            # Derive a stable key from the fallback for development
            import hashlib
            key = base64.urlsafe_b64encode(
                hashlib.sha256(_DEFAULT_KEY_FALLBACK.encode()).digest()
            )
            _fernet = Fernet(key)
    except ImportError:
        logger.warning("cryptography not available — passwords stored in plaintext")
        _fernet = False  # Sentinel: encryption disabled
    except Exception as exc:
        logger.warning("Fernet init failed (%s) — passwords stored in plaintext", exc)
        _fernet = False
    return _fernet


def encrypt_password(plaintext: str) -> str:
    """Encrypt a password for storage. Returns encrypted string or plaintext if encryption unavailable."""
    if not plaintext:
        return ""
    f = _get_fernet()
    if not f:
        return plaintext
    try:
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.warning("password encryption failed: %s", exc)
        return plaintext


def decrypt_password(ciphertext: str) -> str:
    """Decrypt a stored password. Returns plaintext or original if decryption fails."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    if not f:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        # Not encrypted (legacy plaintext) or wrong key — return as-is
        return ciphertext


class Base(DeclarativeBase):
    pass


class DepartmentRecord(Base):
    """部门表 — 多租户隔离的核心。"""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SourceRecord(Base):
    """数据源表 — 用户添加的数据库连接配置。

    与系统 A 的 sources 表完全对齐：
    结构化字段（host/port/database/username/password）+ params（JSON 扩展参数）。
    """
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dept_id = Column(Integer, nullable=True, index=True)  # NULL = 默认部门（单租户模式）
    name = Column(String(128), nullable=False, index=True)
    type = Column(String(64), nullable=False)
    host = Column(String(255), nullable=False, default="")
    port = Column(Integer, default=0)
    database = Column(String(128), default="")
    username = Column(String(128), default="")
    password = Column(String(512), default="")
    params = Column(Text, default="{}")  # JSON 字符串
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ToolRecord(Base):
    """工具表 — MCP 工具定义。

    与系统 A 的 tools 表完全对齐：
    source_name 引用 sources.name，params 存额外工具参数。
    """
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dept_id = Column(Integer, nullable=True, index=True)  # NULL = 默认部门
    name = Column(String(128), nullable=False, index=True)
    type = Column(String(64), nullable=False)
    source_name = Column(String(128), nullable=False, default="")
    description = Column(Text, default="")
    params = Column(Text, default="{}")  # JSON 字符串
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ToolsetRecord(Base):
    """工具集表 — 将工具聚合为 toolset。

    与系统 A 的 toolsets 表对齐：
    tool_names 用逗号分隔字符串存储。
    """
    __tablename__ = "toolsets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dept_id = Column(Integer, nullable=True, index=True)
    name = Column(String(128), nullable=False)
    tool_names = Column(Text, default="")  # 逗号分隔
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApiKeyRecord(Base):
    """API 密钥表 — 员工访问鉴权。

    与系统 A 的 api_keys 表完全对齐：
    key_hash = SHA256(原始密钥)。
    """
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dept_id = Column(Integer, nullable=True, index=True)
    key_hash = Column(String(128), unique=True, nullable=False)
    description = Column(String(255), default="")
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)


# --- 默认部门 ID（单租户模式下使用）---
_DEFAULT_DEPT_NAME = "default"
_default_dept_id_cache: int | None = None


class ConfigStore:
    """配置存储层，封装所有持久化操作。

    表结构与 Config DB 完全统一，支持 SQLite/MySQL 两后端。
    """

    def __init__(self, store_url: str = "", username: str = "", password: str = ""):
        # 若单独传入 username/password，则注入到 URL 的 netloc（覆盖 URL 中可能内联的凭据）
        url = store_url
        if username or password:
            url = self._inject_credentials(url, username, password)
        self._url = url
        self._engine = None
        self._session_factory = None

        if not url:
            # 默认使用当前工作目录下的 SQLite 文件
            import os
            db_path = os.path.join(os.getcwd(), "toolbox_data.db")
            self._url = f"sqlite+aiosqlite:///{db_path}"
            logger.info("ConfigStore: 未配置 store_url，默认使用 SQLite 文件: %s", db_path)
        elif url.startswith("sqlite"):
            if "aiosqlite" not in url:
                self._url = url.replace("sqlite://", "sqlite+aiosqlite://")
            logger.info("ConfigStore: 使用 SQLite 文件存储: %s", url)
        elif url.startswith("mysql"):
            if "aiomysql" not in url:
                self._url = url.replace("mysql://", "mysql+aiomysql://")
            logger.info("ConfigStore: 使用 MySQL 存储: %s", self._safe_url())
        else:
            raise ValueError(
                f"不支持的 store_url scheme: {url}"
                "（仅支持 sqlite:// / mysql://）"
            )

    @staticmethod
    def _inject_credentials(url: str, username: str, password: str) -> str:
        """将 username/password 注入 URL 的 netloc；若 URL 已内联凭据则覆盖。"""
        from urllib.parse import urlparse, urlunparse, quote
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        userinfo = ""
        if username:
            userinfo += quote(username, safe="")
        if password:
            userinfo += ":" + quote(password, safe="")
        netloc = f"{userinfo}@{host}{port}" if userinfo else f"{host}{port}"
        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

    def _safe_url(self) -> str:
        """脱敏后的 URL（隐藏账号密码），用于日志。"""
        from urllib.parse import urlparse
        parsed = urlparse(self._url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}{parsed.path}"

    async def initialize(self) -> None:
        self._engine = create_async_engine(
            self._url,
            echo=False,
            pool_size=5,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # 确保默认部门存在（单租户模式）
        await self._ensure_default_dept()
        logger.info("ConfigStore: 初始化完成，表已就绪")

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @property
    def is_persistent(self) -> bool:
        """是否为持久化存储（文件/MySQL）。内存 SQLite 视为非持久化。"""
        return ":memory:" not in self._url

    async def _ensure_default_dept(self) -> None:
        """确保默认部门存在（单租户模式下 dept_id 使用此 ID）。"""
        global _default_dept_id_cache
        if _default_dept_id_cache is not None:
            return
        async with self._session_factory() as session:
            record = await session.scalar(
                select(DepartmentRecord).where(DepartmentRecord.name == _DEFAULT_DEPT_NAME)
            )
            if record is None:
                record = DepartmentRecord(name=_DEFAULT_DEPT_NAME, display_name="默认部门")
                session.add(record)
                await session.commit()
                await session.refresh(record)
            _default_dept_id_cache = record.id

    def _dept_id(self) -> int:
        """获取默认部门 ID（单租户模式）。"""
        if _default_dept_id_cache is None:
            raise RuntimeError("ConfigStore 未初始化，请先调用 initialize()")
        return _default_dept_id_cache

    # --- Source CRUD ---

    async def save_source(self, name: str, src_type: str, config_data: dict[str, Any]) -> None:
        """保存或更新数据源配置。

        从 config_data 中提取结构化字段（host/port/database/username/password），
        剩余字段存入 params JSON。密码在落库前加密。
        """
        dept_id = self._dept_id()
        host = str(config_data.get("host", ""))
        port = int(config_data.get("port", 0) or 0)
        database = str(config_data.get("database", config_data.get("path", "")) or "")
        username = str(config_data.get("user", config_data.get("username", "")) or "")
        password = encrypt_password(str(config_data.get("password", "") or ""))

        # params 存储非结构化字段
        structured_keys = {"host", "port", "database", "path", "user", "username", "password", "name", "type"}
        params = {k: v for k, v in config_data.items() if k not in structured_keys}
        params_json = json.dumps(params, ensure_ascii=False, default=str)

        async with self._session_factory() as session:
            existing = await session.scalar(
                select(SourceRecord).where(
                    SourceRecord.name == name,
                    SourceRecord.dept_id == dept_id,
                )
            )
            if existing:
                existing.type = src_type
                existing.host = host
                existing.port = port
                existing.database = database
                existing.username = username
                existing.password = password
                existing.params = params_json
            else:
                session.add(SourceRecord(
                    dept_id=dept_id,
                    name=name,
                    type=src_type,
                    host=host,
                    port=port,
                    database=database,
                    username=username,
                    password=password,
                    params=params_json,
                ))
            await session.commit()

    async def delete_source(self, name: str) -> None:
        dept_id = self._dept_id()
        async with self._session_factory() as session:
            record = await session.scalar(
                select(SourceRecord).where(
                    SourceRecord.name == name,
                    SourceRecord.dept_id == dept_id,
                )
            )
            if record:
                await session.delete(record)
                await session.commit()

    async def load_sources(self) -> list[dict[str, Any]]:
        """加载所有数据源，合并结构化字段和 params。"""
        dept_id = self._dept_id()
        async with self._session_factory() as session:
            result = await session.scalars(
                select(SourceRecord).where(SourceRecord.dept_id == dept_id)
            )
            sources = []
            for r in result:
                src: dict[str, Any] = {
                    "name": r.name,
                    "type": r.type,
                }
                if r.host:
                    src["host"] = r.host
                if r.port and r.port > 0:
                    src["port"] = r.port
                if r.database:
                    # sqlite 类型用 path 字段
                    if r.type == "sqlite":
                        src["path"] = r.database
                    else:
                        src["database"] = r.database
                if r.username:
                    src["user"] = r.username
                if r.password:
                    src["password"] = decrypt_password(r.password)
                # 合并 params JSON
                if r.params:
                    try:
                        parsed = json.loads(r.params)
                        if isinstance(parsed, dict):
                            for k, v in parsed.items():
                                src.setdefault(k, v)
                    except (json.JSONDecodeError, TypeError):
                        pass
                sources.append(src)
            return sources

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

        从 config_data 中提取结构化字段，剩余存入 params JSON。
        """
        dept_id = self._dept_id()
        source_name = source or ""
        desc = description or ""

        # params 存储非结构化字段
        structured_keys = {"name", "type", "source", "source_name", "description", "kind"}
        params = {k: v for k, v in config_data.items() if k not in structured_keys}
        params_json = json.dumps(params, ensure_ascii=False, default=str)

        async with self._session_factory() as session:
            existing = await session.scalar(
                select(ToolRecord).where(
                    ToolRecord.name == name,
                    ToolRecord.dept_id == dept_id,
                )
            )
            if existing:
                existing.type = tool_type
                existing.source_name = source_name
                existing.description = desc
                existing.params = params_json
            else:
                session.add(ToolRecord(
                    dept_id=dept_id,
                    name=name,
                    type=tool_type,
                    source_name=source_name,
                    description=desc,
                    params=params_json,
                ))
            await session.commit()

    async def delete_tool(self, name: str) -> None:
        dept_id = self._dept_id()
        async with self._session_factory() as session:
            record = await session.scalar(
                select(ToolRecord).where(
                    ToolRecord.name == name,
                    ToolRecord.dept_id == dept_id,
                )
            )
            if record:
                await session.delete(record)
                await session.commit()

    async def delete_tools_by_source(self, source_name: str) -> None:
        dept_id = self._dept_id()
        async with self._session_factory() as session:
            result = await session.scalars(
                select(ToolRecord).where(
                    ToolRecord.source_name == source_name,
                    ToolRecord.dept_id == dept_id,
                )
            )
            for record in result:
                await session.delete(record)
            await session.commit()

    async def load_tools(self) -> list[dict[str, Any]]:
        """加载所有工具，合并结构化字段和 params。"""
        dept_id = self._dept_id()
        async with self._session_factory() as session:
            result = await session.scalars(
                select(ToolRecord).where(ToolRecord.dept_id == dept_id)
            )
            tools = []
            for r in result:
                tool: dict[str, Any] = {
                    "name": r.name,
                    "type": r.type,
                    "source": r.source_name or "",
                    "description": r.description or "",
                }
                # 合并 params JSON
                if r.params:
                    try:
                        parsed = json.loads(r.params)
                        if isinstance(parsed, dict):
                            for k, v in parsed.items():
                                tool.setdefault(k, v)
                    except (json.JSONDecodeError, TypeError):
                        pass
                tools.append(tool)
            return tools

    # --- Department CRUD ---

    async def list_departments(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.scalars(select(DepartmentRecord))
            return [
                {"id": r.id, "name": r.name, "display_name": r.display_name}
                for r in result
            ]

    # --- ApiKey CRUD ---

    async def save_api_key(self, dept_id: int, key_hash: str, description: str = "") -> None:
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(ApiKeyRecord).where(ApiKeyRecord.key_hash == key_hash)
            )
            if existing:
                existing.dept_id = dept_id
                existing.description = description
            else:
                session.add(ApiKeyRecord(
                    dept_id=dept_id, key_hash=key_hash, description=description
                ))
            await session.commit()

    async def list_api_keys(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.scalars(select(ApiKeyRecord))
            return [
                {
                    "id": r.id,
                    "dept_id": r.dept_id,
                    "key_hash": r.key_hash,
                    "description": r.description,
                    "created_at": r.created_at,
                    "expires_at": r.expires_at,
                }
                for r in result
            ]


# 全局单例
_store: ConfigStore | None = None


def get_store() -> ConfigStore | None:
    return _store


def set_store(store: ConfigStore) -> None:
    global _store
    _store = store


async def init_store(store_url: str = "", username: str = "", password: str = "") -> ConfigStore:
    store = ConfigStore(store_url, username, password)
    await store.initialize()
    set_store(store)
    return store
