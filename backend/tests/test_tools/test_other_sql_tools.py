"""Tests for GenericSQLTool family — yaml statement/parameters/templateParameters modes.

Covers GenericSQLTool, GenericExecuteSQLTool and _OtherSQLToolConfig.from_dict behavior,
including the four execution modes:
  1. statement + templateParameters → render_sql_template
  2. statement + parameters         → execute with named bind params (with default fallback)
  3. statement only                 → execute fixed SQL directly
  4. no statement (kind=sql/exec)   → user provides 'sql' param

Uses asyncio.run() rather than pytest-asyncio to stay consistent with the project's
other sync-only test files (test_pg_tools.py / test_mysql_tools.py).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import data_tool_mcp.tools.other_sql_tools  # noqa: F401  trigger registration
from data_tool_mcp.sources.base import SQLSource
from data_tool_mcp.tools.base import (
    ConfigBase,
    _bind_param_values,
    get_tool_config_class,
    list_tool_types,
)
from data_tool_mcp.tools.other_sql_tools import (
    GenericExecuteSQLTool,
    GenericListQueryTool,
    GenericListTablesTool,
    GenericSQLTool,
)
from data_tool_mcp.tools.template import render_sql_template


class _FakeSQLSource(SQLSource):
    """记录传入的 (sql, params) 以便断言的 fake source。

    继承 SQLSource 以通过 _get_typed_source_async 的 isinstance 校验,
    抽象方法 list_tables/describe_table 在本测试中不会被调用,给 no-op 即可。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    @property
    def source_type(self) -> str:
        return "fake-sql"

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def execute_sql(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((sql, params))
        return [{"col": 1}]

    async def list_tables(self) -> list[str]:
        return []

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        return []


class _FakeSourceProvider:
    """直接返回预置 source 的 provider,release_source 为 no-op。"""

    def __init__(self, source: _FakeSQLSource) -> None:
        self._source = source

    async def get_source(self, name: str):
        return self._source

    async def release_source(self, name: str) -> None:
        return None


def _run(coro):
    """同步运行 async 协程,避免依赖 pytest-asyncio。"""
    return asyncio.run(coro)


class TestOtherSQLRegistration:
    """工具类型注册校验。"""

    def test_oracle_gaussdb_clickhouse_registered(self):
        """oracle/gaussdb/clickhouse/yugabyte/cockroach 等专用类型应注册。"""
        all_tools = list_tool_types()
        assert "oracle-sql" in all_tools
        assert "oracle-execute-sql" in all_tools
        assert "gaussdb-sql" in all_tools
        assert "gaussdb-execute-sql" in all_tools
        assert "clickhouse-sql" in all_tools
        assert "clickhouse-execute-sql" in all_tools
        assert "yugabytedb-sql" in all_tools
        assert "cockroachdb-sql" in all_tools
        assert "cockroachdb-execute-sql" in all_tools
        assert "mindsdb-sql" in all_tools


class TestOtherSQLConfigFromDict:
    """_OtherSQLToolConfig.from_dict 应解析 yaml statement/parameters/templateParameters 字段。"""

    def test_oracle_sql_parses_statement_and_parameters(self):
        """oracle-sql 应解析 statement + parameters 字段。"""
        cls = get_tool_config_class("oracle-sql")
        cfg = cls.from_dict(
            "list_tables",
            {
                "source": "oracle-source",
                "description": "test",
                "statement": "SELECT * FROM user_tables WHERE table_name = :table_name",
                "parameters": [
                    {"name": "table_name", "type": "string", "description": "table name"}
                ],
            },
        )
        assert cfg.source == "oracle-source"
        assert "SELECT * FROM user_tables" in cfg.statement
        assert len(cfg.parameters) == 1
        assert cfg.parameters[0]["name"] == "table_name"
        assert cfg.template_parameters == []

    def test_gaussdb_sql_parses_template_parameters(self):
        """gaussdb-sql 应解析 templateParameters 字段。"""
        cls = get_tool_config_class("gaussdb-sql")
        cfg = cls.from_dict(
            "explain",
            {
                "source": "gaussdb-source",
                "statement": "EXPLAIN {{.query}};",
                "templateParameters": [
                    {"name": "query", "type": "string", "required": True}
                ],
            },
        )
        assert cfg.statement == "EXPLAIN {{.query}};"
        assert len(cfg.template_parameters) == 1
        assert cfg.template_parameters[0]["name"] == "query"
        assert cfg.parameters == []

    def test_clickhouse_sql_no_statement_defaults_to_empty(self):
        """clickhouse-sql 无 statement 时各字段应为空列表/空字符串。"""
        cls = get_tool_config_class("clickhouse-sql")
        cfg = cls.from_dict("execute_sql", {"source": "ch-source"})
        assert cfg.statement == ""
        assert cfg.parameters == []
        assert cfg.template_parameters == []


class TestBindParamValues:
    """_bind_param_values 应返回命名绑定 dict 并正确回填 default。"""

    def test_returns_dict_with_named_bindings(self):
        """用户传参时应直接取用户值。"""
        parameters = [
            {"name": "metric", "type": "string"},
            {"name": "limit", "type": "integer"},
        ]
        result = _bind_param_values(parameters, {"metric": "CPU_TIME", "limit": 10})
        assert result == {"metric": "CPU_TIME", "limit": 10}

    def test_fills_default_when_user_omits(self):
        """yaml default 字段应在用户未提供时回填。"""
        parameters = [
            {"name": "metric", "type": "string", "default": "elapsed_time"},
            {"name": "limit", "type": "integer", "default": 5},
        ]
        result = _bind_param_values(parameters, {})
        assert result == {"metric": "elapsed_time", "limit": 5}

    def test_user_value_overrides_default(self):
        """用户传值应覆盖 yaml default。"""
        parameters = [
            {"name": "metric", "type": "string", "default": "elapsed_time"},
        ]
        result = _bind_param_values(parameters, {"metric": "cpu_time"})
        assert result == {"metric": "cpu_time"}

    def test_returns_none_when_no_default_no_user_value(self):
        """无 default 且用户未传时返回 None(对应 SQL NULL)。"""
        parameters = [{"name": "table_name", "type": "string"}]
        result = _bind_param_values(parameters, {})
        assert result == {"table_name": None}


class TestGenericSQLToolModes:
    """GenericSQLTool 的四种执行模式。"""

    def _make_tool(
        self,
        statement: str = "",
        template_parameters: list[dict[str, Any]] | None = None,
        parameters: list[dict[str, Any]] | None = None,
    ) -> GenericSQLTool:
        cfg = ConfigBase(name="test-tool", description="test")
        return GenericSQLTool(
            cfg=cfg,
            source_name="test-source",
            statement=statement,
            template_parameters=template_parameters or [],
            parameters=parameters or [],
        )

    def test_mode_template_parameters_renders_template(self):
        """statement + templateParameters 应使用 render_sql_template 内联渲染。"""
        tool = self._make_tool(
            statement="EXPLAIN {{.query}};",
            template_parameters=[{"name": "query", "type": "string"}],
        )
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        result = _run(tool.invoke({"query": "SELECT 1"}, source_provider=provider))

        assert result == {"rows": [{"col": 1}], "rowCount": 1}
        assert len(fake.calls) == 1
        sql, params = fake.calls[0]
        assert sql == "EXPLAIN SELECT 1;"
        assert params is None

    def test_mode_parameters_uses_named_bindings(self):
        """statement + parameters 应通过 source.execute_sql(sql, dict) 命名绑定。"""
        tool = self._make_tool(
            statement="SELECT * FROM t WHERE id = :id AND status = :status",
            parameters=[
                {"name": "id", "type": "integer"},
                {"name": "status", "type": "string", "default": "active"},
            ],
        )
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        _run(tool.invoke({"id": 42}, source_provider=provider))

        sql, params = fake.calls[0]
        assert sql == "SELECT * FROM t WHERE id = :id AND status = :status"
        assert params == {"id": 42, "status": "active"}

    def test_mode_statement_only_executes_fixed_sql(self):
        """statement only 应直接执行固定 SQL,无参数。"""
        tool = self._make_tool(statement="SELECT 1")
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        _run(tool.invoke({}, source_provider=provider))

        sql, params = fake.calls[0]
        assert sql == "SELECT 1"
        assert params is None

    def test_mode_no_statement_uses_user_sql_param(self):
        """无 statement 时应使用 params['sql']。"""
        tool = self._make_tool()
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        _run(tool.invoke({"sql": "SELECT NOW()"}, source_provider=provider))

        sql, params = fake.calls[0]
        assert sql == "SELECT NOW()"
        assert params is None

    def test_mode_no_statement_missing_sql_raises(self):
        """无 statement 且用户未传 sql 时应报错。"""
        tool = self._make_tool()
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        with pytest.raises(ValueError, match="missing 'sql'"):
            _run(tool.invoke({}, source_provider=provider))


class TestGenericExecuteSQLTool:
    """GenericExecuteSQLTool 与 GenericSQLTool 行为对齐(仅 annotations 不同)。"""

    def test_template_mode_works(self):
        """GenericExecuteSQLTool 也支持 templateParameters 模式。"""
        cfg = ConfigBase(name="exec-tool", description="exec")
        tool = GenericExecuteSQLTool(
            cfg=cfg,
            source_name="test-source",
            statement="INSERT INTO t VALUES ({{.value}})",
            template_parameters=[{"name": "value", "type": "integer"}],
        )
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        result = _run(tool.invoke({"value": 42}, source_provider=provider))

        sql, _ = fake.calls[0]
        assert sql == "INSERT INTO t VALUES (42)"
        assert result == {"rows": [{"col": 1}], "rowCount": 1}


class TestGenericSQLToolManifest:
    """GenericSQLTool.manifest 应根据模式生成正确参数定义。"""

    def test_manifest_no_statement_has_sql_param(self):
        """无 statement 时 manifest 应包含 sql 参数。"""
        cfg = ConfigBase(name="t", description="t")
        tool = GenericSQLTool(cfg=cfg, source_name="s")
        m = tool.manifest()
        param_names = [p.name for p in m.parameters]
        assert "sql" in param_names

    def test_manifest_with_parameters_lists_user_params(self):
        """有 parameters 时 manifest 应列出 yaml 定义的参数。"""
        cfg = ConfigBase(name="t", description="t")
        tool = GenericSQLTool(
            cfg=cfg,
            source_name="s",
            statement="SELECT * FROM t WHERE id = :id",
            parameters=[{"name": "id", "type": "integer", "description": "id"}],
        )
        m = tool.manifest()
        param_names = [p.name for p in m.parameters]
        assert param_names == ["id"]
        assert "sql" not in param_names

    def test_manifest_with_template_parameters_lists_user_params(self):
        """有 templateParameters 时 manifest 应列出 yaml 定义的参数。"""
        cfg = ConfigBase(name="t", description="t")
        tool = GenericSQLTool(
            cfg=cfg,
            source_name="s",
            statement="EXPLAIN {{.query}}",
            template_parameters=[{"name": "query", "type": "string"}],
        )
        m = tool.manifest()
        param_names = [p.name for p in m.parameters]
        assert param_names == ["query"]


class TestListTablesAndQueryKinds:
    """list-tables / list-query kind 仍使用内置 SQL,不接受 yaml 注入。"""

    def test_list_tables_uses_builtin_sql(self):
        """list-tables kind 应使用 extra 中的内置 SQL。"""
        cfg = ConfigBase(name="t", description="t")
        tool = GenericListTablesTool(cfg=cfg, source_name="s", sql="SELECT table_name FROM t")
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        _run(tool.invoke({}, source_provider=provider))

        sql, _ = fake.calls[0]
        assert sql == "SELECT table_name FROM t"

    def test_list_query_uses_builtin_sql(self):
        """list-query kind 应使用 extra 中的内置 SQL。"""
        cfg = ConfigBase(name="t", description="t")
        tool = GenericListQueryTool(
            cfg=cfg, source_name="s", sql="SELECT * FROM processlist"
        )
        fake = _FakeSQLSource()
        provider = _FakeSourceProvider(fake)

        _run(tool.invoke({}, source_provider=provider))

        sql, _ = fake.calls[0]
        assert sql == "SELECT * FROM processlist"


class TestTemplateRenderingIntegration:
    """模板渲染端到端验证(模拟 Oracle get_query_plan 的 SQL)。"""

    def test_oracle_explain_plan_renders_correctly(self):
        """Oracle get_query_plan 的 EXPLAIN PLAN 应正确渲染用户 SQL。"""
        template = "EXPLAIN PLAN FOR {{.query}};\nSELECT * FROM TABLE(DBMS_XPLAN.DISPLAY());\n"
        rendered = render_sql_template(template, {"query": "select * from auth_group;"})
        assert "EXPLAIN PLAN FOR select * from auth_group;" in rendered
        assert "DBMS_XPLAN.DISPLAY()" in rendered

    def test_sql_injection_defense_via_escape(self):
        """模板渲染应转义单引号防注入。"""
        rendered = render_sql_template(
            "EXPLAIN {{.query}}", {"query": "SELECT ' OR '1'='1"}
        )
        # 单引号被转义为两个连续单引号,避免破坏 SQL 字符串字面量
        assert "SELECT '' OR ''1''=''1" in rendered
