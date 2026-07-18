from __future__ import annotations

import logging
import os

import yaml
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from data_tool_mcp.config.store import get_store
from data_tool_mcp.sources import decode_source_config
from data_tool_mcp.tools import decode_tool_config

router = APIRouter(prefix="/mcp-api", tags=["Admin"])

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


# ---------------------------------------------------------------------------
# 预设工具加载相关辅助函数
# ---------------------------------------------------------------------------


def _read_yaml_docs(path: str) -> list | None:
    """读取 yaml 文件并返回所有文档列表,失败返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return list(yaml.safe_load_all(f))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to read prebuilt yaml %s: %s", path, exc)
        return None


def _is_tool_doc(doc: Any) -> bool:
    """判断 yaml 文档是否为 tool 类型。"""
    return isinstance(doc, dict) and doc.get("kind") == "tool"


def _collect_tool_docs(docs: list) -> list[dict[str, Any]]:
    """从 yaml 文档列表中筛选 kind==tool 的文档。"""
    return [doc for doc in docs if _is_tool_doc(doc)]


def _filter_tool_docs(docs: list) -> list[dict[str, Any]] | None:
    """从 yaml 文档列表中筛选 kind==tool 的文档,空则返回 None。"""
    tools = _collect_tool_docs(docs)
    return tools or None


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
    docs = _read_yaml_docs(path)
    if docs is None:
        return None
    return _filter_tool_docs(docs)


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
        {
            "name": "path",
            "label": "数据库路径",
            "type": "text",
            "required": True,
            "placeholder": "例如 /data/test.db 或 :memory:",
        },
    ],
    "clickhouse": [
        {"name": "host", "label": "主机", "type": "text", "default": "localhost"},
        {"name": "port", "label": "端口", "type": "number", "default": 9000},
        {"name": "database", "label": "数据库名", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "default": "default"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "snowflake": [
        {
            "name": "account",
            "label": "账户",
            "type": "text",
            "required": True,
            "placeholder": "xy12345",
        },
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
        {
            "name": "uri",
            "label": "连接 URI",
            "type": "text",
            "required": True,
            "placeholder": "mongodb://user:pass@host:27017/db",
        },
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
        {
            "name": "uri",
            "label": "URI",
            "type": "text",
            "required": True,
            "default": "bolt://localhost:7687",
        },
        {"name": "user", "label": "用户名", "type": "text", "default": "neo4j"},
        {"name": "password", "label": "密码", "type": "password"},
    ],
    "elasticsearch": [
        {
            "name": "addresses",
            "label": "地址",
            "type": "text",
            "required": True,
            "placeholder": "http://localhost:9200",
        },
        {"name": "username", "label": "用户名", "type": "text"},
        {"name": "password", "label": "密码", "type": "password"},
        {"name": "apiKey", "label": "API Key", "type": "password"},
    ],
    "couchbase": [
        {
            "name": "connectionString",
            "label": "连接字符串",
            "type": "text",
            "required": True,
            "placeholder": "couchbase://localhost",
        },
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
        {
            "name": "tablePrefix",
            "label": "表名前缀",
            "type": "text",
            "placeholder": "可选,用于多租户隔离",
        },
        {"name": "protocol", "label": "协议", "type": "text", "default": "binary"},
        {"name": "transport", "label": "传输方式", "type": "text", "default": "buffered"},
    ],
    "http": [
        {
            "name": "url",
            "label": "URL",
            "type": "text",
            "required": True,
            "placeholder": "https://api.example.com",
        },
        {"name": "method", "label": "方法", "type": "text", "default": "GET"},
        {
            "name": "headers",
            "label": "Headers (JSON)",
            "type": "text",
            "placeholder": '{"Authorization": "Bearer ..."}',
        },
    ],
}


# ---------------------------------------------------------------------------
# 工具分类辅助函数
# ---------------------------------------------------------------------------


def _get_tool_params(tool: Any) -> list:
    """获取工具的参数清单,无 manifest 时返回空列表。"""
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    return manifest.parameters if manifest else []


def _is_sql_only_param(params: list) -> bool:
    """判断参数列表是否仅含一个名为 sql 的参数。"""
    return len(params) == 1 and params[0].name == "sql"


def _classify_by_required(params: list) -> str:
    """根据是否有必填参数返回 parameterized / oneclick。"""
    return "parameterized" if any(p.default is None for p in params) else "oneclick"


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
    params = _get_tool_params(tool)
    if not params:
        return "oneclick"
    if _is_sql_only_param(params):
        return "sql"
    return _classify_by_required(params)


def _get_rm(request: Request):
    """从 request.app.state 获取 ResourceManager。"""
    return request.app.state.resource_manager


def _get_config(request: Request):
    """从 request.app.state 获取 ServerConfig。"""
    return request.app.state.config


async def _build_source(src_type: str, name: str, config_data: dict[str, Any]):
    """Build and initialize a Source from type + config dict."""
    source_config = decode_source_config(src_type, name, config_data)
    return await source_config.initialize()


# ---------------------------------------------------------------------------
# 持久化 / 自动建工具相关辅助函数
# ---------------------------------------------------------------------------


def _build_persist_config(tool_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """从 tool_data 中拆出 description 与剩余 config_data,供持久化使用。"""
    description = tool_data.get("description", "")
    config_data = {
        k: v for k, v in tool_data.items() if k not in ("name", "type", "source", "description")
    }
    return description, config_data


async def _persist_tool(
    tool_name: str, tool_type: str, source: str, tool_data: dict[str, Any]
) -> None:
    """将工具持久化到 ConfigStore（仅在持久化模式下生效）。"""
    store = get_store()
    if not _is_store_usable(store):
        return
    try:
        description, config_data = _build_persist_config(tool_data)
        await store.save_tool(tool_name, tool_type, source, description, config_data)
    except Exception as exc:
        logger.warning("持久化工具 %r 失败: %s", tool_name, exc)


def _extract_env_keys(src_cfg: dict[str, Any]) -> tuple[str, str]:
    """从数据源配置中提取 (systemId, environment),均去除空白。"""
    system_id = str(src_cfg.get("systemId", "") or "").strip()
    environment = str(src_cfg.get("environment", "") or "").strip()
    return system_id, environment


def _inject_env_keys(tool_data: dict[str, Any], system_id: str, environment: str) -> None:
    """将非空的 systemId / environment 注入到 tool_data。"""
    extras = {"systemId": system_id, "environment": environment}
    tool_data.update({k: v for k, v in extras.items() if v})


def _tool_already_exists(tool_name: str | None, rm) -> bool:
    """tool_name 为 None 或已存在时返回 True。"""
    return tool_name is None or tool_name in rm.get_tools_map()


def _build_tool_data(
    doc: dict[str, Any],
    name: str,
    tool_name: str,
    tool_type: str,
    system_id: str,
    environment: str,
) -> dict[str, Any]:
    """基于 prebuilt yaml doc 构造完整 tool_data。"""
    tool_data = {k: v for k, v in doc.items() if k not in ("kind", "name", "source")}
    tool_data["name"] = tool_name
    tool_data["source"] = name
    _inject_env_keys(tool_data, system_id, environment)
    tool_data.setdefault(
        "description",
        f"Auto-generated {tool_type} tool for source '{name}'.",
    )
    return tool_data


def _build_prebuilt_tool_doc(
    doc: dict[str, Any],
    name: str,
    system_id: str,
    environment: str,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """从 prebuilt doc 构造 (tool_name, tool_type, tool_data);缺失字段返回 (None, None, None)。"""
    yaml_name = doc.get("name")
    tool_type = doc.get("type")
    if not yaml_name or not tool_type:
        return None, None, None
    tool_name = f"{name}-{yaml_name}"
    tool_data = _build_tool_data(doc, name, tool_name, tool_type, system_id, environment)
    return tool_name, tool_type, tool_data


async def _try_add_tool(
    rm,
    tool_name: str,
    tool_type: str,
    tool_data: dict[str, Any],
    source_name: str,
    persist: bool,
) -> bool:
    """尝试初始化并注册一个工具,成功返回 True,失败仅告警。"""
    try:
        tool_config = decode_tool_config(tool_type, tool_name, tool_data)
        tool = await tool_config.initialize()
        rm.add_tool(tool_name, tool, tool_type)
        if persist:
            await _persist_tool(tool_name, tool_type, source_name, tool_data)
        return True
    except Exception as exc:
        logger.warning("auto-create tool %r (%s) failed: %s", tool_name, tool_type, exc)
        return False


async def _try_create_prebuilt_tool(
    rm,
    doc: dict[str, Any],
    name: str,
    system_id: str,
    environment: str,
) -> str | None:
    """尝试基于单个 prebuilt doc 创建工具,返回创建的工具名(或 None)。"""
    tool_name, tool_type, tool_data = _build_prebuilt_tool_doc(doc, name, system_id, environment)
    if _tool_already_exists(tool_name, rm):
        return None
    if await _try_add_tool(rm, tool_name, tool_type, tool_data, name, persist=True):
        return tool_name
    return None


async def _create_prebuilt_tools(
    rm,
    prebuilt: list[dict[str, Any]],
    name: str,
    system_id: str,
    environment: str,
) -> list[str]:
    """基于 prebuilt yaml 文档列表创建工具。"""
    created: list[str] = []
    for doc in prebuilt:
        tool_name = await _try_create_prebuilt_tool(rm, doc, name, system_id, environment)
        if tool_name:
            created.append(tool_name)
    return created


def _build_default_tool_data(
    name: str,
    suffix: str,
    tool_type: str,
    system_id: str,
    environment: str,
) -> dict[str, Any]:
    """构造 fallback 工具的最小 tool_data。"""
    tool_name = f"{name}-{suffix}"
    tool_data: dict[str, Any] = {
        "name": tool_name,
        "type": tool_type,
        "source": name,
        "description": f"Auto-generated {tool_type} tool for source '{name}'.",
    }
    _inject_env_keys(tool_data, system_id, environment)
    return tool_data


async def _try_create_default_tool(
    rm,
    name: str,
    suffix: str,
    tool_type: str,
    system_id: str,
    environment: str,
) -> str | None:
    """尝试创建单个 fallback 工具,返回工具名(或 None)。"""
    tool_name = f"{name}-{suffix}"
    if _tool_already_exists(tool_name, rm):
        return None
    tool_data = _build_default_tool_data(name, suffix, tool_type, system_id, environment)
    if await _try_add_tool(rm, tool_name, tool_type, tool_data, name, persist=False):
        return tool_name
    return None


async def _create_default_tools(
    rm,
    src_type: str,
    name: str,
    system_id: str,
    environment: str,
) -> list[str]:
    """Fallback: 为无 prebuilt yaml 的数据源类型创建最小工具集。"""
    created: list[str] = []
    for suffix, tool_type in _SOURCE_DEFAULT_TOOLS.get(src_type, []):
        tool_name = await _try_create_default_tool(
            rm, name, suffix, tool_type, system_id, environment
        )
        if tool_name:
            created.append(tool_name)
    return created


async def _auto_create_tools(rm, src_type: str, name: str) -> list[str]:
    """Auto-generate default tools for a newly-added source.

    Fulfills the admin UI promise ('添加数据源后会自动生成工具'): when a source
    is added at runtime we register its default tool(s) so they show up in
    GET /mcp-api/tools and are exposed via MCP (added to the default toolset).

    Strategy:
      1. If a prebuilt <src_type>.yaml exists, derive the COMPLETE tool set
         from it (name + full config such as inline SQL). This matches
         `--prebuilt <src_type>` exactly and stays in sync with the yaml.
      2. Otherwise fall back to the hardcoded _SOURCE_DEFAULT_TOOLS specs
         (used for types without a prebuilt yaml, e.g. mongodb/redis/http).

    A failure creating one tool only warns and is skipped, so a single bad
    tool can never block adding the source.
    """
    src_cfg = rm.get_source_config(name) or {}
    system_id, environment = _extract_env_keys(src_cfg)
    prebuilt = _load_prebuilt_tools(src_type)
    if prebuilt is not None:
        return await _create_prebuilt_tools(rm, prebuilt, name, system_id, environment)
    return await _create_default_tools(rm, src_type, name, system_id, environment)


# ---------------------------------------------------------------------------
# 数据源配置加载 / 存在性检查 / 工具计数相关辅助函数
# ---------------------------------------------------------------------------


def _is_store_usable(store) -> bool:
    """store 非 None 且为持久化存储时返回 True。"""
    return store is not None and store.is_persistent


async def _load_all_source_configs(rm, store) -> dict[str, dict[str, Any]]:
    """加载所有数据源配置,优先用 store,失败或非持久化时回退到 rm。"""
    if not _is_store_usable(store):
        return rm.get_all_source_configs()
    try:
        sources_list = await store.load_sources()
        return _convert_sources_list_to_configs(sources_list)
    except Exception as exc:
        logger.warning("查询数据源列表失败: %s", exc)
        return rm.get_all_source_configs()


def _convert_sources_list_to_configs(
    sources_list: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """将 store 返回的 list 形式转为 {name: cfg} dict。"""
    configs: dict[str, dict[str, Any]] = {}
    for s in sources_list:
        sname = s.get("name", "")
        if sname:
            configs[sname] = s
    return configs


async def _check_source_exists(rm, store, name: str) -> bool:
    """数据源存在性检查,优先用 store,回退到 rm。"""
    if not _is_store_usable(store):
        return rm.has_source(name)
    try:
        existing = await store.get_source(name)
        return existing is not None
    except Exception as exc:
        logger.warning("查询数据源 %r 失败: %s", name, exc)
        return rm.has_source(name)


def _get_source_env_keys_from_cfg(src_cfg: dict[str, Any]) -> tuple[str, str]:
    """从 source 配置中提取 (systemId, environment)。"""
    system_id = str(src_cfg.get("systemId", "") or "").strip()
    environment = str(src_cfg.get("environment", "") or "").strip()
    return system_id, environment


def _get_tools_for_source_from_rm(rm, name: str) -> list[str]:
    """从 rm 内存中查询绑定到指定数据源的工具名列表。"""
    return [
        tname for tname, t in rm.get_tools_map().items() if getattr(t, "source_name", None) == name
    ]


def _extract_tool_names_from_list(tools_list: list[dict[str, Any]]) -> list[str]:
    """从工具列表中提取非空工具名。"""
    return [t["name"] for t in tools_list if t.get("name")]


async def _get_tools_for_source(rm, store, name: str) -> list[str]:
    """获取数据源绑定的工具名列表,优先用 store,回退到 rm。"""
    if not _is_store_usable(store):
        return _get_tools_for_source_from_rm(rm, name)
    try:
        tools_list = await store.load_tools_by_source(name)
        return _extract_tool_names_from_list(tools_list)
    except Exception as exc:
        logger.warning("查询数据源 %r 的工具失败: %s", name, exc)
        return _get_tools_for_source_from_rm(rm, name)


def _compute_tool_count_from_rm(rm, name: str) -> int:
    """从 rm 内存计算绑定到指定数据源的工具数量。"""
    return sum(1 for t in rm.get_tools_map().values() if getattr(t, "source_name", None) == name)


def _needs_sqlite_normalize(src_type: str, config_data: dict[str, Any]) -> bool:
    """判断是否需要将 database 字段重命名为 path。"""
    return src_type == "sqlite" and "database" in config_data and "path" not in config_data


def _normalize_sqlite_config(src_type: str, config_data: dict[str, Any]) -> None:
    """sqlite 数据源: 将 frontend 传入的 database 字段重命名为 path。"""
    if not _needs_sqlite_normalize(src_type, config_data):
        return
    config_data["path"] = config_data.pop("database")


async def _build_source_or_raise(
    src_type: str,
    name: str,
    config_data: dict[str, Any],
    error_prefix: str,
):
    """构造并初始化 Source,失败时抛出对应的 HTTPException。"""
    try:
        return await _build_source(src_type, name, config_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{error_prefix}: {exc}")


async def _persist_source(store, name: str, src_type: str, config_data: dict[str, Any]) -> bool:
    """持久化数据源到 ConfigStore(仅在持久化模式下生效)。返回是否成功。"""
    if not _is_store_usable(store):
        return True  # 无 store 视为成功(单机模式)
    try:
        await store.save_source(name, src_type, config_data)
        return True
    except Exception as exc:
        logger.warning("持久化数据源 %r 失败: %s", name, exc)
        return False


async def _build_source_response(
    rm,
    store,
    name: str,
    src_type: str,
    config_data: dict[str, Any],
) -> dict[str, Any]:
    """构造数据源响应 dict,持久化模式从 store 读取,回退到 config_data + rm。"""
    if _is_store_usable(store):
        return await _source_to_dict(name, store=store)
    # 回退: 手动构造 source_config（config_data 缺少 name/type，补上）
    src_cfg = dict(config_data)
    src_cfg["name"] = name
    src_cfg["type"] = src_type
    result = await _source_to_dict(name, src_cfg)
    result["toolCount"] = _compute_tool_count_from_rm(rm, name)
    return result


async def _load_source_config_from_store(store, name: str) -> dict[str, Any] | None:
    """从 store 加载数据源配置,失败返回 None。"""
    if not _is_store_usable(store):
        return None
    try:
        return await store.get_source(name)
    except Exception as exc:
        logger.warning("查询数据源 %r 失败: %s", name, exc)
        return None


def _load_source_config_from_rm(rm, name: str) -> dict[str, Any] | None:
    """从 rm 加载数据源配置,不存在时返回 None。"""
    if not rm.has_source(name):
        return None
    return rm.get_source_config(name) or {}


async def _load_source_config(rm, store, name: str) -> dict[str, Any] | None:
    """加载数据源配置: 优先用 store,回退到 rm;不存在时返回 None。"""
    src_cfg = await _load_source_config_from_store(store, name)
    if src_cfg is not None:
        return src_cfg
    return _load_source_config_from_rm(rm, name)


def _get_password_from_cfg(src_cfg: dict[str, Any]) -> str:
    """从数据源配置中读取明文密码。"""
    return str(src_cfg.get("password", "") or "")


async def _get_password_ciphertext(store, src_cfg: dict[str, Any], name: str) -> str:
    """获取数据源密码密文,持久化模式从 store 读取,回退到内存明文密码。"""
    if not _is_store_usable(store):
        return _get_password_from_cfg(src_cfg)
    try:
        sid, env = _get_source_env_keys_from_cfg(src_cfg)
        return await store.get_source_password(name, sid, env)
    except Exception as exc:
        logger.warning("读取数据源 %r 密文失败: %s", name, exc)
        return _get_password_from_cfg(src_cfg)


def _filter_tool_names(existing: list[str], to_remove: list[str]) -> list[str]:
    """从 existing 中排除 to_remove 中的工具名。"""
    return [n for n in existing if n not in to_remove]


def _remove_tools_from_default_toolset(rm, tool_names: list[str]) -> None:
    """从默认 toolset(name=="")中移除指定工具名。"""
    default_ts = rm.get_toolset("")
    if default_ts is None:
        return
    default_ts.tool_names = _filter_tool_names(default_ts.tool_names, tool_names)


# ---------------------------------------------------------------------------
# _source_to_dict 及字段处理辅助函数
# ---------------------------------------------------------------------------


async def _compute_tool_count_from_store(store, name: str) -> int:
    """从 store 计算绑定到指定数据源的工具数量,失败返回 0。"""
    if store is None:
        return 0
    try:
        return await store.count_tools_by_source(name)
    except Exception:
        return 0


def _redact_password(value: Any, password_ciphertext: str) -> Any:
    """根据是否提供密文对 password 字段值进行脱敏/回填。"""
    if not value:
        return value
    if password_ciphertext:
        return password_ciphertext
    return "********"


def _build_source_base_dict(
    name: str, source_config: dict[str, Any], tool_count: int
) -> dict[str, Any]:
    """构造数据源响应的基础字段。"""
    return {
        "name": name,
        "type": source_config.get("type", "unknown"),
        "status": "connected",
        "latency": None,
        "error": None,
        "toolCount": tool_count,
    }


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
    if source_config is None:
        source_config = await _resolve_source_config(name, store)
    tool_count = await _compute_tool_count_from_store(store, name)
    result = _build_source_base_dict(name, source_config, tool_count)
    _apply_source_config_fields(result, source_config, password_ciphertext)
    return result


async def _resolve_source_config_from_store(name: str, store) -> dict[str, Any]:
    """从 store 读取数据源配置,失败返回空 dict。"""
    try:
        return await store.get_source(name) or {}
    except Exception:
        return {}


async def _resolve_source_config(name: str, store) -> dict[str, Any]:
    """从 store 读取数据源配置,失败或无 store 时返回空 dict。"""
    if store is None:
        return {}
    return await _resolve_source_config_from_store(name, store)


def _apply_source_config_field(
    result: dict[str, Any],
    k: str,
    v: Any,
    password_ciphertext: str,
) -> None:
    """将单个 source_config 字段写入 result,处理 password 脱敏。"""
    if k in ("name", "type"):
        return
    if k == "password":
        result[k] = _redact_password(v, password_ciphertext)
        return
    result[k] = v


def _apply_source_config_fields(
    result: dict[str, Any],
    source_config: dict[str, Any],
    password_ciphertext: str,
) -> None:
    """将 source_config 中的字段附加到 result,跳过 name/type,处理 password 脱敏。"""
    for k, v in source_config.items():
        _apply_source_config_field(result, k, v, password_ciphertext)


# ---------------------------------------------------------------------------
# 创建/更新数据源校验相关辅助函数
# ---------------------------------------------------------------------------


def _validate_required_fields(name: str, src_type: str) -> None:
    """校验必填字段 name / type。"""
    if not name or not src_type:
        raise HTTPException(status_code=400, detail="name and type are required")


def _validate_system_id(system_id: str) -> None:
    """校验 systemId 必填、长度不超过 10 位、仅含字母数字下划线横线。"""
    import re

    if not system_id:
        raise HTTPException(status_code=400, detail="systemId is required")
    if len(system_id) > 10:
        raise HTTPException(status_code=400, detail="systemId 长度不能超过 10 位")
    if not re.match(r"^[a-zA-Z0-9_-]+$", system_id):
        raise HTTPException(
            status_code=400,
            detail="systemId 只能包含字母、数字、下划线和横线",
        )


def _validate_environment(environment: str) -> None:
    """校验 environment 必填且属于预设环境列表。"""
    if not environment:
        raise HTTPException(status_code=400, detail="environment is required")
    if environment not in ENVIRONMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"environment 必须为 {ENVIRONMENTS} 之一",
        )


def _get_enabled_source_types(config) -> list:
    """从 config 中读取已启用的数据源类型列表。"""
    return getattr(config, "enabled_source_types", []) or []


def _is_whitelist_active(enabled: Any) -> bool:
    """判断白名单是否生效: 非空 list 表示启用白名单。"""
    return isinstance(enabled, list) and bool(enabled)


def _validate_source_type_whitelist(config, src_type: str) -> None:
    """数据源类型白名单校验: 防止绕过 UI 直接调用 API 创建被禁用类型。"""
    enabled = _get_enabled_source_types(config)
    if not _is_whitelist_active(enabled):
        return
    if src_type in enabled:
        return
    raise HTTPException(
        status_code=403,
        detail=f"数据源类型 {src_type!r} 未启用,请联系管理员调整 --enabled-source-types",
    )


def _validate_create_source_input(body: dict[str, Any], config) -> tuple[str, str, str, str]:
    """校验 create_source 入参,返回 (name, src_type, system_id, environment)。"""
    name = body.get("name", "")
    src_type = body.get("type", "")
    system_id = str(body.get("systemId", "") or "").strip()
    environment = str(body.get("environment", "") or "").strip()
    _validate_required_fields(name, src_type)
    _validate_name_param(name)
    _validate_system_id(system_id)
    _validate_environment(environment)
    _validate_source_type_whitelist(config, src_type)
    return name, src_type, system_id, environment


def _validate_name_param(name: str) -> None:
    """校验路径参数 name 格式:1-128 字符,仅 [a-zA-Z0-9_.-]。

    防止特殊字符注入日志、文件路径等非 SQL 场景。
    """
    from data_tool_mcp.config.loader import validate_resource_name

    try:
        validate_resource_name(name, "source")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _validate_update_source_input(body: dict[str, Any], config, old_cfg: dict[str, Any]) -> str:
    """校验 update_source 入参,返回 src_type。

    name 来自路径参数(已在路由入口校验),type 可选(不传则沿用旧值)。
    systemId / environment / type 白名单必须校验,防止绕过创建时的约束。
    """
    src_type = body.get("type", old_cfg.get("type", ""))
    system_id = str(body.get("systemId", "") or "").strip()
    environment = str(body.get("environment", "") or "").strip()
    _validate_required_fields("", src_type)  # type 必填
    _validate_system_id(system_id)
    _validate_environment(environment)
    _validate_source_type_whitelist(config, src_type)
    return src_type


async def _check_source_uniqueness_in_rm(rm, name: str, system_id: str, environment: str) -> None:
    """rm 内存模式下的数据源唯一性校验。"""
    for existing_name, existing_config in rm.get_all_source_configs().items():
        if _is_same_source(existing_name, existing_config, name, system_id, environment):
            raise HTTPException(
                status_code=409,
                detail=f"系统 {system_id} 环境 {environment} 下数据源 {name!r} 已存在",
            )


def _is_same_source(
    existing_name: str,
    existing_config: dict[str, Any],
    name: str,
    system_id: str,
    environment: str,
) -> bool:
    """判断已存在数据源是否与目标 (name, system_id, environment) 冲突。"""
    return (
        existing_name == name
        and existing_config.get("systemId") == system_id
        and existing_config.get("environment") == environment
    )


async def _check_source_uniqueness(rm, store, name: str, system_id: str, environment: str) -> None:
    """数据源唯一性校验,优先用 store,回退到 rm。"""
    if not _is_store_usable(store):
        await _check_source_uniqueness_in_rm(rm, name, system_id, environment)
        return
    existing = await store.get_source(name, system_id, environment)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"系统 {system_id} 环境 {environment} 下数据源 {name!r} 已存在",
        )


async def _save_source_to_store(
    store, name: str, src_type: str, config_data: dict[str, Any]
) -> bool:
    """保存数据源到 store,ValueError 转为 409,其他异常仅告警。返回是否成功。"""
    try:
        await store.save_source(name, src_type, config_data)
        return True
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.warning("持久化数据源 %r 失败: %s", name, exc)
        return False


async def _persist_new_source(store, name: str, src_type: str, config_data: dict[str, Any]) -> bool:
    """持久化新建数据源,ValueError 转为 409,其他异常仅告警。返回是否成功。"""
    if not _is_store_usable(store):
        return True  # 无 store 视为成功(单机模式)
    return await _save_source_to_store(store, name, src_type, config_data)


# ---------------------------------------------------------------------------
# 更新/删除数据源时清理旧工具的辅助函数
# ---------------------------------------------------------------------------


async def _clear_store_tools_for_source(store, rm, name: str, old_cfg: dict[str, Any]) -> None:
    """同步清除 store 中该数据源的旧工具(随后 _auto_create_tools 会重新持久化)。"""
    if not _is_store_usable(store):
        return
    try:
        old_sid, old_env = _get_source_env_keys_from_cfg(old_cfg)
        await store.delete_tools_by_source(name, old_sid, old_env)
    except Exception as exc:
        logger.warning("清除数据源 %r 的旧工具失败: %s", name, exc)


async def _delete_old_source_record(
    store, name: str, old_cfg: dict[str, Any], new_config: dict[str, Any]
) -> None:
    """更新数据源时,若 system_id 或 environment 变更,删除旧的 store 记录。

    save_source 以 (name, system_id, environment) 为复合键做 upsert,
    当键值变更时会插入新记录而非更新,旧记录需手动清除。
    """
    if not _is_store_usable(store):
        return
    old_sid, old_env = _get_source_env_keys_from_cfg(old_cfg)
    new_sid = str(new_config.get("systemId", "") or "").strip()
    new_env = str(new_config.get("environment", "") or "").strip()
    if old_sid == new_sid and old_env == new_env:
        return
    try:
        await store.delete_source(name, old_sid, old_env)
    except Exception as exc:
        logger.warning("清除数据源 %r 的旧 store 记录失败: %s", name, exc)


# ---------------------------------------------------------------------------
# 系统聚合相关辅助函数
# ---------------------------------------------------------------------------


def _init_system_entry(sid: str) -> dict[str, Any]:
    """构造 systems dict 中单个系统的初始结构。"""
    return {
        "systemId": sid,
        "sourceCount": 0,
        "sources": [],
        "environments": [],
    }


def _append_env_to_system(system_entry: dict[str, Any], env: str) -> None:
    """将环境编号追加到系统条目(去重)。"""
    if env and env not in system_entry["environments"]:
        system_entry["environments"].append(env)


def _add_source_to_systems(
    systems: dict[str, dict[str, Any]],
    name: str,
    cfg: dict[str, Any],
) -> None:
    """将单个数据源聚合到 systems dict 中。"""
    sid, env = _extract_env_keys(cfg)
    if not sid:
        return
    if sid not in systems:
        systems[sid] = _init_system_entry(sid)
    systems[sid]["sourceCount"] += 1
    systems[sid]["sources"].append(name)
    _append_env_to_system(systems[sid], env)


def _aggregate_systems(configs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """按 systemId 聚合数据源,返回排序后的系统列表。"""
    systems: dict[str, dict[str, Any]] = {}
    for name, cfg in configs.items():
        _add_source_to_systems(systems, name, cfg)
    return sorted(systems.values(), key=lambda x: x["systemId"])


# ---------------------------------------------------------------------------
# Toolset 分类相关辅助函数
# ---------------------------------------------------------------------------


def _classify_named_toolset_type(name: str, source_names: set[str], system_ids: set[str]) -> str:
    """判断具名 toolset 类型: system / source / custom。"""
    if name in system_ids:
        return "system"
    if name in source_names:
        return "source"
    return "custom"


def _classify_toolset_type(name: str, source_names: set[str], system_ids: set[str]) -> str:
    """判断 toolset 类型: all / system / source / custom。"""
    if not name:
        return "all"
    return _classify_named_toolset_type(name, source_names, system_ids)


def _build_toolset_item(name: str, tool_count: int, ts_type: str) -> dict[str, Any]:
    """构造单个 toolset 响应项。"""
    return {
        "name": name,
        "displayName": "全部工具" if not name else name,
        "toolCount": tool_count,
        "type": ts_type,
    }


_TOOLSET_TYPE_ORDER = {"all": 0, "system": 1, "source": 2, "custom": 3}


def _sort_toolsets(result: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """排序: 全部 → system → source → custom, 每组内按名称排序。"""
    result.sort(key=lambda x: (_TOOLSET_TYPE_ORDER.get(x["type"], 9), x["name"]))
    return result


def _extract_source_names(items) -> list[str]:
    """从 items 中提取非空 name 列表。"""
    return [s["name"] for s in items if s.get("name")]


def _extract_system_ids(items) -> set[str]:
    """从 items 中提取非空 systemId 集合。"""
    result: set[str] = set()
    for item in items:
        sid, _ = _extract_env_keys(item)
        if sid:
            result.add(sid)
    return result


def _extract_source_and_system_names(
    sources_list: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    """从 sources_list 中提取 (source_names, system_ids) 集合。"""
    source_names = set(_extract_source_names(sources_list))
    system_ids = _extract_system_ids(sources_list)
    return source_names, system_ids


def _extract_source_and_system_names_from_rm(rm) -> tuple[set[str], set[str]]:
    """从 rm 中提取 (source_names, system_ids) 集合。"""
    configs = rm.get_all_source_configs()
    source_names = set(configs.keys())
    system_ids = _extract_system_ids(configs.values())
    return source_names, system_ids


# ---------------------------------------------------------------------------
# dashboard / health 辅助函数
# ---------------------------------------------------------------------------


async def _query_today_requests_from_store(store) -> int:
    """从 store 查询今日 MCP 请求数,失败返回 0。"""
    if not _is_store_usable(store):
        return 0
    try:
        from datetime import date

        today_str = date.today().isoformat()
        stats = await store.query_mcp_stats(start_date=today_str, end_date=today_str)
        return stats.get("summary", {}).get("total", 0)
    except Exception as exc:
        logger.warning("查询今日 MCP 请求数失败: %s", exc)
        return 0


async def _query_dashboard_counts(store, rm) -> tuple[int, int]:
    """查询 dashboard 所需的 source/tool 计数。"""
    if not _is_store_usable(store):
        return len(rm.get_all_source_configs()), len(rm.get_tools_map())
    try:
        return await store.count_sources(), await store.count_tools()
    except Exception as exc:
        logger.warning("查询 dashboard 计数失败: %s", exc)
        return len(rm.get_all_source_configs()), len(rm.get_tools_map())


def _get_rm_source_names(rm) -> list[str]:
    """从 rm 内存中获取数据源名列表。"""
    return list(rm.get_all_source_configs().keys())


async def _load_source_names(rm, store) -> list[str]:
    """加载数据源名列表,优先用 store,回退到 rm。"""
    if not _is_store_usable(store):
        return _get_rm_source_names(rm)
    try:
        sources_list = await store.load_sources()
        return _extract_source_names(sources_list)
    except Exception as exc:
        logger.warning("查询 health 数据源列表失败: %s", exc)
        return _get_rm_source_names(rm)


def _build_source_health_item(name: str) -> dict[str, Any]:
    """构造 health 接口中单个数据源的健康状态项。"""
    return {
        "name": name,
        "status": "unknown",
        "latency": None,
        "lastError": None,
    }


# ---------------------------------------------------------------------------
# source-types / tools 列表辅助函数
# ---------------------------------------------------------------------------


def _build_all_schemas_response() -> dict[str, dict[str, Any]]:
    """构造全部数据源类型 schema 响应。"""
    return {k: {"fields": v} for k, v in SOURCE_TYPE_SCHEMAS.items()}


def _build_filtered_schemas_response(enabled_set: set[str]) -> dict[str, dict[str, Any]]:
    """按白名单集合过滤 SOURCE_TYPE_SCHEMAS 响应。"""
    return {k: {"fields": v} for k, v in SOURCE_TYPE_SCHEMAS.items() if k in enabled_set}


def _filter_schemas_by_whitelist(enabled: list) -> dict[str, dict[str, Any]]:
    """按白名单过滤 SOURCE_TYPE_SCHEMAS,空列表表示全部启用。"""
    if not _is_whitelist_active(enabled):
        return _build_all_schemas_response()
    return _build_filtered_schemas_response(set(enabled))


def _get_tool_env_keys(rm, source_name: str | None) -> tuple[str, str]:
    """从数据源配置中提取工具的 (systemId, environment)。"""
    if not source_name:
        return "", ""
    src_cfg = rm.get_source_config(source_name) or {}
    return _get_source_env_keys_from_cfg(src_cfg)


def _build_tool_list_item(rm, name: str, tool) -> dict[str, Any]:
    """构造 list_tools 接口中单个工具的响应项。"""
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    tool_type = rm.get_tool_type(name)
    source_name = getattr(tool, "source_name", None)
    system_id, environment = _get_tool_env_keys(rm, source_name)
    return {
        "name": name,
        "type": tool_type,
        "source": source_name,
        "description": manifest.description if manifest else None,
        "category": _classify_tool(tool, tool_type),
        "systemId": system_id,
        "environment": environment,
    }


# ---------------------------------------------------------------------------
# get_tool 输入 schema 构造辅助函数
# ---------------------------------------------------------------------------


def _build_param_property(param) -> dict[str, Any]:
    """将单个 ParameterManifest 转为 JSON Schema property。"""
    prop: dict[str, Any] = {
        "type": param.type,
        "description": param.description,
    }
    if param.default is not None:
        prop["default"] = param.default
    if param.allowed_values:
        prop["enum"] = param.allowed_values
    return prop


def _has_manifest_params(manifest) -> bool:
    """判断 manifest 是否有参数。"""
    return bool(manifest and manifest.parameters)


def _collect_param_props(parameters: list) -> tuple[dict[str, Any], list[str]]:
    """收集参数的 properties 和 required 列表。"""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in parameters:
        properties[param.name] = _build_param_property(param)
        if param.required:
            required.append(param.name)
    return properties, required


def _build_input_schema(manifest) -> dict[str, Any] | None:
    """将 manifest.parameters 转为前端使用的 JSON Schema 格式。"""
    if not _has_manifest_params(manifest):
        return None
    properties, required = _collect_param_props(manifest.parameters)
    return {"properties": properties, "required": required}


# ---------------------------------------------------------------------------
# execute_query / list_source_tables 辅助函数
# ---------------------------------------------------------------------------


async def _execute_sql_with_timing(source, statement: str) -> tuple[list[dict[str, Any]], int]:
    """执行 SQL 并返回 (rows, duration_ms)。"""
    import time

    start = time.monotonic()
    rows = await source.execute_sql(statement)
    duration_ms = int((time.monotonic() - start) * 1000)
    return rows, duration_ms


# 各数据源类型对应的表元数据查询 SQL
_DIALECT_TABLES_SQL: dict[str, str] = {
    "sqlite": "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    "postgres": "SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public' ORDER BY name",
    "postgresql": "SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public' ORDER BY name",
    "mysql": "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY name",
    "mssql": "SELECT name FROM sys.tables ORDER BY name",
}

_DEFAULT_TABLES_SQL = "SELECT table_name AS name FROM information_schema.tables ORDER BY name"


def _get_dialect_tables_sql(src_type: str) -> str:
    """根据数据源类型返回对应的表元数据查询 SQL。"""
    return _DIALECT_TABLES_SQL.get(src_type, _DEFAULT_TABLES_SQL)


def _extract_single_table_name(row: dict[str, Any]) -> Any:
    """从单行查询结果中提取表名。"""
    return row.get("name") or row.get("tablename") or list(row.values())[0]


def _filter_non_empty(items: list) -> list:
    """过滤掉列表中的 falsy 值。"""
    return [t for t in items if t]


def _extract_table_names(rows: list[dict[str, Any]]) -> list[str]:
    """从查询结果中提取表名列表。"""
    tables = [_extract_single_table_name(r) for r in rows]
    return _filter_non_empty(tables)


# ---------------------------------------------------------------------------
# mcp_test 辅助函数
# ---------------------------------------------------------------------------


def _resolve_toolset_from_env(system_id: str, environment: str) -> str:
    """根据系统编号和环境推导 toolset 名称。"""
    if system_id and environment:
        return f"{system_id}-{environment}"
    return system_id


def _resolve_effective_toolset(toolset_name: str, system_id: str, environment: str) -> str:
    """确定最终用于过滤的 toolset 名称。"""
    if toolset_name:
        return toolset_name
    return _resolve_toolset_from_env(system_id, environment)


def _validate_toolset_exists(rm, effective_toolset: str) -> None:
    """如果指定了 toolset,校验其是否存在,不存在抛 404。"""
    if not effective_toolset:
        return
    toolset = rm.get_toolset(effective_toolset)
    if toolset is None:
        raise HTTPException(status_code=404, detail=f"toolset {effective_toolset!r} not found")


# ---------------------------------------------------------------------------
# mcp_stats / mcp_logs 辅助函数
# ---------------------------------------------------------------------------


def _get_default_date_range() -> tuple[str, str]:
    """返回默认日期范围 (start_date, end_date): 今天往前 29 天 ~ 今天。"""
    from datetime import date, timedelta

    today = date.today()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")
    return start_date, end_date


def _fill_default_dates(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    """用默认值填充缺失的日期。"""
    default_start, default_end = _get_default_date_range()
    return start_date or default_start, end_date or default_end


def _resolve_date_range(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    """解析日期范围,缺省时使用默认值。"""
    if start_date and end_date:
        return start_date, end_date
    return _fill_default_dates(start_date, end_date)


def _build_no_persistence_stats_response() -> dict[str, Any]:
    """未启用持久化时返回的 mcp_stats 空响应。"""
    return {
        "summary": {"total": 0, "success": 0, "fail": 0, "avg_latency_ms": 0},
        "by_system": [],
        "by_source": [],
        "by_tool": [],
        "timeline": [],
        "note": "未启用持久化存储，无法统计 MCP 请求",
    }


def _build_no_persistence_logs_response(page: int, page_size: int) -> dict[str, Any]:
    """未启用持久化时返回的 mcp_logs 空响应。"""
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_pages": 1,
        "note": "未启用持久化存储，无法查询 MCP 请求记录",
    }


# ===========================================================================
# 路由处理器
# ===========================================================================


@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    """返回 dashboard 概览数据(版本、计数、今日请求数等)。"""
    rm = _get_rm(request)
    config = _get_config(request)
    store = get_store()
    # 今日请求数 — 优先从数据库 mcp_request_logs 表查询（持久化，重启不丢）
    # 回退到内存计数器（未启用持久化时）
    today_requests = await _query_today_requests_from_store(store)
    if today_requests == 0:
        from data_tool_mcp.server.stats import get_request_counter

        today_requests = get_request_counter().get_today_count()
    # 数据源/工具计数 — 优先从数据库查询（多实例一致性），回退到 rm 内存
    source_count, tool_count = await _query_dashboard_counts(store, rm)
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
    """返回数据源健康状态和服务运行状态。"""
    rm = _get_rm(request)
    store = get_store()
    # 数据源名列表 — 优先从数据库查询（多实例一致性），回退到 rm 内存
    source_names = await _load_source_names(rm, store)
    source_health = [_build_source_health_item(name) for name in source_names]
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
    return _filter_schemas_by_whitelist(enabled)


@router.get("/environments")
async def list_environments() -> list[str]:
    """返回预设环境列表，供前端下拉选择。"""
    return ENVIRONMENTS


@router.get("/systems")
async def list_systems(request: Request) -> list[dict[str, Any]]:
    """列出所有系统编号及其数据源数量,供 MCP 配置按系统筛选使用。"""
    rm = _get_rm(request)
    store = get_store()
    configs = await _load_all_source_configs(rm, store)
    return _aggregate_systems(configs)


@router.get("/systems/{system_id}/sources")
async def list_sources_by_system(request: Request, system_id: str) -> list[dict[str, Any]]:
    """按系统编号列出该系统下所有数据源。"""
    rm = _get_rm(request)
    store = get_store()
    if _is_store_usable(store):
        try:
            sources_list = await store.load_sources_by_system(system_id)
            return await _build_sources_response_from_store_list(sources_list, store)
        except Exception as exc:
            logger.warning("查询系统 %r 数据源失败: %s", system_id, exc)
    # 回退到 rm
    return await _build_sources_response_from_rm_filtered(rm, system_id)


async def _build_sources_response_from_store_list(
    sources_list: list[dict[str, Any]],
    store,
) -> list[dict[str, Any]]:
    """将 store 返回的数据源列表转为响应 dict 列表。"""
    result: list[dict[str, Any]] = []
    for s in sources_list:
        name = s.get("name")
        if not name:
            continue
        item = await _source_to_dict(name, s, store=store)
        result.append(item)
    return result


async def _build_rm_source_item(rm, name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """从 rm 内存构造单个数据源响应项,手动计算 tool_count。"""
    src_cfg = cfg or {}
    item = await _source_to_dict(name, src_cfg)
    item["toolCount"] = _compute_tool_count_from_rm(rm, name)
    return item


async def _build_sources_response_from_rm_filtered(
    rm,
    system_id: str,
) -> list[dict[str, Any]]:
    """从 rm 内存按 system_id 过滤并构造响应 dict 列表。"""
    configs = rm.get_all_source_configs()
    result: list[dict[str, Any]] = []
    for name, cfg in configs.items():
        sid, _ = _extract_env_keys(cfg)
        if sid != system_id:
            continue
        result.append(await _build_rm_source_item(rm, name, cfg))
    return result


@router.get("/sources")
async def list_sources(request: Request) -> list[dict[str, Any]]:
    """列出所有数据源(优先从 store,回退到 rm 内存)。"""
    rm = _get_rm(request)
    store = get_store()
    if _is_store_usable(store):
        try:
            sources_list = await store.load_sources()
            return await _build_sources_response_from_store_list(sources_list, store)
        except Exception as exc:
            logger.warning("查询数据源列表失败: %s", exc)
    # 回退到 rm
    return await _build_sources_response_from_rm(rm)


async def _build_sources_response_from_rm(rm) -> list[dict[str, Any]]:
    """从 rm 内存构造全部数据源的响应 dict 列表。"""
    configs = rm.get_all_source_configs()
    result: list[dict[str, Any]] = []
    for name, src_cfg in configs.items():
        src_cfg = src_cfg or {}
        item = await _source_to_dict(name, src_cfg)
        # 回退场景下手动计算 tool_count（_source_to_dict 在无 store 时返回 0）
        item["toolCount"] = _compute_tool_count_from_rm(rm, name)
        result.append(item)
    return result


@router.post("/sources")
async def create_source(request: Request) -> dict[str, Any]:
    """创建数据源并自动生成默认工具,持久化到 ConfigStore。"""
    body = await request.json()
    config = _get_config(request)
    name, src_type, system_id, environment = _validate_create_source_input(body, config)
    rm = _get_rm(request)
    store = get_store()
    # 数据源主键包含系统编号+环境: 同一系统同一环境下数据源名不可重复,不同系统/环境可同名
    # 优先从 store 查询唯一性（多实例一致性），回退到 rm 内存
    await _check_source_uniqueness(rm, store, name, system_id, environment)
    # Normalize field names: frontend sends "database" for sqlite, backend expects "path"
    config_data = {k: v for k, v in body.items() if k not in ("name", "type")}
    _normalize_sqlite_config(src_type, config_data)
    source = await _build_source_or_raise(src_type, name, config_data, "创建数据源失败")
    await rm.add_source(name, source, config=config_data)
    created_tools = await _auto_create_tools(rm, src_type, name)
    # 持久化到 ConfigStore（store 已在上方唯一性校验时获取）
    persisted = await _persist_new_source(store, name, src_type, config_data)
    # 创建后从 store 读取配置（多实例一致性），回退到 config_data + rm
    result = await _build_source_response(rm, store, name, src_type, config_data)
    result["createdTools"] = created_tools
    result["persisted"] = persisted
    return result


@router.get("/sources/{name}")
async def get_source(request: Request, name: str) -> dict[str, Any]:
    """获取指定数据源详情,支持编辑场景回填密文密码。"""
    _validate_name_param(name)
    rm = _get_rm(request)
    store = get_store()
    # 存在性检查 + 配置读取: 优先用 store, 回退到 rm
    src_cfg = await _load_source_config(rm, store, name)
    if src_cfg is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    # 编辑场景: 优先从持久化存储读取密文, 前端原样回传即可保持密码不变;
    # 回退到 ResourceManager 内存配置中的明文密码(未启用持久化时),
    # 前端原样回传时 _normalize_password_for_storage 会加密后落库。
    password_ciphertext = await _get_password_ciphertext(store, src_cfg, name)
    return await _source_to_dict(
        name, src_cfg, password_ciphertext=password_ciphertext, store=store
    )


def _get_source_config_or_empty(rm, name: str) -> dict[str, Any]:
    """从 rm 获取数据源配置,不存在时返回空 dict。"""
    return rm.get_source_config(name) or {}


def _build_config_data(body: dict[str, Any]) -> dict[str, Any]:
    """从请求 body 中提取 config_data(排除 name/type)。"""
    return {k: v for k, v in body.items() if k not in ("name", "type")}


@router.put("/sources/{name}")
async def update_source(request: Request, name: str) -> dict[str, Any]:
    """更新数据源,清理旧工具后重新生成并持久化。"""
    _validate_name_param(name)
    body = await request.json()
    config = _get_config(request)
    rm = _get_rm(request)
    store = get_store()
    # 存在性检查: 优先用 store, 回退到 rm
    if not await _check_source_exists(rm, store, name):
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    # 失效旧 source 缓存(关闭旧连接池)
    old_cfg = _get_source_config_or_empty(rm, name)
    # V1: 校验 systemId / environment / type 白名单,防止绕过创建时的约束
    src_type = _validate_update_source_input(body, config, old_cfg)
    await rm.invalidate_source(name)
    config_data = _build_config_data(body)
    _normalize_sqlite_config(src_type, config_data)
    # Remove old tools bound to this source before recreating
    old_tools = await _get_tools_for_source(rm, store, name)
    await _remove_tools_for_update(rm, store, name, old_cfg, old_tools)
    source = await _build_source_or_raise(src_type, name, config_data, "更新数据源失败")
    await rm.add_source(name, source, config=config_data)
    await _auto_create_tools(rm, src_type, name)
    # 持久化更新数据源到 ConfigStore（工具已在 _auto_create_tools 中持久化）
    persisted = await _persist_source(store, name, src_type, config_data)
    # T2: 仅在持久化成功后才删除旧 store 记录,防止中间异常导致数据丢失。
    # save_source 以 (name, system_id, environment) 为复合键做 upsert,
    # 当键值变更时会插入新记录而非更新,旧记录需手动清除。
    if persisted:
        await _delete_old_source_record(store, name, old_cfg, config_data)
    # 更新后从 store 读取配置（多实例一致性），回退到 config_data + rm
    result = await _build_source_response(rm, store, name, src_type, config_data)
    result["persisted"] = persisted
    return result


async def _remove_tools_for_update(
    rm,
    store,
    name: str,
    old_cfg: dict[str, Any],
    old_tools: list[str],
) -> None:
    """更新数据源时清理旧工具:从 rm 内存 + 默认 toolset + store 中移除。"""
    for tname in old_tools:
        rm.remove_tool(tname)
    _remove_tools_from_default_toolset(rm, old_tools)
    # 同步清除 store 中该数据源的旧工具（随后 _auto_create_tools 会重新持久化）。
    # 旧工具仍属于更新前的 system_id + environment，需从旧 source config 中提取。
    await _clear_store_tools_for_source(store, rm, name, old_cfg)


async def _remove_source_tools(rm, store, name: str) -> None:
    """移除数据源绑定的所有工具:从 rm 内存 + 默认 toolset 中删除。"""
    removed = await _get_tools_for_source(rm, store, name)
    for tname in removed:
        rm.remove_tool(tname)
    _remove_tools_from_default_toolset(rm, removed)


@router.delete("/sources/{name}", status_code=204)
async def delete_source(request: Request, name: str):
    """删除数据源及其绑定工具,并从默认 toolset 移除。"""
    _validate_name_param(name)
    rm = _get_rm(request)
    store = get_store()
    # 存在性检查: 优先用 store, 回退到 rm
    if not await _check_source_exists(rm, store, name):
        return
    # 持久化删除前先取出 system_id + environment，用于精确删除 store 中记录
    old_cfg = _get_source_config_or_empty(rm, name)
    sid, env = _get_source_env_keys_from_cfg(old_cfg)
    await rm.remove_source(name)
    # Remove tools bound to this source (auto-generated or manual) and
    # drop them from the default toolset so no orphan tools remain.
    # 优先从 store 查询（多实例一致性），回退到 rm 内存
    await _remove_source_tools(rm, store, name)
    # 持久化删除到 ConfigStore
    await _persist_delete_source(store, name, sid, env)


async def _persist_delete_source(store, name: str, sid: str, env: str) -> None:
    """持久化删除数据源及其工具到 ConfigStore（单事务原子删除）。"""
    if not _is_store_usable(store):
        return
    try:
        await store.delete_source_and_tools(name, sid, env)
    except Exception as exc:
        logger.warning("持久化删除数据源 %r 失败: %s", name, exc)


@router.post("/sources/{name}/test")
async def test_source(request: Request, name: str) -> dict[str, Any]:
    """测试数据源连通性,返回 ok/latency/error。"""
    _validate_name_param(name)
    rm = _get_rm(request)
    if not rm.has_source(name):
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    source = await rm.get_source(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    try:
        result = await _measure_source_connect_latency(source)
        return result
    finally:
        await rm.release_source(name)


async def _measure_source_connect_latency(source) -> dict[str, Any]:
    """测量 source.connect() 延迟,返回 ok/latency/error。"""
    import time

    try:
        start = time.monotonic()
        if hasattr(source, "connect"):
            await source.connect()
        latency = int((time.monotonic() - start) * 1000)
        return {"ok": True, "latency": latency, "error": None}
    except Exception as exc:
        return {"ok": False, "latency": 0, "error": str(exc)}


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    """列出所有工具及其分类信息。"""
    rm = _get_rm(request)
    tools = rm.get_tools_map()
    return [_build_tool_list_item(rm, name, tool) for name, tool in tools.items()]


def _build_tool_detail(rm, name: str, tool) -> dict[str, Any]:
    """构造 get_tool 接口的工具详情响应。"""
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    tool_type = rm.get_tool_type(name)
    return {
        "name": name,
        "type": tool_type,
        "source": getattr(tool, "source_name", None),
        "description": manifest.description if manifest else None,
        "inputSchema": _build_input_schema(manifest),
        "category": _classify_tool(tool, tool_type),
    }


@router.get("/tools/{name}")
async def get_tool(request: Request, name: str) -> dict[str, Any]:
    """获取指定工具详情(含 inputSchema)。"""
    rm = _get_rm(request)
    tool = rm.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool {name!r} not found")
    return _build_tool_detail(rm, name, tool)


async def _invoke_tool_safe(tool, params: dict[str, Any], rm) -> dict[str, Any]:
    """调用工具并处理异常:ValueError 转 400,其他转 500。"""
    try:
        result = await tool.invoke(params, source_provider=rm)
        return {"result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/tools/{name}/invoke")
async def invoke_tool(request: Request, name: str) -> dict[str, Any]:
    """调用指定工具并返回结果。"""
    rm = _get_rm(request)
    tool = rm.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool {name!r} not found")
    body = await request.json()
    params = body.get("params", {})
    return await _invoke_tool_safe(tool, params, rm)


@router.delete("/tools/{name}", status_code=204)
async def delete_tool(request: Request, name: str):
    """删除指定工具,并持久化到 ConfigStore。"""
    rm = _get_rm(request)
    rm.remove_tool(name)
    # 持久化删除到 ConfigStore
    store = get_store()
    if not _is_store_usable(store):
        return
    try:
        await store.delete_tool(name)
    except Exception as exc:
        logger.warning("持久化删除工具 %r 失败: %s", name, exc)


@router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    """返回服务端配置概览(YAML + parsed)。"""
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
    """触发配置重载(占位实现)。"""
    return {"ok": True, "errors": None}


def _validate_query_input(source_name: str, statement: str) -> None:
    """校验查询接口入参:sourceName 和 statement 均必填。"""
    if not source_name or not statement:
        raise HTTPException(status_code=400, detail="sourceName and statement are required")


def _validate_source_sql_support(source, source_name: str) -> None:
    """校验数据源是否支持 SQL 查询。"""
    if not hasattr(source, "execute_sql"):
        raise HTTPException(
            status_code=400, detail=f"source {source_name!r} does not support SQL queries"
        )


@router.post("/query")
async def execute_query(request: Request) -> dict[str, Any]:
    """在指定数据源上执行 SQL 查询并返回结果。"""
    body = await request.json()
    source_name = body.get("sourceName", "")
    statement = body.get("statement", "")
    _validate_query_input(source_name, statement)
    rm = _get_rm(request)
    source = await rm.get_source(source_name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {source_name!r} not found")
    try:
        _validate_source_sql_support(source, source_name)
        return await _run_sql_query(source, statement)
    finally:
        await rm.release_source(source_name)


def _build_sql_query_response(rows: list[dict[str, Any]], duration_ms: int) -> dict[str, Any]:
    """构造 SQL 查询响应 dict。"""
    columns = list(rows[0].keys()) if rows else []
    return {
        "columns": columns,
        "rows": [list(r.values()) for r in rows],
        "rowCount": len(rows),
        "durationMs": duration_ms,
    }


async def _run_sql_query(source, statement: str) -> dict[str, Any]:
    """执行 SQL 查询并返回 columns/rows/rowCount/durationMs。"""
    try:
        rows, duration_ms = await _execute_sql_with_timing(source, statement)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _build_sql_query_response(rows, duration_ms)


@router.get("/sources/{name}/tables")
async def list_source_tables(request: Request, name: str) -> dict[str, Any]:
    """List tables in a SQL data source, for the query console sidebar."""
    _validate_name_param(name)
    rm = _get_rm(request)
    source = await rm.get_source(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    try:
        if not hasattr(source, "execute_sql"):
            raise HTTPException(
                status_code=400, detail=f"source {name!r} does not support SQL queries"
            )
        return await _query_source_tables(source)
    finally:
        await rm.release_source(name)


async def _query_source_tables(source) -> dict[str, Any]:
    """查询数据源中的表列表。"""
    # Detect dialect for the right metadata query
    src_type = getattr(source, "source_type", "")
    sql = _get_dialect_tables_sql(src_type)
    try:
        rows = await source.execute_sql(sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"tables": _extract_table_names(rows)}


def _parse_mcp_test_input(body: dict[str, Any]) -> tuple[str, str, str]:
    """从 mcp_test 请求 body 中解析 (toolset_name, system_id, environment)。"""
    toolset_name = body.get("toolset", "") or ""
    system_id, environment = _extract_env_keys(body)
    return toolset_name, system_id, environment


def _build_mcp_test_response(result: dict[str, Any]) -> dict[str, Any]:
    """构造 mcp_test 接口响应。"""
    tools = result.get("tools", [])
    return {
        "ok": True,
        "count": len(tools),
        "tools": [{"name": t["name"], "description": t.get("description", "")} for t in tools],
    }


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
    toolset_name, system_id, environment = _parse_mcp_test_input(body)
    rm = _get_rm(request)

    # 确定最终用于过滤的 toolset 名称:
    #   选了数据源 → 用数据源名(数据源本身就是一个 toolset)
    #   仅选系统编号+环境 → 优先用 {system_id}-{environment} 格式
    effective_toolset = _resolve_effective_toolset(toolset_name, system_id, environment)
    _validate_toolset_exists(rm, effective_toolset)

    from data_tool_mcp.server.mcp.protocol import MCPProtocol

    protocol = MCPProtocol(rm, toolset_name=effective_toolset)
    result = await protocol.handle_tools_list({})
    return _build_mcp_test_response(result)


@router.get("/toolsets")
async def list_toolsets(request: Request) -> list[dict[str, Any]]:
    """列出所有 toolset（工具集），供 MCP 配置的 toolset 选择下拉框使用。

    返回每个 toolset 的名称和工具数量。空名 toolset（默认包含所有工具）
    显示为 "全部工具"。标注 toolset 类型(source/system/custom)以便前端分组。
    """
    store = get_store()
    if _is_store_usable(store):
        result = await _build_toolsets_from_store(store)
        if result:
            return result
    # store 不可用或返回空列表时回退到 rm 内存
    rm = _get_rm(request)
    return _build_toolsets_from_rm(rm)


def _build_toolset_entry(
    item: dict[str, Any],
    source_names: set[str],
    system_ids: set[str],
) -> dict[str, Any]:
    """从 store 返回的单个 toolset 项构造响应项。"""
    name = item.get("name", "")
    tools = item.get("tools", []) or []
    ts_type = _classify_toolset_type(name, source_names, system_ids)
    return _build_toolset_item(name, len(tools), ts_type)


async def _build_toolsets_from_store(store) -> list[dict[str, Any]] | None:
    """从 store 构造 toolset 响应列表,失败时返回 None 触发回退。"""
    try:
        toolsets_list = await store.load_toolsets()
        sources_list = await store.load_sources()
    except Exception as exc:
        logger.warning("查询 toolset 列表失败: %s", exc)
        return None
    source_names, system_ids = _extract_source_and_system_names(sources_list)
    result = [_build_toolset_entry(item, source_names, system_ids) for item in toolsets_list]
    return _sort_toolsets(result)


def _build_toolsets_from_rm(rm) -> list[dict[str, Any]]:
    """从 rm 内存构造 toolset 响应列表。"""
    toolsets = rm.get_toolsets_map()
    source_names, system_ids = _extract_source_and_system_names_from_rm(rm)
    result: list[dict[str, Any]] = []
    for name, toolset in toolsets.items():
        ts_type = _classify_toolset_type(name, source_names, system_ids)
        result.append(_build_toolset_item(name, len(toolset.tool_names), ts_type))
    return _sort_toolsets(result)


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
    store = get_store()
    if not _is_store_usable(store):
        return _build_no_persistence_stats_response()

    start_date, end_date = _resolve_date_range(start_date, end_date)
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
    store = get_store()
    if not _is_store_usable(store):
        return _build_no_persistence_logs_response(page, page_size)

    start_date, end_date = _resolve_date_range(start_date, end_date)
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
