"""Source package — auto-imports all registered source modules.

⚠️ 依赖约定（重要，新增 source 务必遵守）
----------------------------------------
本包在导入时会 auto-import 下方所有 source 模块，以触发各自的 `@register_source`
装饰器完成注册。因此：

- **禁止在模块顶层 eager import 任何「可选 extra 驱动」**（如 mongodb → `motor`、
  postgres → `asyncpg`、clickhouse → `clickhouse-driver` 等）。否则未安装对应 extra
  的用户在后端启动时会立即 `ModuleNotFoundError`，拖垮整个服务。
- **正确范式**：将驱动 import 放在 `SourceConfig.initialize()`（或 `connect()`）
  **内部延迟导入**，只有在真正创建该类型连接时才需要它。
- `mongodb.py`、`http_source.py`、`redis.py` 均已采用此范式（分别在 `initialize()`
  内延迟导入 `motor` / `httpx` / `redis.asyncio`），作为参考范例。新增可选驱动
  source 时务必沿用，避免重蹈覆辙。
"""

from data_tool_mcp.sources.base import (
    NoSQLSource,
    SQLSource,
    Source,
    SourceConfig,
    decode_source_config,
    get_source_config_class,
    list_source_types,
    register_source,
    register_source_alias,
)

# Auto-import concrete source modules to trigger @register_source decorators
# Maps to Go: init() registration in each source package
from data_tool_mcp.sources import postgresql as _postgresql  # noqa: F401
from data_tool_mcp.sources import mysql as _mysql  # noqa: F401
from data_tool_mcp.sources import redis as _redis  # noqa: F401
from data_tool_mcp.sources import sqlite as _sqlite  # noqa: F401
from data_tool_mcp.sources import mongodb as _mongodb  # noqa: F401
from data_tool_mcp.sources import mssql as _mssql  # noqa: F401
from data_tool_mcp.sources import clickhouse as _clickhouse  # noqa: F401
from data_tool_mcp.sources import snowflake as _snowflake  # noqa: F401
from data_tool_mcp.sources import oracle as _oracle  # noqa: F401
from data_tool_mcp.sources import oceanbase as _oceanbase  # noqa: F401
from data_tool_mcp.sources import trino as _trino  # noqa: F401
from data_tool_mcp.sources import cockroachdb as _cockroachdb  # noqa: F401
from data_tool_mcp.sources import tidb as _tidb  # noqa: F401
from data_tool_mcp.sources import yugabytedb as _yugabytedb  # noqa: F401
from data_tool_mcp.sources import firebird as _firebird  # noqa: F401
from data_tool_mcp.sources import singlestore as _singlestore  # noqa: F401
from data_tool_mcp.sources import mindsdb as _mindsdb  # noqa: F401

# NoSQL sources
from data_tool_mcp.sources import cassandra as _cassandra  # noqa: F401
from data_tool_mcp.sources import neo4j_source as _neo4j_source  # noqa: F401
from data_tool_mcp.sources import elasticsearch as _elasticsearch  # noqa: F401
from data_tool_mcp.sources import couchbase as _couchbase  # noqa: F401
from data_tool_mcp.sources import valkey as _valkey  # noqa: F401
from data_tool_mcp.sources import scylladb as _scylladb  # noqa: F401
from data_tool_mcp.sources import dgraph as _dgraph  # noqa: F401

# Cloud API sources
from data_tool_mcp.sources import bigquery as _bigquery  # noqa: F401
from data_tool_mcp.sources import spanner as _spanner  # noqa: F401
from data_tool_mcp.sources import alloydbpg as _alloydbpg  # noqa: F401
from data_tool_mcp.sources import alloydbadmin as _alloydbadmin  # noqa: F401
from data_tool_mcp.sources import cloudsqlpg as _cloudsqlpg  # noqa: F401
from data_tool_mcp.sources import cloudsqlmysql as _cloudsqlmysql  # noqa: F401
from data_tool_mcp.sources import cloudsqlmssql as _cloudsqlmssql  # noqa: F401
from data_tool_mcp.sources import cloudsqladmin as _cloudsqladmin  # noqa: F401
from data_tool_mcp.sources import cloudstorage as _cloudstorage  # noqa: F401
from data_tool_mcp.sources import firestore_source as _firestore_source  # noqa: F401
from data_tool_mcp.sources import bigtable as _bigtable  # noqa: F401
from data_tool_mcp.sources import looker_source as _looker_source  # noqa: F401
from data_tool_mcp.sources import cloudmonitoring as _cloudmonitoring  # noqa: F401
from data_tool_mcp.sources import cloudloggingadmin as _cloudloggingadmin  # noqa: F401
from data_tool_mcp.sources import cloudhealthcare as _cloudhealthcare  # noqa: F401
from data_tool_mcp.sources import cloudgda as _cloudgda  # noqa: F401
from data_tool_mcp.sources import dataproc_source as _dataproc_source  # noqa: F401
from data_tool_mcp.sources import dataplex_source as _dataplex_source  # noqa: F401
from data_tool_mcp.sources import datalineage as _datalineage  # noqa: F401
from data_tool_mcp.sources import serverlessspark as _serverlessspark  # noqa: F401
from data_tool_mcp.sources import http_source as _http_source  # noqa: F401

__all__ = [
    "Source",
    "SourceConfig",
    "SQLSource",
    "NoSQLSource",
    "register_source",
    "get_source_config_class",
    "list_source_types",
    "decode_source_config",
]
