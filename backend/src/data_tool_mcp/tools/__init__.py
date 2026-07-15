"""Tool package — auto-imports all registered tool modules."""

from data_tool_mcp.tools.base import (
    BaseTool,
    ConfigBase,
    ParameterManifest,
    SourceProvider,
    Tool,
    ToolAnnotations,
    ToolConfig,
    ToolManifest,
    decode_tool_config,
    get_tool_config_class,
    list_tool_types,
    register_tool,
)

# Auto-import concrete tool modules to trigger @register_tool decorators
from data_tool_mcp.tools import sql_tools as _sql_tools  # noqa: F401
from data_tool_mcp.tools import redis_tools as _redis_tools  # noqa: F401
from data_tool_mcp.tools import mongo_tools as _mongo_tools  # noqa: F401
from data_tool_mcp.tools import pg_tools as _pg_tools  # noqa: F401
from data_tool_mcp.tools import mysql_tools as _mysql_tools  # noqa: F401
from data_tool_mcp.tools import mssql_tools as _mssql_tools  # noqa: F401
from data_tool_mcp.tools import bigquery_tools as _bigquery_tools  # noqa: F401
from data_tool_mcp.tools import other_sql_tools as _other_sql_tools  # noqa: F401
from data_tool_mcp.tools import neo4j_tools as _neo4j_tools  # noqa: F401
from data_tool_mcp.tools import cassandra_tools as _cassandra_tools  # noqa: F401
from data_tool_mcp.tools import es_tools as _es_tools  # noqa: F401
from data_tool_mcp.tools import alloydb_tools as _alloydb_tools  # noqa: F401
from data_tool_mcp.tools import cloudsql_tools as _cloudsql_tools  # noqa: F401
from data_tool_mcp.tools import cloudsqlpg_tools as _cloudsqlpg_tools  # noqa: F401
from data_tool_mcp.tools import cloudstorage_tools as _cloudstorage_tools  # noqa: F401
from data_tool_mcp.tools import firestore_tools as _firestore_tools  # noqa: F401
from data_tool_mcp.tools import looker_tools as _looker_tools  # noqa: F401
from data_tool_mcp.tools import spanner_tools as _spanner_tools  # noqa: F401
from data_tool_mcp.tools import http_tools as _http_tools  # noqa: F401
from data_tool_mcp.tools import cloudhealthcare_tools as _cloudhealthcare_tools  # noqa: F401
from data_tool_mcp.tools import cloudlogging_tools as _cloudlogging_tools  # noqa: F401
from data_tool_mcp.tools import cloudmonitoring_tools as _cloudmonitoring_tools  # noqa: F401
from data_tool_mcp.tools import dataplex_tools as _dataplex_tools  # noqa: F401
from data_tool_mcp.tools import dataproc_tools as _dataproc_tools  # noqa: F401
from data_tool_mcp.tools import serverless_spark_tools as _serverless_spark_tools  # noqa: F401
from data_tool_mcp.tools import cloud_sql_variant_tools as _cloud_sql_variant_tools  # noqa: F401
from data_tool_mcp.tools import valkey_tools as _valkey_tools  # noqa: F401
from data_tool_mcp.tools import couchbase_tools as _couchbase_tools  # noqa: F401
from data_tool_mcp.tools import bigtable_tools as _bigtable_tools  # noqa: F401
from data_tool_mcp.tools import datalineage_tools as _datalineage_tools  # noqa: F401
from data_tool_mcp.tools import cloudgda_tools as _cloudgda_tools  # noqa: F401
from data_tool_mcp.tools import dataform_tools as _dataform_tools  # noqa: F401
from data_tool_mcp.tools import alloydb_ainl_tools as _alloydb_ainl_tools  # noqa: F401
from data_tool_mcp.tools import wait_tools as _wait_tools  # noqa: F401
from data_tool_mcp.tools import hbase_tools as _hbase_tools  # noqa: F401
from data_tool_mcp.tools import tdsql_tools as _tdsql_tools  # noqa: F401

__all__ = [
    "BaseTool",
    "ConfigBase",
    "ParameterManifest",
    "SourceProvider",
    "Tool",
    "ToolAnnotations",
    "ToolConfig",
    "ToolManifest",
    "register_tool",
    "get_tool_config_class",
    "list_tool_types",
    "decode_tool_config",
]
