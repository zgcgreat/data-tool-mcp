from __future__ import annotations

import logging
import os

import yaml
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from data_tool_mcp.config.store import get_store
from data_tool_mcp.sources import decode_source_config
from data_tool_mcp.tools import decode_tool_config

router = APIRouter(prefix="/admin", tags=["admin"])

logger = logging.getLogger(__name__)

# Directory holding the prebuilt *.yaml configs (sibling package data).
_PREBUILT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prebuiltconfigs")

# Mapping from registered source type → prebuilt yaml file name (when they differ).
_PREBUILT_YAML_OVERRIDES: dict[str, str] = {
    "alloydb-postgres": "alloydb-postgres",
    "cloud-sql-postgres": "cloud-sql-postgres",
    "cloud-sql-mysql": "cloud-sql-mysql",
    "cloud-sql-mssql": "cloud-sql-mssql",
    "oracle": "oracledb",
    "cloud-storage": "cloud-storage",
    "cloud-healthcare": "cloud-healthcare",
    "serverless-spark": "serverless-spark",
    "spanner": "spanner",
}

# Fallback tool specs used ONLY for source types that have NO prebuilt
# <type>.yaml (e.g. redis, mongodb, http). For types that DO ship a prebuilt
# yaml (postgres/mysql/mssql/sqlite/neo4j/elasticsearch/...), the full tool
# set is derived directly from that yaml by _load_prebuilt_tools(), so the
# entries below for those types are ignored.
# Spec = (tool name suffix, registered tool type).

# 预设环境列表（按命名规范顺序）
ENVIRONMENTS = ["dev", "st", "uat", "prd"]

_SOURCE_DEFAULT_TOOLS: dict[str, list[tuple[str, str]]] = {
    "postgres": [("execute-sql", "postgres-execute-sql")],
    "mysql": [("execute-sql", "mysql-execute-sql")],
    "mssql": [("execute-sql", "mssql-execute-sql")],
    "sqlite": [("execute-sql", "sqlite-execute-sql")],
    "neo4j": [
        ("cypher", "neo4j-cypher"),
        ("execute-cypher", "neo4j-execute-cypher"),
        ("schema", "neo4j-schema"),
    ],
    "cassandra": [("execute-cql", "cassandra-cql")],
    "scylladb": [("execute-cql", "scylladb-cql")],
    "elasticsearch": [
        ("esql", "elasticsearch-esql"),
        ("execute-esql", "elasticsearch-execute-esql"),
    ],
    "mongodb": [
        ("find", "mongodb-find"),
        ("find-one", "mongodb-find-one"),
        ("aggregate", "mongodb-aggregate"),
        ("insert-one", "mongodb-insert-one"),
        ("insert-many", "mongodb-insert-many"),
        ("delete-one", "mongodb-delete-one"),
        ("delete-many", "mongodb-delete-many"),
        ("update-one", "mongodb-update-one"),
        ("update-many", "mongodb-update-many"),
    ],
    "redis": [("redis", "redis")],
    "valkey": [("valkey", "valkey")],
    "http": [("http", "http")],
}


def _load_prebuilt_tools(src_type: str) -> list[dict[str, Any]] | None:
    """Extract tool definitions from prebuiltconfigs/<src_type>.yaml.

    Returns the list of `kind: tool` docs (with the original tool name and
    full config such as `statement`/`templateParameters`), or None when there
    is no prebuilt yaml for this source type.

    Using the prebuilt yaml as the source of truth guarantees the admin UI
    auto-generates EXACTLY the same tools `--prebuilt <src_type>` would, and
    stays in sync if the yaml changes.
    """
    yaml_name = _PREBUILT_YAML_OVERRIDES.get(src_type, src_type)
    path = os.path.join(_PREBUILT_DIR, f"{yaml_name}.yaml")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to read prebuilt yaml %s: %s", path, exc)
        return None
    tools = [
        doc for doc in docs
        if isinstance(doc, dict) and doc.get("kind") == "tool"
    ]
    return tools or None

