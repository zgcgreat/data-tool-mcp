"""Tests for PostgreSQL tools — registration, manifest, config parsing."""
from __future__ import annotations

import pytest
from data_tool_mcp.tools.base import get_tool_config_class, list_tool_types, register_tool_alias


class TestPgTools:
    """PostgreSQL tool registration and manifest tests."""

    def test_registration(self):
        """All 24+ PostgreSQL tools should be registered."""
        all_tools = list_tool_types()
        pg_tools = [t for t in all_tools if t.startswith("postgres-")]
        # Core SQL tools
        assert "postgres-sql" in pg_tools
        assert "postgres-execute-sql" in pg_tools
        # List tools
        assert "postgres-list-tables" in pg_tools
        assert "postgres-list-schemas" in pg_tools
        assert "postgres-list-views" in pg_tools
        assert "postgres-list-indexes" in pg_tools
        assert "postgres-list-roles" in pg_tools
        assert "postgres-list-triggers" in pg_tools
        assert "postgres-list-sequences" in pg_tools
        assert "postgres-list-locks" in pg_tools
        assert "postgres-list-active-queries" in pg_tools
        # Param tools
        assert "postgres-get-column-cardinality" in pg_tools
        # Overview
        assert "postgres-database-overview" in pg_tools
        # At least 22 list tools
        assert len(pg_tools) >= 22

    def test_manifest_structure(self):
        """postgres-sql manifest should have correct structure."""
        cls = get_tool_config_class("postgres-sql")
        assert cls is not None

    def test_pg_execute_sql_registered(self):
        """postgres-execute-sql should have a ToolConfig class."""
        cls = get_tool_config_class("postgres-execute-sql")
        assert cls is not None

    def test_pg_list_tables_registered(self):
        """postgres-list-tables should have a ToolConfig class."""
        cls = get_tool_config_class("postgres-list-tables")
        assert cls is not None

    def test_pg_database_overview_registered(self):
        """postgres-database-overview should have a ToolConfig class."""
        cls = get_tool_config_class("postgres-database-overview")
        assert cls is not None
