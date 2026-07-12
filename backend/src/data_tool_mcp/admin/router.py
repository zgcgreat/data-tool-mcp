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
    sources = rm.get_sources_map()
    tools = rm.get_tools_map()
    # 今日请求数 — 从内存计数器读取(跨日自动重置)
    from data_tool_mcp.server.stats import get_request_counter
    today_requests = get_request_counter().get_today_count()
    return {
        "version": getattr(config, "version", "0.1.0"),
        "uptime": None,
        "sourceCount": len(sources),
        "sourceOnline": len(sources),
        "toolCount": len(tools),
        "todayRequests": today_requests,
        "sourceHealth": [],
        "recentErrors": [],
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    rm = _get_rm(request)
    sources = rm.get_sources_map()
    source_health = []
    for name, source in sources.items():
        source_health.append({
            "name": name,
            "status": "unknown",
            "latency": None,
            "lastError": None,
        })
    return {"sources": source_health, "server": "running"}


@router.get("/source-types")
async def source_types() -> dict[str, Any]:
    return {k: {"fields": v} for k, v in SOURCE_TYPE_SCHEMAS.items()}


def _source_to_dict(name: str, source: Any, rm=None) -> dict[str, Any]:
    tool_count = 0
    if rm is not None:
        tool_count = sum(
            1 for t in rm.get_tools_map().values()
            if getattr(t, "source_name", None) == name
        )
    result: dict[str, Any] = {
        "name": name,
        "type": getattr(source, "source_type", "unknown"),
        "status": "connected",
        "latency": None,
        "error": None,
        "toolCount": tool_count,
    }
    # 附加配置字段（密码脱敏）
    if rm is not None:
        config = rm.get_source_config(name)
        if config:
            for k, v in config.items():
                if k == "password" and v:
                    result[k] = "********"
                else:
                    result[k] = v
    return result


@router.get("/sources")
async def list_sources(request: Request) -> list[dict[str, Any]]:
    rm = _get_rm(request)
    sources = rm.get_sources_map()
    return [_source_to_dict(name, source, rm) for name, source in sources.items()]


@router.post("/sources")
async def create_source(request: Request) -> dict[str, Any]:
    body = await request.json()
    name = body.get("name", "")
    src_type = body.get("type", "")
    if not name or not src_type:
        raise HTTPException(status_code=400, detail="name and type are required")
    rm = _get_rm(request)
    if name in rm.get_sources_map():
        raise HTTPException(status_code=409, detail=f"source {name!r} already exists")
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
    # 持久化到 ConfigStore
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            await store.save_source(name, src_type, config_data)
        except Exception as exc:
            logger.warning("持久化数据源 %r 失败: %s", name, exc)
    result = _source_to_dict(name, source, rm)
    result["createdTools"] = created_tools
    return result


@router.get("/sources/{name}")
async def get_source(request: Request, name: str) -> dict[str, Any]:
    rm = _get_rm(request)
    sources = rm.get_sources_map()
    if name not in sources:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    source = sources[name]
    return _source_to_dict(name, source, rm)


@router.put("/sources/{name}")
async def update_source(request: Request, name: str) -> dict[str, Any]:
    body = await request.json()
    rm = _get_rm(request)
    if name not in rm.get_sources_map():
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
    old_tools = [
        tname for tname, t in rm.get_tools_map().items()
        if getattr(t, "source_name", None) == name
    ]
    for tname in old_tools:
        rm.remove_tool(tname)
    default_ts = rm.get_toolset("")
    if default_ts is not None:
        default_ts.tool_names = [n for n in default_ts.tool_names if n not in old_tools]
    # 同步清除 store 中该数据源的旧工具（随后 _auto_create_tools 会重新持久化）
    store = get_store()
    if store is not None and store.is_persistent:
        try:
            await store.delete_tools_by_source(name)
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
    return _source_to_dict(name, source, rm)


@router.delete("/sources/{name}", status_code=204)
async def delete_source(request: Request, name: str):
    rm = _get_rm(request)
    if name in rm.get_sources_map():
        source = rm.get_source(name)
        if hasattr(source, "close"):
            try:
                await source.close()
            except Exception:
                pass
        rm.remove_source(name)
        # Remove tools bound to this source (auto-generated or manual) and
        # drop them from the default toolset so no orphan tools remain.
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
        store = get_store()
        if store is not None and store.is_persistent:
            try:
                await store.delete_source(name)
                await store.delete_tools_by_source(name)
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
        result.append({
            "name": name,
            "type": tool_type,
            "source": getattr(tool, "source_name", None),
            "description": manifest.description if manifest else None,
            "category": _classify_tool(tool, tool_type),
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
    """
    body = await request.json()
    toolset_name = body.get("toolset", "") or ""
    rm = _get_rm(request)

    # 如果指定了 toolset，先校验其是否存在
    if toolset_name:
        toolset = rm.get_toolset(toolset_name)
        if toolset is None:
            raise HTTPException(status_code=404, detail=f"toolset {toolset_name!r} not found")

    from data_tool_mcp.server.mcp.protocol import MCPProtocol
    protocol = MCPProtocol(rm, toolset_name=toolset_name)
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
    显示为 "全部工具"。
    """
    rm = _get_rm(request)
    toolsets = rm.get_toolsets_map()
    result: list[dict[str, Any]] = []
    for name, toolset in toolsets.items():
        result.append({
            "name": name,
            "displayName": "全部工具" if not name else name,
            "toolCount": len(toolset.tool_names),
        })
    return result



