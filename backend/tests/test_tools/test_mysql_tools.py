"""Tests for MySQL tools — registration, manifest, config parsing."""

from __future__ import annotations

from data_tool_mcp.tools.base import get_tool_config_class, list_tool_types


class TestMySQLTools:
    """MySQL tool registration and manifest tests."""

    def test_registration(self):
        """All 10 MySQL tools should be registered."""
        all_tools = list_tool_types()
        mysql_tools = [t for t in all_tools if t.startswith("mysql-")]
        assert "mysql-sql" in mysql_tools
        assert "mysql-execute-sql" in mysql_tools
        assert "mysql-list-tables" in mysql_tools
        assert "mysql-list-table-stats" in mysql_tools
        assert "mysql-list-active-queries" in mysql_tools
        assert "mysql-list-all-locks" in mysql_tools
        assert "mysql-list-table-fragmentation" in mysql_tools
        assert "mysql-list-tables-missing-unique-indexes" in mysql_tools
        assert "mysql-show-query-stats" in mysql_tools
        assert "mysql-get-query-plan" in mysql_tools
        assert len(mysql_tools) >= 10

    def test_mysql_sql_manifest(self):
        """mysql-sql should have a ToolConfig class."""
        cls = get_tool_config_class("mysql-sql")
        assert cls is not None

    def test_mysql_execute_sql_registered(self):
        """mysql-execute-sql should have a ToolConfig class."""
        cls = get_tool_config_class("mysql-execute-sql")
        assert cls is not None

    def test_mysql_list_tables_registered(self):
        """mysql-list-tables should have a ToolConfig class."""
        cls = get_tool_config_class("mysql-list-tables")
        assert cls is not None