SOURCE_TYPE_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "postgres": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 5432},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
        {"name": "maxOpenConns", "label": "最大连接数", "type": "number", "default": 4},
    ],
    "mysql": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 3306},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "mssql": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 1433},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "sqlite": [
        {"name": "path", "label": "数据库路径", "type": "text", "required": True,
         "placeholder": "例如 /data/test.db 或 :memory:"},
    ],
    "clickhouse": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 9000},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "default": "default"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "snowflake": [
        {"name": "account", "label": "账户", "type": "text", "required": True, "placeholder": "xy12345"},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
        {"name": "warehouse", "label": "Warehouse", "type": "text"},
    ],
    "oracle": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 1521},
        {"name": "database", "label": "服务名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "oceanbase": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 2881},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "tdsql": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 3306},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "gaussdb": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 5432},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "trino": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 8080},
        {"name": "database", "label": "Catalog", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "tidb": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 4000},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "cockroachdb": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 26257},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "yugabytedb": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 5433},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "firebird": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 3050},
        {"name": "database", "label": "数据库路径", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "default": "SYSDBA"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "singlestore": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 3306},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "mindsdb": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 47334},
        {"name": "database", "label": "数据库名", "type": "text", "default": "mindsdb"},
        {"name": "user", "label": "用户名", "type": "text", "default": "mindsdb"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "redis": [
        {"name": "address", "label": "地址", "type": "text", "default": "localhost:6379"},
        {"name": "password", "label": "密码", "type": "password"},
        {"name": "db", "label": "DB", "type": "number", "default": 0},
    ],
    "valkey": [
        {"name": "address", "label": "地址", "type": "text", "default": "localhost:6379"},
        {"name": "password", "label": "密码", "type": "password"},
        {"name": "db", "label": "DB", "type": "number", "default": 0},
    ],
    "mongodb": [
        {"name": "uri", "label": "连接 URI", "type": "text", "required": True,
         "placeholder": "mongodb://user:pass@host:27017/db"},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
    ],
    "cassandra": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 9042},
        {"name": "keyspace", "label": "Keyspace", "type": "text", "required": True},
        {"name": "username", "label": "用户名", "type": "text"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "scylladb": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 9042},
        {"name": "keyspace", "label": "Keyspace", "type": "text", "required": True},
        {"name": "username", "label": "用户名", "type": "text"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "neo4j": [
        {"name": "uri", "label": "URI", "type": "text", "required": True, "default": "bolt://localhost:7687"},
        {"name": "user", "label": "用户名", "type": "text", "default": "neo4j"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "elasticsearch": [
        {"name": "addresses", "label": "地址", "type": "text", "required": True,
         "placeholder": "http://localhost:9200"},
        {"name": "username", "label": "用户名", "type": "text"},
        {"name": "password", "label": "密码", "type": "password"},
        {"name": "apiKey", "label": "API Key", "type": "password"},
    ],
    "couchbase": [
        {"name": "connectionString", "label": "连接字符串", "type": "text", "required": True,
         "placeholder": "couchbase://localhost"},
        {"name": "bucket", "label": "Bucket", "type": "text", "required": True},
        {"name": "username", "label": "用户名", "type": "text"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "dgraph": [
        {"name": "address", "label": "地址", "type": "text", "default": "localhost:9080"},
    ],
    "hbase": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 9090},
        {"name": "tablePrefix", "label": "表名前缀", "type": "text",
         "placeholder": "可选,用于多租户隔离"},
        {"name": "protocol", "label": "协议", "type": "text", "default": "binary"},
        {"name": "transport", "label": "传输方式", "type": "text", "default": "buffered"},
    ],
    "http": [
        {"name": "url", "label": "URL", "type": "text", "required": True,
         "placeholder": "https://api.example.com"},
        {"name": "method", "label": "方法", "type": "text", "default": "GET"},
        {"name": "headers", "label": "Headers (JSON)", "type": "text",
         "placeholder": '{"Authorization": "Bearer ..."}'},
    ],
}


def _classify_tool(tool: Any, tool_type: str) -> str:
    """Classify a tool for UI display based on its manifest parameters.

    Categories:
      - "sql":          Manifest's only parameter is 'sql' — user must provide
                        full SQL text. (e.g. postgres-execute-sql, sqlite-execute-sql)
      - "oneclick":     No parameters, or every parameter has a default value —
                        user can just click Execute. (e.g. list-tables, list-views)
      - "parameterized":Has required parameters (no default) — user must fill in
                        form fields. (e.g. get-column-cardinality, get-query-plan)
    """
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    params = manifest.parameters if manifest else []

    if not params:
        return "oneclick"

    # If the only parameter is 'sql', user must write SQL
    if len(params) == 1 and params[0].name == "sql":
        return "sql"

    # Check if any parameter is required (no default value)
    has_required = any(p.default is None for p in params)
    return "parameterized" if has_required else "oneclick"


def _get_rm(request: Request):
    return request.app.state.resource_manager


def _get_config(request: Request):
    return request.app.state.config


async def _build_source(src_type: str, name: str, config_data: dict[str, Any]):
    """Build and initialize a Source from type + config dict."""
    source_config = decode_source_config(src_type, name, config_data)
    return await source_config.initialize()


async def _persist_tool(tool_name: str, tool_type: str, source: str, tool_data: dict[str, Any]) -> None:
    """将工具持久化到 ConfigStore（仅在持久化模式下生效）。"""
    store = get_store()
    if store is None or not store.is_persistent:
        return
    try:
        description = tool_data.get("description", "")
        config_data = {
            k: v for k, v in tool_data.items()
            if k not in ("name", "type", "source", "description")
        }
        await store.save_tool(tool_name, tool_type, source, description, config_data)
    except Exception as exc:
        logger.warning("持久化工具 %r 失败: %s", tool_name, exc)


async def _auto_create_tools(rm, src_type: str, name: str) -> list[str]:
    """Auto-generate default tools for a newly-added source.

    Fulfills the admin UI promise ('添加数据源后会自动生成工具'): when a source
    is added at runtime we register its default tool(s) so they show up in
    GET /admin/tools and are exposed via MCP (added to the default toolset).

    Strategy:
      1. If a prebuilt <src_type>.yaml exists, derive the COMPLETE tool set
         from it (name + full config such as inline SQL). This matches
         `--prebuilt <src_type>` exactly and stays in sync with the yaml.
      2. Otherwise fall back to the hardcoded _SOURCE_DEFAULT_TOOLS specs
         (used for types without a prebuilt yaml, e.g. mongodb/redis/http).

    A failure creating one tool only warns and is skipped, so a single bad
    tool can never block adding the source.
    """
    created: list[str] = []

    # 从数据源配置中提取 systemId / environment,注入到 tool_data 中便于持久化
    src_cfg = rm.get_source_config(name) or {}
    tool_system_id = str(src_cfg.get("systemId", "") or "").strip()
    tool_environment = str(src_cfg.get("environment", "") or "").strip()

    prebuilt = _load_prebuilt_tools(src_type)
    if prebuilt is not None:
        for doc in prebuilt:
            yaml_name = doc.get("name")
            tool_type = doc.get("type")
            if not yaml_name or not tool_type:
                continue
            tool_name = f"{name}-{yaml_name}"
            if tool_name in rm.get_tools_map():
                continue
            # Pass the full yaml tool config (minus kind/name/source which we
            # override) so inline SQL / template params are preserved.
            tool_data = {
                k: v for k, v in doc.items()
                if k not in ("kind", "name", "source")
            }
            tool_data["name"] = tool_name
            tool_data["source"] = name
            if tool_system_id:
                tool_data["systemId"] = tool_system_id
            if tool_environment:
                tool_data["environment"] = tool_environment
            tool_data.setdefault(
                "description",
                f"Auto-generated {tool_type} tool for source '{name}'.",
            )
            try:
                tool_config = decode_tool_config(tool_type, tool_name, tool_data)
                tool = await tool_config.initialize()
                rm.add_tool(tool_name, tool, tool_type)
                await _persist_tool(tool_name, tool_type, name, tool_data)
                created.append(tool_name)
            except Exception as exc:
                logger.warning(
                    "auto-create tool %r (%s) failed: %s", tool_name, tool_type, exc
                )
        return created

    # Fallback: hardcoded minimal spec for source types without a prebuilt yaml.
    for suffix, tool_type in _SOURCE_DEFAULT_TOOLS.get(src_type, []):
        tool_name = f"{name}-{suffix}"
        if tool_name in rm.get_tools_map():
            continue
        tool_data = {
            "name": tool_name,
            "type": tool_type,
            "source": name,
            "description": f"Auto-generated {tool_type} tool for source '{name}'.",
        }
        if tool_system_id:
            tool_data["systemId"] = tool_system_id
        if tool_environment:
            tool_data["environment"] = tool_environment
        try:
            tool_config = decode_tool_config(tool_type, tool_name, tool_data)
            tool = await tool_config.initialize()
            rm.add_tool(tool_name, tool, tool_type)
            created.append(tool_name)
        except Exception as exc:
            logger.warning(
                "auto-create tool %r (%s) failed: %s", tool_name, tool_type, exc
            )
    return created


@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    rm = _get_rm(request)
    config = _get_config(request)
    # 今日请求数 — 优先从数据库 mcp_request_logs 表查询（持久化，重启不丢）
    # 回退到内存计数器（未启用持久化时）
    today_requests = 0
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            from datetime import date
            today_str = date.today().isoformat()
            stats = await store.query_mcp_stats(start_date=today_str, end_date=today_str)
            today_requests = stats.get("summary", {}).get("total", 0)
        except Exception as exc:
            logger.warning("查询今日 MCP 请求数失败: %s", exc)
    if today_requests == 0:
        from data_tool_mcp.server.stats import get_request_counter
        today_requests = get_request_counter().get_today_count()
    # 数据源/工具计数 — 优先从数据库查询（多实例一致性），回退到 rm 内存
    source_count = 0
    tool_count = 0
    if store is not None and store.is_persistent:
        try:
            source_count = await store.count_sources()
            tool_count = await store.count_tools()
        except Exception as exc:
            logger.warning("查询 dashboard 计数失败: %s", exc)
    else:
        source_count = len(rm.get_sources_map())
        tool_count = len(rm.get_tools_map())
    return {
        "version": getattr(config, "version", "0.1.0"),
        "uptime": None,
        "sourceCount": source_count,
        "sourceOnline": source_count,
        "toolCount": tool_count,
        "todayRequests": today_requests,
        "sourceHealth": [],
        "recentErrors": [],
        # MCP 服务实际监听端口 — 前端据此构造 MCP 端点 URL,
        # 避免误用前端/nginx 端口（如 5173/8080）。
        "mcpPort": config.port,
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    rm = _get_rm(request)
    # 数据源名列表 — 优先从数据库查询（多实例一致性），回退到 rm 内存
    source_names: list[str] = []
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            sources_list = await store.load_sources()
            source_names = [s.get("name", "") for s in sources_list if s.get("name")]
        except Exception as exc:
            logger.warning("查询 health 数据源列表失败: %s", exc)
            source_names = list(rm.get_sources_map().keys())
    else:
        source_names = list(rm.get_sources_map().keys())
    source_health = [
        {
            "name": name,
            "status": "unknown",
            "latency": None,
            "lastError": None,
        }
        for name in source_names
    ]
    return {"sources": source_health, "server": "running"}


@router.get("/source-types")
async def source_types(request: Request) -> dict[str, Any]:
    """返回所有已注册的数据源类型及其字段 schema。

    若 ServerConfig.enabled_source_types 非空,仅返回白名单内的类型;
    空 = 全部启用(默认)。前端据此自动隐藏被禁用的类型。
    """
    config = _get_config(request)
    # 严格判断 list 类型,避免 MagicMock 等非 list 对象误判为 truthy
    enabled = getattr(config, "enabled_source_types", []) or []
    if isinstance(enabled, list) and enabled:
        enabled_set = set(enabled)
        return {k: {"fields": v} for k, v in SOURCE_TYPE_SCHEMAS.items() if k in enabled_set}
    return {k: {"fields": v} for k, v in SOURCE_TYPE_SCHEMAS.items()}


@router.get("/environments")
async def list_environments() -> list[str]:
    """返回预设环境列表，供前端下拉选择。"""
    return ENVIRONMENTS


@router.get("/systems")
async def list_systems(request: Request) -> list[dict[str, Any]]:
    """列出所有系统编号及其数据源数量,供 MCP 配置按系统筛选使用。"""
    store = get_store()
    configs: dict[str, dict[str, Any]] = {}
    if store is not None and store.is_persistent:
        try:
            sources_list = await store.load_sources()
            # 转为 {name: cfg} 形式以保持后续逻辑一致
            for s in sources_list:
                sname = s.get("name", "")
                if sname:
                    configs[sname] = s
        except Exception as exc:
            logger.warning("查询系统列表失败: %s", exc)
            rm = _get_rm(request)
            configs = rm.get_all_source_configs()
    else:
        rm = _get_rm(request)
        configs = rm.get_all_source_configs()
    systems: dict[str, dict[str, Any]] = {}
    for name, cfg in configs.items():
        sid = str(cfg.get("systemId", "") or "").strip()
        if not sid:
            continue
        if sid not in systems:
            systems[sid] = {
                "systemId": sid,
                "sourceCount": 0,
                "sources": [],
                "environments": [],
            }
        systems[sid]["sourceCount"] += 1
        systems[sid]["sources"].append(name)
        # 收集该系统下的所有 environment（去重）
        env = str(cfg.get("environment", "") or "").strip()
        if env and env not in systems[sid]["environments"]:
            systems[sid]["environments"].append(env)
    # 按系统编号排序返回
    return sorted(systems.values(), key=lambda x: x["systemId"])


@router.get("/systems/{system_id}/sources")
async def list_sources_by_system(request: Request, system_id: str) -> list[dict[str, Any]]:
    """按系统编号列出该系统下所有数据源。"""
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            sources_list = await store.load_sources_by_system(system_id)
            return [
                await _source_to_dict(s["name"], s, store=store)
                for s in sources_list
                if s.get("name")
            ]
        except Exception as exc:
            logger.warning("查询系统 %r 数据源失败: %s", system_id, exc)
    # 回退到 rm
    rm = _get_rm(request)
    configs = rm.get_all_source_configs()
    result: list[dict[str, Any]] = []
    sources = rm.get_sources_map()
    for name, cfg in configs.items():
        sid = str(cfg.get("systemId", "") or "").strip()
        if sid == system_id and name in sources:
            src_cfg = rm.get_source_config(name) or {}
            item = await _source_to_dict(name, src_cfg)
            # 回退场景下手动计算 tool_count（_source_to_dict 在无 store 时返回 0）
            item["toolCount"] = sum(
                1 for t in rm.get_tools_map().values()
                if getattr(t, "source_name", None) == name
            )
            result.append(item)
    return result


async def _source_to_dict(
    name: str,
    source_config: dict[str, Any] | None = None,
    *,
    password_ciphertext: str = "",
    store=None,
) -> dict[str, Any]:
    """转换单个数据源为响应 dict。

    Args:
        source_config: 数据源配置 dict（含 type/host/port/database/user/password/
            systemId/environment 等）。None 时从 store 查询（需要 store 参数）。
        password_ciphertext: 非空时直接作为 password 字段返回(供编辑场景使用,
            前端原样回传即可保持密码不变); 空字符串时密码字段统一脱敏为
            "********"(列表场景使用)。
        store: ConfigStore 实例，用于查询 tool_count 和 source_config。
    """
    # 如果没有 source_config，从 store 查询
    if source_config is None and store is not None:
        source_config = await store.get_source(name) or {}
    if source_config is None:
        source_config = {}

    tool_count = 0
    if store is not None:
        try:
            tool_count = await store.count_tools_by_source(name)
        except Exception:
            pass

    result: dict[str, Any] = {
        "name": name,
        "type": source_config.get("type", "unknown"),
        "status": "connected",
        "latency": None,
        "error": None,
        "toolCount": tool_count,
    }

    # 附加配置字段
    for k, v in source_config.items():
        if k in ("name", "type"):
            continue
        if k == "password" and v:
            if password_ciphertext:
                # 编辑场景: 优先返回持久化存储中的密文, 前端原样回传即可保持密码不变
                result[k] = password_ciphertext
            else:
                # 列表场景: 统一脱敏为占位符
                result[k] = "********"
        else:
            result[k] = v
    return result


@router.get("/sources")
async def list_sources(request: Request) -> list[dict[str, Any]]:
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            sources_list = await store.load_sources()
            return [
                await _source_to_dict(s["name"], s, store=store)
                for s in sources_list
                if s.get("name")
            ]
        except Exception as exc:
            logger.warning("查询数据源列表失败: %s", exc)
    # 回退到 rm
    rm = _get_rm(request)
    sources = rm.get_sources_map()
    result: list[dict[str, Any]] = []
    for name, source in sources.items():
        src_cfg = rm.get_source_config(name) or {}
        item = await _source_to_dict(name, src_cfg)
        # 回退场景下手动计算 tool_count（_source_to_dict 在无 store 时返回 0）
        item["toolCount"] = sum(
            1 for t in rm.get_tools_map().values()
            if getattr(t, "source_name", None) == name
        )
        result.append(item)
    return result


@router.post("/sources")
async def create_source(request: Request) -> dict[str, Any]:
    body = await request.json()
    name = body.get("name", "")
    src_type = body.get("type", "")
    system_id = str(body.get("systemId", "") or "").strip()
    environment = str(body.get("environment", "") or "").strip()
    if not name or not src_type:
        raise HTTPException(status_code=400, detail="name and type are required")
    if not system_id:
        raise HTTPException(status_code=400, detail="systemId is required")
    if len(system_id) > 10:
        raise HTTPException(status_code=400, detail="systemId 长度不能超过 10 位")
    if not environment:
        raise HTTPException(status_code=400, detail="environment is required")
    if environment not in ENVIRONMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"environment 必须为 {ENVIRONMENTS} 之一",
        )
    # 数据源类型白名单校验: 防止绕过 UI 直接调用 API 创建被禁用类型
    config = _get_config(request)
    enabled = getattr(config, "enabled_source_types", []) or []
    if isinstance(enabled, list) and enabled and src_type not in enabled:
        raise HTTPException(
            status_code=403,
            detail=f"数据源类型 {src_type!r} 未启用,请联系管理员调整 --enabled-source-types",
        )
    rm = _get_rm(request)
    # 数据源主键包含系统编号+环境: 同一系统同一环境下数据源名不可重复,不同系统/环境可同名
    # 优先从 store 查询唯一性（多实例一致性），回退到 rm 内存
    store = get_store()
    if store is not None and store.is_persistent:
        existing = await store.get_source(name, system_id, environment)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"系统 {system_id} 环境 {environment} 下数据源 {name!r} 已存在",
            )
    else:
        for existing_name, existing_config in rm.get_all_source_configs().items():
            if (
                existing_name == name
                and existing_config.get("systemId") == system_id
                and existing_config.get("environment") == environment
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"系统 {system_id} 环境 {environment} 下数据源 {name!r} 已存在",
                )
    # Normalize field names: frontend sends "database" for sqlite, backend expects "path"
    config_data = {k: v for k, v in body.items() if k not in ("name", "type")}
    if src_type == "sqlite" and "database" in config_data and "path" not in config_data:
        config_data["path"] = config_data.pop("database")
    try:
        source = await _build_source(src_type, name, config_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"创建数据源失败: {exc}")
    rm.add_source(name, source, config=config_data)
    created_tools = await _auto_create_tools(rm, src_type, name)
    # 持久化到 ConfigStore（store 已在上方唯一性校验时获取）
    if store is not None and store.is_persistent:
        try:
            await store.save_source(name, src_type, config_data)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            logger.warning("持久化数据源 %r 失败: %s", name, exc)
    # 创建后从 store 读取配置（多实例一致性），回退到 config_data + rm
    if store is not None and store.is_persistent:
        result = await _source_to_dict(name, store=store)
    else:
        # 回退: 手动构造 source_config（config_data 缺少 name/type，补上）
        src_cfg = dict(config_data)
        src_cfg["name"] = name
        src_cfg["type"] = src_type
        result = await _source_to_dict(name, src_cfg)
        result["toolCount"] = sum(
            1 for t in rm.get_tools_map().values()
            if getattr(t, "source_name", None) == name
        )
    result["createdTools"] = created_tools
    return result


@router.get("/sources/{name}")
async def get_source(request: Request, name: str) -> dict[str, Any]:
    rm = _get_rm(request)
    store = get_store()
    # 存在性检查 + 配置读取: 优先用 store, 回退到 rm
    src_cfg: dict[str, Any] | None = None
    if store is not None and store.is_persistent:
        try:
            src_cfg = await store.get_source(name)
        except Exception as exc:
            logger.warning("查询数据源 %r 失败: %s", name, exc)
            src_cfg = None
    if src_cfg is None:
        # 回退到 rm
        if name not in rm.get_sources_map():
            raise HTTPException(status_code=404, detail=f"source {name!r} not found")
        src_cfg = rm.get_source_config(name) or {}
    # 编辑场景: 优先从持久化存储读取密文, 前端原样回传即可保持密码不变;
    # 回退到 ResourceManager 内存配置中的明文密码(未启用持久化时),
    # 前端原样回传时 _normalize_password_for_storage 会加密后落库。
    password_ciphertext = ""
    if store is not None and store.is_persistent:
        try:
            sid = str(src_cfg.get("systemId", "") or "").strip()
            env = str(src_cfg.get("environment", "") or "").strip()
            password_ciphertext = await store.get_source_password(name, sid, env)
        except Exception as exc:
            logger.warning("读取数据源 %r 密文失败: %s", name, exc)
    if not password_ciphertext:
        # 未启用持久化或读取失败: 回退到内存中的明文密码
        password_ciphertext = str(src_cfg.get("password", "") or "")
    return await _source_to_dict(
        name, src_cfg, password_ciphertext=password_ciphertext, store=store
    )


@router.put("/sources/{name}")
async def update_source(request: Request, name: str) -> dict[str, Any]:
    body = await request.json()
    rm = _get_rm(request)
    store = get_store()
    # 存在性检查: 优先用 store, 回退到 rm
    exists = False
    if store is not None and store.is_persistent:
        try:
            existing = await store.get_source(name)
            exists = existing is not None
        except Exception as exc:
            logger.warning("查询数据源 %r 失败: %s", name, exc)
            exists = name in rm.get_sources_map()
    else:
        exists = name in rm.get_sources_map()
    if not exists:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    # Close old source before replacing
    old = rm.get_source(name)
    if old is not None and hasattr(old, "close"):
        try:
            await old.close()
        except Exception:
            pass
    src_type = body.get("type", getattr(old, "source_type", "unknown"))
    config_data = {k: v for k, v in body.items() if k not in ("name", "type")}
    if src_type == "sqlite" and "database" in config_data and "path" not in config_data:
        config_data["path"] = config_data.pop("database")
    # Remove old tools bound to this source before recreating
    # 优先从 store 查询（多实例一致性），回退到 rm 内存
    if store is not None and store.is_persistent:
        try:
            old_tools_list = await store.load_tools_by_source(name)
            old_tools = [t["name"] for t in old_tools_list if t.get("name")]
        except Exception as exc:
            logger.warning("查询数据源 %r 的旧工具失败: %s", name, exc)
            old_tools = [
                tname for tname, t in rm.get_tools_map().items()
                if getattr(t, "source_name", None) == name
            ]
    else:
        old_tools = [
            tname for tname, t in rm.get_tools_map().items()
            if getattr(t, "source_name", None) == name
        ]
    for tname in old_tools:
        rm.remove_tool(tname)
    default_ts = rm.get_toolset("")
    if default_ts is not None:
        default_ts.tool_names = [n for n in default_ts.tool_names if n not in old_tools]
    # 同步清除 store 中该数据源的旧工具（随后 _auto_create_tools 会重新持久化）。
    # 旧工具仍属于更新前的 system_id + environment，需从旧 source config 中提取。
    if store is not None and store.is_persistent:
        try:
            old_cfg = rm.get_source_config(name) or {}
            old_sid = str(old_cfg.get("systemId", "") or "").strip()
            old_env = str(old_cfg.get("environment", "") or "").strip()
            await store.delete_tools_by_source(name, old_sid, old_env)
        except Exception as exc:
            logger.warning("清除数据源 %r 的旧工具失败: %s", name, exc)
    try:
        source = await _build_source(src_type, name, config_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"更新数据源失败: {exc}")
    rm.add_source(name, source, config=config_data)
    await _auto_create_tools(rm, src_type, name)
    # 持久化更新数据源到 ConfigStore（工具已在 _auto_create_tools 中持久化）
    if store is not None and store.is_persistent:
        try:
            await store.save_source(name, src_type, config_data)
        except Exception as exc:
            logger.warning("持久化更新数据源 %r 失败: %s", name, exc)
    # 更新后从 store 读取配置（多实例一致性），回退到 config_data + rm
    if store is not None and store.is_persistent:
        return await _source_to_dict(name, store=store)
    # 回退: 手动构造 source_config（config_data 缺少 name/type，补上）
    src_cfg = dict(config_data)
    src_cfg["name"] = name
    src_cfg["type"] = src_type
    result = await _source_to_dict(name, src_cfg)
    result["toolCount"] = sum(
        1 for t in rm.get_tools_map().values()
        if getattr(t, "source_name", None) == name
    )
    return result


@router.delete("/sources/{name}", status_code=204)
async def delete_source(request: Request, name: str):
    rm = _get_rm(request)
    store = get_store()
    # 存在性检查: 优先用 store, 回退到 rm
    exists = False
    if store is not None and store.is_persistent:
        try:
            existing = await store.get_source(name)
            exists = existing is not None
        except Exception as exc:
            logger.warning("查询数据源 %r 失败: %s", name, exc)
            exists = name in rm.get_sources_map()
    else:
        exists = name in rm.get_sources_map()
    if exists:
        source = rm.get_source(name)
        if hasattr(source, "close"):
            try:
                await source.close()
            except Exception:
                pass
        # 持久化删除前先取出 system_id + environment，用于精确删除 store 中记录
        old_cfg = rm.get_source_config(name) or {}
        sid = str(old_cfg.get("systemId", "") or "").strip()
        env = str(old_cfg.get("environment", "") or "").strip()
        rm.remove_source(name)
        # Remove tools bound to this source (auto-generated or manual) and
        # drop them from the default toolset so no orphan tools remain.
        # 优先从 store 查询（多实例一致性），回退到 rm 内存
        if store is not None and store.is_persistent:
            try:
                removed_list = await store.load_tools_by_source(name)
                removed = [t["name"] for t in removed_list if t.get("name")]
            except Exception as exc:
                logger.warning("查询数据源 %r 的工具失败: %s", name, exc)
                removed = [
                    tname for tname, t in rm.get_tools_map().items()
                    if getattr(t, "source_name", None) == name
                ]
        else:
            removed = [
                tname for tname, t in rm.get_tools_map().items()
                if getattr(t, "source_name", None) == name
            ]
        for tname in removed:
            rm.remove_tool(tname)
        default_ts = rm.get_toolset("")
        if default_ts is not None:
            default_ts.tool_names = [n for n in default_ts.tool_names if n not in removed]
        # 持久化删除到 ConfigStore
        if store is not None and store.is_persistent:
            try:
                await store.delete_source(name, sid, env)
                await store.delete_tools_by_source(name, sid, env)
            except Exception as exc:
                logger.warning("持久化删除数据源 %r 失败: %s", name, exc)



@router.post("/sources/{name}/test")
async def test_source(request: Request, name: str) -> dict[str, Any]:
    rm = _get_rm(request)
    if name not in rm.get_sources_map():
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    source = rm.get_source(name)
    try:
        import time
        start = time.monotonic()
        if hasattr(source, "connect"):
            await source.connect()
        latency = int((time.monotonic() - start) * 1000)
        return {"ok": True, "latency": latency, "error": None}
    except Exception as exc:
        return {"ok": False, "latency": 0, "error": str(exc)}


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    rm = _get_rm(request)
    tools = rm.get_tools_map()
    result = []
    for name, tool in tools.items():
        manifest = tool.manifest() if hasattr(tool, "manifest") else None
        tool_type = rm.get_tool_type(name)
        source_name = getattr(tool, "source_name", None)
        # 从数据源配置中提取 systemId / environment,用于前端按系统+环境筛选
        system_id = ""
        environment = ""
        if source_name:
            src_cfg = rm.get_source_config(source_name) or {}
            system_id = str(src_cfg.get("systemId", "") or "").strip()
            environment = str(src_cfg.get("environment", "") or "").strip()
        result.append({
            "name": name,
            "type": tool_type,
            "source": source_name,
            "description": manifest.description if manifest else None,
            "category": _classify_tool(tool, tool_type),
            "systemId": system_id,
            "environment": environment,
        })
    return result


@router.get("/tools/{name}")
async def get_tool(request: Request, name: str) -> dict[str, Any]:
    rm = _get_rm(request)
    tool = rm.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool {name!r} not found")
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    
    # Convert ParameterManifest list to JSON Schema format for frontend
    input_schema = None
    if manifest and manifest.parameters:
        properties = {}
        required = []
        for param in manifest.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.default is not None:
                properties[param.name]["default"] = param.default
            if param.allowed_values:
                properties[param.name]["enum"] = param.allowed_values
            if param.required:
                required.append(param.name)
        
        input_schema = {
            "properties": properties,
            "required": required,
        }
    
    return {
        "name": name,
        "type": rm.get_tool_type(name),
        "source": getattr(tool, "source_name", None),
        "description": manifest.description if manifest else None,
        "inputSchema": input_schema,
        "category": _classify_tool(tool, rm.get_tool_type(name)),
    }


@router.post("/tools/{name}/invoke")
async def invoke_tool(request: Request, name: str) -> dict[str, Any]:
    rm = _get_rm(request)
    tool = rm.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool {name!r} not found")
    body = await request.json()
    params = body.get("params", {})
    try:
        result = await tool.invoke(params, source_provider=rm)
        return {"result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/tools/{name}", status_code=204)
async def delete_tool(request: Request, name: str):
    rm = _get_rm(request)
    rm.remove_tool(name)
    # 持久化删除到 ConfigStore
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            await store.delete_tool(name)
        except Exception as exc:
            logger.warning("持久化删除工具 %r 失败: %s", name, exc)


@router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    config = _get_config(request)
    prebuilt = config.prebuilt.split(",") if config.prebuilt else []
    parsed = {
        "address": config.address,
        "port": config.port,
        "log_level": config.log_level,
        "sources": len(config.source_configs),
        "tools": len(config.tool_configs),
        "toolsets": len(config.toolset_configs),
    }
    yaml_lines = [
        "# Server Config",
        f"address: {config.address}",
        f"port: {config.port}",
        f"log_level: {config.log_level}",
        f"sources: {len(config.source_configs)} configured",
        f"tools: {len(config.tool_configs)} configured",
        f"toolsets: {len(config.toolset_configs)} configured",
    ]
    return {
        "yaml": "\n".join(yaml_lines),
        "parsed": parsed,
        "prebuiltNames": prebuilt,
    }


@router.post("/config/reload")
async def reload_config(request: Request) -> dict[str, Any]:
    return {"ok": True, "errors": None}


@router.post("/query")
async def execute_query(request: Request) -> dict[str, Any]:
    body = await request.json()
    source_name = body.get("sourceName", "")
    statement = body.get("statement", "")
    if not source_name or not statement:
        raise HTTPException(status_code=400, detail="sourceName and statement are required")
    rm = _get_rm(request)
    source = rm.get_source(source_name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {source_name!r} not found")
    if not hasattr(source, "execute_sql"):
        raise HTTPException(status_code=400, detail=f"source {source_name!r} does not support SQL queries")
    import time
    start = time.monotonic()
    try:
        rows = await source.execute_sql(statement)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    duration_ms = int((time.monotonic() - start) * 1000)
    columns = list(rows[0].keys()) if rows else []
    return {
        "columns": columns,
        "rows": [list(r.values()) for r in rows],
        "rowCount": len(rows),
        "durationMs": duration_ms,
    }


@router.get("/sources/{name}/tables")
async def list_source_tables(request: Request, name: str) -> dict[str, Any]:
    """List tables in a SQL data source, for the query console sidebar."""
    rm = _get_rm(request)
    source = rm.get_source(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    if not hasattr(source, "execute_sql"):
        raise HTTPException(status_code=400, detail=f"source {name!r} does not support SQL queries")
    # Detect dialect for the right metadata query
    src_type = getattr(source, "source_type", "")
    if src_type == "sqlite":
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    elif src_type in ("postgres", "postgresql"):
        sql = "SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public' ORDER BY name"
    elif src_type == "mysql":
        sql = "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY name"
    elif src_type == "mssql":
        sql = "SELECT name FROM sys.tables ORDER BY name"
    else:
        sql = "SELECT table_name AS name FROM information_schema.tables ORDER BY name"
    try:
        rows = await source.execute_sql(sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    tables = [r.get("name") or r.get("tablename") or list(r.values())[0] for r in rows]
    return {"tables": [t for t in tables if t]}


@router.post("/mcp-test")
async def mcp_test(request: Request) -> dict[str, Any]:
    """模拟 MCP 客户端调用 tools/list，验证端点配置是否可用。

    内部构造 MCPProtocol 并调用 handle_tools_list，与真实 MCP 客户端
    调用 /sse 或 / 端点的 tools/list 方法走完全相同的代码路径。

    过滤逻辑与 MCP 路由一致：
      - 选了数据源(toolset) → 按数据源 toolset 过滤
      - 仅选系统编号+环境(systemId/environment) → 按系统-环境 toolset 过滤
      - 都未选 → 返回全部工具
    """
    body = await request.json()
    toolset_name = body.get("toolset", "") or ""
    system_id = str(body.get("systemId", "") or "").strip()
    environment = str(body.get("environment", "") or "").strip()
    rm = _get_rm(request)

    # 确定最终用于过滤的 toolset 名称:
    #   选了数据源 → 用数据源名(数据源本身就是一个 toolset)
    #   仅选系统编号+环境 → 优先用 {system_id}-{environment} 格式
    if toolset_name:
        effective_toolset = toolset_name
    elif system_id and environment:
        effective_toolset = f"{system_id}-{environment}"
    else:
        effective_toolset = system_id

    # 如果指定了 toolset，先校验其是否存在
    if effective_toolset:
        toolset = rm.get_toolset(effective_toolset)
        if toolset is None:
            raise HTTPException(status_code=404, detail=f"toolset {effective_toolset!r} not found")

    from data_tool_mcp.server.mcp.protocol import MCPProtocol
    protocol = MCPProtocol(rm, toolset_name=effective_toolset)
    result = await protocol.handle_tools_list({})
    tools = result.get("tools", [])
    return {
        "ok": True,
        "count": len(tools),
        "tools": [{"name": t["name"], "description": t.get("description", "")} for t in tools],
    }


@router.get("/toolsets")
async def list_toolsets(request: Request) -> list[dict[str, Any]]:
    """列出所有 toolset（工具集），供 MCP 配置的 toolset 选择下拉框使用。

    返回每个 toolset 的名称和工具数量。空名 toolset（默认包含所有工具）
    显示为 "全部工具"。标注 toolset 类型(source/system/custom)以便前端分组。
    """
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            toolsets_list = await store.load_toolsets()
            sources_list = await store.load_sources()
        except Exception as exc:
            logger.warning("查询 toolset 列表失败: %s", exc)
            toolsets_list = []
            sources_list = []
        source_names = {s["name"] for s in sources_list if s.get("name")}
        system_ids = {
            str(s.get("systemId", "") or "").strip()
            for s in sources_list
            if str(s.get("systemId", "") or "").strip()
        }
        result: list[dict[str, Any]] = []
        for item in toolsets_list:
            name = item.get("name", "")
            tools = item.get("tools", []) or []
            # 判断 toolset 类型
            if not name:
                ts_type = "all"
            elif name in system_ids:
                ts_type = "system"
            elif name in source_names:
                ts_type = "source"
            else:
                ts_type = "custom"
            result.append({
                "name": name,
                "displayName": "全部工具" if not name else name,
                "toolCount": len(tools),
                "type": ts_type,
            })
        # 排序: 全部 → system → source → custom, 每组内按名称排序
        type_order = {"all": 0, "system": 1, "source": 2, "custom": 3}
        result.sort(key=lambda x: (type_order.get(x["type"], 9), x["name"]))
        return result
    # 回退到 rm
    rm = _get_rm(request)
    toolsets = rm.get_toolsets_map()
    source_names = set(rm.get_sources_map().keys())
    configs = rm.get_all_source_configs()
    system_ids = {
        str(cfg.get("systemId", "") or "").strip()
        for cfg in configs.values()
        if str(cfg.get("systemId", "") or "").strip()
    }
    result: list[dict[str, Any]] = []
    for name, toolset in toolsets.items():
        # 判断 toolset 类型
        if not name:
            ts_type = "all"
        elif name in system_ids:
            ts_type = "system"
        elif name in source_names:
            ts_type = "source"
        else:
            ts_type = "custom"
        result.append({
            "name": name,
            "displayName": "全部工具" if not name else name,
            "toolCount": len(toolset.tool_names),
            "type": ts_type,
        })
    # 排序: 全部 → system → source → custom, 每组内按名称排序
    type_order = {"all": 0, "system": 1, "source": 2, "custom": 3}
    result.sort(key=lambda x: (type_order.get(x["type"], 9), x["name"]))
    return result


@router.get("/mcp-stats")
async def mcp_stats(
    request: Request,
    start_date: str | None = None,
    end_date: str | None = None,
    system_id: str = "",
    source_name: str = "",
) -> dict[str, Any]:
    """MCP 请求统计接口 — 支持按系统、数据源、日期范围聚合查询。

    参数:
        start_date: YYYY-MM-DD（含），默认今天往前 30 天
        end_date:   YYYY-MM-DD（含），默认今天
        system_id:  筛选系统编号，空串表示不限
        source_name: 筛选数据源名称，空串表示不限

    返回:
        summary / by_system / by_source / by_tool / timeline
    """
    from datetime import date, timedelta

    store = get_store()
    if store is None or not store.is_persistent:
        return {
            "summary": {"total": 0, "success": 0, "fail": 0, "avg_latency_ms": 0},
            "by_system": [],
            "by_source": [],
            "by_tool": [],
            "timeline": [],
            "note": "未启用持久化存储，无法统计 MCP 请求",
        }

    today = date.today()
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")

    result = await store.query_mcp_stats(
        start_date=start_date,
        end_date=end_date,
        system_id=system_id.strip(),
        source_name=source_name.strip(),
    )
    result["start_date"] = start_date
    result["end_date"] = end_date
    return result


@router.get("/mcp-logs")
async def mcp_logs(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    system_id: str = "",
    source_name: str = "",
) -> dict[str, Any]:
    """MCP 请求记录分页查询 — 最新记录排在最前面。

    参数:
        page: 页码（从 1 开始）
        page_size: 每页条数（最大 100）
        start_date / end_date / system_id / source_name: 筛选条件（与 mcp-stats 共享）
    """
    from datetime import date, timedelta

    store = get_store()
    if store is None or not store.is_persistent:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 1,
            "note": "未启用持久化存储，无法查询 MCP 请求记录",
        }

    today = date.today()
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")

    result = await store.query_mcp_logs(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        system_id=system_id.strip(),
        source_name=source_name.strip(),
    )
    result["start_date"] = start_date
    result["end_date"] = end_date
    return result



