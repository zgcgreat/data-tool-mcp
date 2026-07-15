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
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# 加解密统一入口 — 企业部署时可替换 utils/crypto.py 为 SM4/KMS 实现
from data_tool_mcp.utils.crypto import (
    decrypt_password,
    encrypt_password,
    is_encrypted,
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
    environment = Column(String(16), nullable=False, default="", index=True)  # 环境（dev/st/uat/prd）
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
    environment = Column(String(16), nullable=False, default="", index=True)  # 环境（dev/st/uat/prd）
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
    method = Column(String(32), nullable=False)  # tools/list, tools/call 等
    success = Column(Integer, nullable=False, default=1)  # 1 成功 0 失败
    latency_ms = Column(Integer, nullable=False, default=0)
    client_addr = Column(String(64), nullable=False, default="")
    error_msg = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now(), index=True)


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

    # --- Source CRUD ---

    async def save_source(self, name: str, src_type: str, config_data: dict[str, Any]) -> None:
        """保存或更新数据源配置。

        从 config_data 中提取结构化字段（system_id/environment/host/port/database/username/password），
        剩余字段存入 params JSON。密码在落库前加密。

        幂等处理: 如果传入的 password 已经是有效密文(能被 decrypt_password 解密),
        说明是编辑时未修改的原密文, 直接保留不重复加密; 否则视为新密码加密后落库。
        """
        system_id = str(config_data.get("systemId", "") or "").strip()
        environment = str(config_data.get("environment", "") or "").strip()
        host = str(config_data.get("host", ""))
        port = int(config_data.get("port", 0) or 0)
        database = str(config_data.get("database", config_data.get("path", "")) or "")
        username = str(config_data.get("user", config_data.get("username", "")) or "")
        # 密码幂等处理: 已是密文则保留, 否则视为新明文密码加密
        raw_password = str(config_data.get("password", "") or "")
        password = normalize_password_for_storage(raw_password)

        # params 存储非结构化字段（systemId/environment 作为结构化字段提取到独立列）
        structured_keys = {"systemId", "environment", "host", "port", "database", "path", "user", "username", "password", "name", "type"}
        params = {k: v for k, v in config_data.items() if k not in structured_keys}
        params_json = json.dumps(params, ensure_ascii=False, default=str)

        async with self._session_factory() as session:
            existing = await session.scalar(
                select(SourceRecord).where(
                    SourceRecord.name == name,
                    SourceRecord.system_id == system_id,
                    SourceRecord.environment == environment,
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
                    system_id=system_id,
                    environment=environment,
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

    async def get_source_password(self, name: str, system_id: str = "", environment: str = "") -> str:
        """读取数据源在数据库中存储的密码密文。

        用于编辑场景: _source_to_dict 返回密文给前端, 前端原样回传即可保持密码不变。
        未启用持久化或记录不存在时返回空字符串。
        可通过 system_id + environment 精确定位（不同环境下同名数据源密码可能不同）。
        """
        if not self.is_persistent:
            return ""
        async with self._session_factory() as session:
            stmt = select(SourceRecord).where(SourceRecord.name == name)
            if system_id:
                stmt = stmt.where(SourceRecord.system_id == system_id)
            if environment:
                stmt = stmt.where(SourceRecord.environment == environment)
            record = await session.scalar(stmt)
            return record.password if record else ""

    async def count_sources(self) -> int:
        """返回数据源总数，用于判断是否需要首次导入预置配置。"""
        from sqlalchemy import func as sa_func
        async with self._session_factory() as session:
            return await session.scalar(
                select(sa_func.count(SourceRecord.id))
            ) or 0

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
        system_id = str(config_data.get("systemId", "") or "").strip()
        environment = str(config_data.get("environment", "") or "").strip()
        tool_names_str = ",".join(tool_names)

        async with self._session_factory() as session:
            existing = await session.scalar(
                select(ToolsetRecord).where(
                    ToolsetRecord.name == name,
                    ToolsetRecord.system_id == system_id,
                    ToolsetRecord.environment == environment,
                )
            )
            if existing:
                existing.tool_names = tool_names_str
            else:
                session.add(ToolsetRecord(
                    system_id=system_id,
                    environment=environment,
                    name=name,
                    tool_names=tool_names_str,
                ))
            await session.commit()

    async def count_toolsets(self) -> int:
        """返回工具集总数。"""
        from sqlalchemy import func as sa_func
        async with self._session_factory() as session:
            return await session.scalar(
                select(sa_func.count(ToolsetRecord.id))
            ) or 0

    async def load_toolsets(self) -> list[dict[str, Any]]:
        """加载所有工具集。"""
        async with self._session_factory() as session:
            result = await session.scalars(
                select(ToolsetRecord)
            )
            toolsets = []
            for r in result:
                ts: dict[str, Any] = {
                    "name": r.name,
                    "tools": [
                        {"name": tn.strip()}
                        for tn in (r.tool_names or "").split(",")
                        if tn.strip()
                    ],
                }
                if r.system_id:
                    ts["systemId"] = r.system_id
                if r.environment:
                    ts["environment"] = r.environment
                toolsets.append(ts)
            return toolsets

    async def delete_source(self, name: str, system_id: str = "", environment: str = "") -> None:
        async with self._session_factory() as session:
            stmt = select(SourceRecord).where(SourceRecord.name == name)
            if system_id:
                stmt = stmt.where(SourceRecord.system_id == system_id)
            if environment:
                stmt = stmt.where(SourceRecord.environment == environment)
            record = await session.scalar(stmt)
            if record:
                await session.delete(record)
                await session.commit()

    # --- 批量导入（YAML/Prebuilt → DB 一次性导入）---

    async def import_toolbox_file(self, tf: "ToolboxFile") -> dict[str, int]:
        """将 ToolboxFile（YAML/Prebuilt 解析结果）批量导入到 store。

        用于 `toolbox import` 子命令和首次启动时自动导入预置配置。
        幂等：同 (system_id, name) 的记录会更新而非重复创建。

        返回: {"sources": N, "tools": N, "toolsets": N} 导入计数。
        """
        counts = {"sources": 0, "tools": 0, "toolsets": 0}

        # 导入数据源
        for name, src_data in tf.sources.items():
            src_type = src_data.get("type", "")
            if not src_type:
                continue
            await self.save_source(name, src_type, src_data)
            counts["sources"] += 1

        # 导入工具
        for name, tool_data in tf.tools.items():
            tool_type = tool_data.get("type", "")
            source = tool_data.get("source", "")
            description = tool_data.get("description", "")
            if not tool_type:
                continue
            await self.save_tool(name, tool_type, source, description, tool_data)
            counts["tools"] += 1

        # 导入工具集
        for name, ts_data in tf.toolsets.items():
            tool_names = [
                t["name"] for t in ts_data.get("tools", []) if "name" in t
            ]
            await self.save_toolset(name, tool_names, ts_data)
            counts["toolsets"] += 1

        logger.info(
            "ToolboxFile 导入完成: %d sources, %d tools, %d toolsets",
            counts["sources"], counts["tools"], counts["toolsets"],
        )
        return counts

    async def load_sources(self) -> list[dict[str, Any]]:
        """加载所有数据源，合并结构化字段和 params。"""
        async with self._session_factory() as session:
            result = await session.scalars(
                select(SourceRecord)
            )
            sources = []
            for r in result:
                src: dict[str, Any] = {
                    "name": r.name,
                    "type": r.type,
                }
                if r.system_id:
                    src["systemId"] = r.system_id
                if r.environment:
                    src["environment"] = r.environment
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

        从 config_data 中提取结构化字段（含 systemId / environment），剩余存入 params JSON。
        systemId / environment 冗余存储到 tools 对应列，便于按系统编号+环境查询。
        """
        source_name = source or ""
        desc = description or ""
        system_id = str(config_data.get("systemId", "") or "").strip()
        environment = str(config_data.get("environment", "") or "").strip()

        # params 存储非结构化字段
        structured_keys = {"systemId", "environment", "name", "type", "source", "source_name", "description", "kind"}
        params = {k: v for k, v in config_data.items() if k not in structured_keys}
        params_json = json.dumps(params, ensure_ascii=False, default=str)

        async with self._session_factory() as session:
            existing = await session.scalar(
                select(ToolRecord).where(
                    ToolRecord.name == name,
                    ToolRecord.system_id == system_id,
                    ToolRecord.environment == environment,
                )
            )
            if existing:
                existing.type = tool_type
                existing.source_name = source_name
                existing.description = desc
                existing.params = params_json
                existing.system_id = system_id
                existing.environment = environment
            else:
                session.add(ToolRecord(
                    system_id=system_id,
                    environment=environment,
                    name=name,
                    type=tool_type,
                    source_name=source_name,
                    description=desc,
                    params=params_json,
                ))
            await session.commit()

    async def delete_tool(self, name: str, system_id: str = "", environment: str = "") -> None:
        async with self._session_factory() as session:
            stmt = select(ToolRecord).where(ToolRecord.name == name)
            if system_id:
                stmt = stmt.where(ToolRecord.system_id == system_id)
            if environment:
                stmt = stmt.where(ToolRecord.environment == environment)
            record = await session.scalar(stmt)
            if record:
                await session.delete(record)
                await session.commit()

    async def delete_tools_by_source(self, source_name: str, system_id: str = "", environment: str = "") -> None:
        async with self._session_factory() as session:
            stmt = select(ToolRecord).where(ToolRecord.source_name == source_name)
            if system_id:
                stmt = stmt.where(ToolRecord.system_id == system_id)
            if environment:
                stmt = stmt.where(ToolRecord.environment == environment)
            result = await session.scalars(stmt)
            for record in result:
                await session.delete(record)
            await session.commit()

    async def load_tools(self) -> list[dict[str, Any]]:
        """加载所有工具，合并结构化字段和 params。"""
        async with self._session_factory() as session:
            result = await session.scalars(
                select(ToolRecord)
            )
            tools = []
            for r in result:
                tool: dict[str, Any] = {
                    "name": r.name,
                    "type": r.type,
                    "source": r.source_name or "",
                    "description": r.description or "",
                }
                if r.system_id:
                    tool["systemId"] = r.system_id
                if r.environment:
                    tool["environment"] = r.environment
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
            async with self._session_factory() as session:
                session.add(McpRequestLogRecord(
                    system_id=system_id[:10],
                    environment=environment[:16],
                    source_name=source_name[:128],
                    tool_name=tool_name[:128],
                    method=method[:32],
                    success=1 if success else 0,
                    latency_ms=latency_ms,
                    client_addr=client_addr[:64],
                    error_msg=error_msg[:2000] if error_msg else "",
                ))
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
        from sqlalchemy import text

        # 构建 WHERE 条件（命名参数，防注入）
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if start_date:
            conditions.append("created_at >= :start_date")
            params["start_date"] = f"{start_date} 00:00:00"
        if end_date:
            conditions.append("created_at < :end_date_exclusive")
            params["end_date_exclusive"] = f"{end_date} 23:59:59"
            # 用 < 次日 00:00:00 更准确，但为兼容 SQLite/MySQL，这里用 <= 当天结束
            conditions[-1] = "created_at <= :end_date_exclusive"
        if system_id:
            conditions.append("system_id = :system_id")
            params["system_id"] = system_id
        if environment:
            conditions.append("environment = :environment")
            params["environment"] = environment
        if source_name:
            conditions.append("source_name = :source_name")
            params["source_name"] = source_name

        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        async with self._session_factory() as session:
            # 1. summary
            summary_row = (await session.execute(
                text(f"""
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                        COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail,
                        COALESCE(ROUND(AVG(latency_ms), 0), 0) AS avg_latency_ms
                    FROM mcp_request_logs{where_clause}
                """),
                params,
            )).fetchone()
            summary = {
                "total": summary_row.total if summary_row else 0,
                "success": summary_row.success if summary_row else 0,
                "fail": summary_row.fail if summary_row else 0,
                "avg_latency_ms": summary_row.avg_latency_ms if summary_row else 0,
            }

            # 2. by_system（不受 system_id 过滤影响时才有意义；若已筛选 system_id 则只返回该系统）
            system_rows = (await session.execute(
                text(f"""
                    SELECT system_id,
                           COUNT(*) AS total,
                           COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                           COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail
                    FROM mcp_request_logs{where_clause}
                    GROUP BY system_id
                    ORDER BY total DESC
                """),
                params,
            )).fetchall()
            by_system = [
                {"system_id": r.system_id or "(未指定)", "total": r.total, "success": r.success, "fail": r.fail}
                for r in system_rows
            ]

            # 3. by_environment（与 by_system 对称；若已筛选 environment 则只返回该环境）
            environment_rows = (await session.execute(
                text(f"""
                    SELECT environment,
                           COUNT(*) AS total,
                           COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                           COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail
                    FROM mcp_request_logs{where_clause}
                    GROUP BY environment
                    ORDER BY total DESC
                """),
                params,
            )).fetchall()
            by_environment = [
                {"environment": r.environment or "(未指定)", "total": r.total, "success": r.success, "fail": r.fail}
                for r in environment_rows
            ]

            # 4. by_source
            source_rows = (await session.execute(
                text(f"""
                    SELECT source_name,
                           COUNT(*) AS total,
                           COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) AS success,
                           COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) AS fail
                    FROM mcp_request_logs{where_clause}
                    GROUP BY source_name
                    ORDER BY total DESC
                """),
                params,
            )).fetchall()
            by_source = [
                {"source_name": r.source_name or "(未指定)", "total": r.total, "success": r.success, "fail": r.fail}
                for r in source_rows
            ]

            # 5. by_tool（只统计 tools/call，tools/list 不分工具）
            tool_where = where_clause
            tool_params = dict(params)
            if "method" not in conditions:
                tool_where = (where_clause + " AND " if where_clause else " WHERE ") + "method = 'tools/call'"
            tool_rows = (await session.execute(
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
                tool_params,
            )).fetchall()
            by_tool = [
                {"tool_name": r.tool_name or "(未知)", "total": r.total, "success": r.success, "fail": r.fail}
                for r in tool_rows
            ]

            # 6. timeline（按天聚合）
            # SQLite 用 DATE()，MySQL 用 DATE()，两者都支持
            timeline_rows = (await session.execute(
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
            )).fetchall()
            timeline = [
                {"date": str(r.date), "total": r.total, "success": r.success, "fail": r.fail}
                for r in timeline_rows
            ]

            return {
                "summary": summary,
                "by_system": by_system,
                "by_environment": by_environment,
                "by_source": by_source,
                "by_tool": by_tool,
                "timeline": timeline,
            }

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
        from sqlalchemy import text

        conditions: list[str] = []
        params: dict[str, Any] = {}
        if start_date:
            conditions.append("created_at >= :start_date")
            params["start_date"] = f"{start_date} 00:00:00"
        if end_date:
            conditions.append("created_at <= :end_date_exclusive")
            params["end_date_exclusive"] = f"{end_date} 23:59:59"
        if system_id:
            conditions.append("system_id = :system_id")
            params["system_id"] = system_id
        if environment:
            conditions.append("environment = :environment")
            params["environment"] = environment
        if source_name:
            conditions.append("source_name = :source_name")
            params["source_name"] = source_name

        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        async with self._session_factory() as session:
            # 总数
            total_row = (await session.execute(
                text(f"SELECT COUNT(*) AS cnt FROM mcp_request_logs{where_clause}"),
                params,
            )).fetchone()
            total = total_row.cnt if total_row else 0
            total_pages = max(1, (total + page_size - 1) // page_size)

            # 分页明细（最新在前）
            rows = (await session.execute(
                text(f"""
                    SELECT id, system_id, environment, source_name, tool_name, method,
                           success, latency_ms, client_addr, error_msg, created_at
                    FROM mcp_request_logs{where_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                """),
                {**params, "limit": page_size, "offset": offset},
            )).fetchall()

            items = [
                {
                    "id": r.id,
                    "system_id": r.system_id or "",
                    "environment": r.environment or "",
                    "source_name": r.source_name or "",
                    "tool_name": r.tool_name or "",
                    "method": r.method,
                    "success": bool(r.success),
                    "latency_ms": r.latency_ms,
                    "client_addr": r.client_addr or "",
                    "error_msg": r.error_msg or "",
                    "created_at": str(r.created_at) if r.created_at else "",
                }
                for r in rows
            ]

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }


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
