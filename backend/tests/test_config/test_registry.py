"""Tests for source and tool registry."""

from __future__ import annotations

import pytest

from data_tool_mcp.sources.base import (
    _source_registry,
    _source_aliases,
    list_source_types,
    register_source,
    get_source_config_class,
)
from data_tool_mcp.tools.base import (
    _tool_registry,
    list_tool_types,
)


class TestSourceRegistry:
    def test_postgres_registered(self):
        """postgres source should be registered as primary name."""
        assert "postgres" in _source_registry

    def test_postgresql_alias(self):
        """postgresql should exist as an alias for backward compat."""
        assert "postgresql" in _source_aliases or "postgresql" in _source_registry

    def test_mysql_registered(self):
        assert "mysql" in _source_registry

    def test_redis_registered(self):
        assert "redis" in _source_registry

    def test_sqlite_registered(self):
        assert "sqlite" in _source_registry

    def test_mongodb_registered(self):
        assert "mongodb" in _source_registry

    def test_list_source_types(self):
        types = list_source_types()
        assert "postgres" in types
        assert "mysql" in types
        assert len(types) >= 45

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="unknown source type"):
            get_source_config_class("nonexistent")

    def test_duplicate_registration_raises(self):
        """Registering a duplicate should still raise ValueError."""
        with pytest.raises(ValueError, match="already registered"):

            @register_source("postgres")
            class DuplicateSource:
                pass


class TestToolRegistry:
    def test_postgres_tools_registered(self):
        """Core PostgreSQL tools should be registered with Go-compatible names."""
        assert "postgres-sql" in _tool_registry
        assert "postgres-execute-sql" in _tool_registry
        assert "postgres-list-tables" in _tool_registry

    def test_redis_tool_registered(self):
        """Single 'redis' tool should be registered (Go style)."""
        assert "redis" in _tool_registry

    def test_mongodb_tools_registered(self):
        """MongoDB tools should use 'mongodb-' prefix (Go style)."""
        assert "mongodb-find" in _tool_registry
        assert "mongodb-aggregate" in _tool_registry

    def test_http_tool_registered(self):
        """HTTP tool should be registered as 'http' (Go style)."""
        assert "http" in _tool_registry

    def test_list_tool_types_includes_aliases(self):
        """list_tool_types() should include both primary and alias names."""
        types = list_tool_types()
        # Core tool names
        assert "postgres-sql" in types
        assert "redis" in types
        assert "http" in types
        assert "mongodb-find" in types
        assert "wait" in types
        assert len(types) >= 260
