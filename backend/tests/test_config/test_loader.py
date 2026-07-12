"""Tests for configuration loading and ENV substitution."""

import os
from pathlib import Path

import pytest

from data_tool_mcp.config.loader import load_yaml_file, substitute_env_vars
from data_tool_mcp.config.models import ServerConfig


class TestEnvSubstitution:
    def test_simple_env(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "hello")
        assert substitute_env_vars("${TEST_VAR}") == "hello"

    def test_env_with_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert substitute_env_vars("${MISSING_VAR:-fallback}") == "fallback"

    def test_env_existing_ignores_default(self, monkeypatch):
        monkeypatch.setenv("EXISTING_VAR", "actual")
        assert substitute_env_vars("${EXISTING_VAR:-fallback}") == "actual"

    def test_nested_dict_substitution(self, monkeypatch):
        monkeypatch.setenv("DB_PASS", "secret123")
        result = substitute_env_vars({
            "host": "localhost",
            "password": "${DB_PASS}",
            "nested": {"key": "${DB_PASS}"},
        })
        assert result["password"] == "secret123"
        assert result["nested"]["key"] == "secret123"

    def test_list_substitution(self, monkeypatch):
        monkeypatch.setenv("ITEM", "value1")
        result = substitute_env_vars(["${ITEM}", "static"])
        assert result == ["value1", "static"]

    def test_missing_env_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ValueError, match="MISSING_VAR"):
            substitute_env_vars("${MISSING_VAR}")


class TestServerConfig:
    def test_defaults(self):
        config = ServerConfig()
        assert config.port == 5000
        assert config.address == "0.0.0.0"
        assert config.log_level == "INFO"
        assert config.stdio is False

    def test_custom_values(self):
        config = ServerConfig(port=8080, address="127.0.0.1", stdio=True)
        assert config.port == 8080
        assert config.address == "127.0.0.1"
        assert config.stdio is True
