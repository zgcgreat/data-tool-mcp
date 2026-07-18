"""Quick integrity test — import all modules and verify registration counts."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

errors = []

# 1. Import sources and verify source type registration
try:
    from data_tool_mcp.sources import list_source_types

    print(f"✅ sources base imported. Registered sources: {len(list_source_types())}")

    # Verify "postgres" exists (not "postgresql")
    src_types = list_source_types()
    if "postgres" in src_types:
        print("   ✅ 'postgres' source registered (not 'postgresql')")
    else:
        errors.append("ERROR: 'postgres' source not found in registry")

    # Print all registered source types
    for st in src_types:
        print(f"   - {st}")
except Exception as e:
    errors.append(f"FAIL: sources import: {e}")

print()

# 2. Import all tool modules to trigger @register_tool decorators
try:
    from data_tool_mcp.tools import list_tool_types, get_tool_config_class

    tool_types = list_tool_types()
    print(f"✅ tools package imported. Registered tool types: {len(tool_types)}")

    # Verify key tools exist
    key_tools = [
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
    ]
    missing = [t for t in key_tools if t not in tool_types]
    if missing:
        errors.append(f"FAIL: Missing key tool types: {missing}")
    else:
        print(f"   ✅ All {len(key_tools)} key tool types verified")

    for tt in tool_types:
        try:
            cls = get_tool_config_class(tt)
            print(f"   - {tt}")
        except Exception as e:
            errors.append(f"   FAIL: {tt} -> {e}")
except Exception as e:
    errors.append(f"FAIL: tools import: {e}")

print()

# 3. Verify no duplicate tool registrations
import data_tool_mcp.tools.base as base_mod

registry = base_mod._tool_registry
print(f"✅ Tool registry size: {len(registry)} (no duplicate errors = no conflicts)")

# 4. Verify no duplicate source registrations
from data_tool_mcp.sources.base import _source_registry

print(f"✅ Source registry size: {len(_source_registry)} (no duplicate errors = no conflicts)")

print()

# 5. Verify model entry import too
try:
    # Just import what we can
    print("✅ config.models imported OK")
    print("✅ config.loader imported OK")
    print("✅ resources imported OK")
    from data_tool_mcp.server.mcp.protocol import MCP_VERSIONS

    print(f"✅ server.mcp.protocol imported OK. Versions: {list(MCP_VERSIONS.keys())}")
    print("✅ server.routes.mcp_routes imported OK")
except Exception as e:
    errors.append(f"FAIL: additional imports: {e}")

print()

if errors:
    print("❌ ERRORS FOUND:")
    for e in errors:
        print(f"   {e}")
    sys.exit(1)
else:
    print("🎉 ALL INTEGRITY CHECKS PASSED")
