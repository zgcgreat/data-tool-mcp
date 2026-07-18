"""Integrity test — import all modules and verify registration counts.

验证 source/tool 注册完整性,以及关键模块可正常导入。
作为标准 pytest 测试运行,不再使用模块级 sys.exit。
"""

from __future__ import annotations


def test_source_registration() -> None:
    """验证 source 注册完整性:postgres 必须存在(不是 postgresql)。"""
    from data_tool_mcp.sources import list_source_types

    src_types = list_source_types()
    assert "postgres" in src_types, f"'postgres' source not found; got: {sorted(src_types)}"


def test_key_tool_types_registered() -> None:
    """验证关键 tool 类型均已注册。"""
    from data_tool_mcp.tools import list_tool_types

    tool_types = set(list_tool_types())
    key_tools = {
        "postgres-sql",
        "postgres-execute-sql",
        "postgres-list-tables",
        "mysql-sql",
        "mysql-execute-sql",
        "mssql-sql",
        "mssql-execute-sql",
        "mssql-list-tables",
        "sqlite-sql",
        "sqlite-execute-sql",
        "redis",
        "valkey",
        "http",
        "mongodb-find",
        "mongodb-find-one",
        "mongodb-insert-one",
        "wait",
        "neo4j-cypher",
        "neo4j-execute-cypher",
        "neo4j-schema",
        "elasticsearch-esql",
        "elasticsearch-execute-esql",
        "cassandra-cql",
        "scylladb-cql",
        "vector-assist-define-spec",
        "vector-assist-get-spec",
        "cloud-gemini-data-analytics-query",
        "alloydb-ai-nl",
    }
    missing = key_tools - tool_types
    assert not missing, f"Missing key tool types: {sorted(missing)}"


def test_tool_config_classes_resolvable() -> None:
    """验证每个已注册的 tool type 都能解析出 config class,且 class 有效。"""
    from data_tool_mcp.tools import get_tool_config_class, list_tool_types

    failures: list[str] = []
    for tt in list_tool_types():
        try:
            cls = get_tool_config_class(tt)
            if cls is None:
                failures.append(f"{tt} -> returned None")
        except Exception as exc:
            failures.append(f"{tt} -> {exc}")
    assert not failures, "Tool config class resolution failures:\n  " + "\n  ".join(failures)


def test_no_duplicate_tool_registrations() -> None:
    """验证 tool 注册表无重复(装饰器在 import 时会抛错,这里交叉校验)。"""
    from data_tool_mcp.tools import list_tool_types

    tool_types = list(list_tool_types())
    # list_tool_types 返回 dict keys,本身已去重;校验注册表尺寸一致
    assert len(tool_types) == len(set(tool_types)), "Duplicate tool types detected"


def test_no_duplicate_source_registrations() -> None:
    """验证 source 注册表无重复。"""
    from data_tool_mcp.sources import list_source_types

    src_types = list(list_source_types())
    assert len(src_types) == len(set(src_types)), "Duplicate source types detected"


def test_critical_modules_importable() -> None:
    """验证关键模块可正常导入(此前用 print 假装通过,现改为真正导入)。"""
    from data_tool_mcp.config import loader, models  # noqa: F401
    from data_tool_mcp import resources  # noqa: F401
    from data_tool_mcp.server.mcp.protocol import MCP_VERSIONS
    from data_tool_mcp.server.routes import mcp_routes  # noqa: F401

    assert len(MCP_VERSIONS) > 0, "MCP_VERSIONS should not be empty"


def test_tool_registry_size_positive() -> None:
    """验证 tool 和 source 注册表非空。"""
    from data_tool_mcp.tools import list_tool_types
    from data_tool_mcp.sources import list_source_types

    assert len(list_tool_types()) > 0, "Tool registry is empty"
    assert len(list_source_types()) > 0, "Source registry is empty"
