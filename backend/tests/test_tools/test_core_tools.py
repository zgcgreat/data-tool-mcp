"""Tests for MSSQL, SQLite, Redis, MongoDB, HTTP, Wait tools."""

from __future__ import annotations

from data_tool_mcp.tools.base import get_tool_config_class, list_tool_types


class TestMSSQLTools:
    """MSSQL tool registration tests."""

    def test_registration(self):
        all_tools = list_tool_types()
        assert "mssql-sql" in all_tools
        assert "mssql-execute-sql" in all_tools
        assert "mssql-list-tables" in all_tools

    def test_mssql_sql_class(self):
        cls = get_tool_config_class("mssql-sql")
        assert cls is not None


class TestSQLiteTools:
    """SQLite tool registration tests."""

    def test_registration(self):
        all_tools = list_tool_types()
        assert "sqlite-sql" in all_tools
        assert "sqlite-execute-sql" in all_tools

    def test_sqlite_sql_class(self):
        cls = get_tool_config_class("sqlite-sql")
        assert cls is not None


class TestRedisTools:
    """Redis tool registration tests."""

    def test_redis_registered(self):
        """Single 'redis' tool should be registered (Go style)."""
        all_tools = list_tool_types()
        assert "redis" in all_tools

    def test_redis_class(self):
        cls = get_tool_config_class("redis")
        assert cls is not None


class TestMongoDBTools:
    """MongoDB tool registration tests."""

    def test_all_mongodb_tools_registered(self):
        all_tools = list_tool_types()
        mongo_tools = [t for t in all_tools if t.startswith("mongodb-")]
        assert "mongodb-find" in mongo_tools
        assert "mongodb-find-one" in mongo_tools
        assert "mongodb-aggregate" in mongo_tools
        assert "mongodb-insert-one" in mongo_tools
        assert "mongodb-insert-many" in mongo_tools
        assert "mongodb-update-one" in mongo_tools
        assert "mongodb-update-many" in mongo_tools
        assert "mongodb-delete-one" in mongo_tools
        assert "mongodb-delete-many" in mongo_tools
        assert len(mongo_tools) >= 9

    def test_mongodb_find_class(self):
        cls = get_tool_config_class("mongodb-find")
        assert cls is not None


class TestHTTPTools:
    """HTTP tool registration tests."""

    def test_http_registered(self):
        """Single 'http' tool should be registered (Go style)."""
        all_tools = list_tool_types()
        assert "http" in all_tools

    def test_http_class(self):
        cls = get_tool_config_class("http")
        assert cls is not None


class TestWaitTools:
    """Wait tool registration tests."""

    def test_wait_registered(self):
        all_tools = list_tool_types()
        assert "wait" in all_tools

    def test_wait_class(self):
        cls = get_tool_config_class("wait")
        assert cls is not None


class TestCoreToolCount:
    """Verify core tool counts match Go version."""

    def test_postgres_tool_count(self):
        all_tools = list_tool_types()
        pg_tools = [t for t in all_tools if t.startswith("postgres-")]
        assert len(pg_tools) >= 22  # Go has 22+ PostgreSQL tools

    def test_mysql_tool_count(self):
        all_tools = list_tool_types()
        mysql_tools = [t for t in all_tools if t.startswith("mysql-")]
        assert len(mysql_tools) >= 10

    def test_mongodb_tool_count(self):
        all_tools = list_tool_types()
        mongo_tools = [t for t in all_tools if t.startswith("mongodb-")]
        assert len(mongo_tools) >= 9
