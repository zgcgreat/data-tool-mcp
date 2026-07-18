"""admin 路由使用的静态数据与常量。

从 admin/router.py 拆分而来，集中存放：
  - 预设环境列表
  - prebuilt yaml 目录与文件名映射
  - 数据源类型 → 默认 fallback 工具清单
  - 数据源类型 → 表单字段 schema
  - 各方言的表元数据查询 SQL
  - toolset 类型排序权重
"""

from __future__ import annotations

import os
from typing import Any

# 预设环境列表（按命名规范顺序）
ENVIRONMENTS = ["dev", "st", "uat", "prd"]

# Directory holding the prebuilt *.yaml configs (sibling package data).
PREBUILT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "prebuiltconfigs"
)

# Mapping from registered source type → prebuilt yaml file name (when they differ).
PREBUILT_YAML_OVERRIDES: dict[str, str] = {
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
SOURCE_DEFAULT_TOOLS: dict[str, list[tuple[str, str]]] = {
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

# 各数据源类型对应的表元数据查询 SQL
DIALECT_TABLES_SQL: dict[str, str] = {
    "sqlite": "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    "postgres": "SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public' ORDER BY name",
    "postgresql": "SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public' ORDER BY name",
    "mysql": "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY name",
    "mssql": "SELECT name FROM sys.tables ORDER BY name",
}

DEFAULT_TABLES_SQL = "SELECT table_name AS name FROM information_schema.tables ORDER BY name"

# toolset 类型排序权重: 全部 → system → source → custom
TOOLSET_TYPE_ORDER: dict[str, int] = {"all": 0, "system": 1, "source": 2, "custom": 3}
