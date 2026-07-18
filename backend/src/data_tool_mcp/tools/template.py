"""Minimal Go text/template renderer.

Supports the subset of Go's text/template used by prebuilt tool
``statement`` templates:

  * ``{{.Name}}``            -- variable substitution
  * ``{{if .Name}}...{{end}}`` -- conditional block (truthy when non-empty)

This is intentionally small; it covers the patterns found in the
shipped prebuilt configs (e.g. sqlite ``list_tables``).

Maps to Go: internal/util/templating (text/template)
"""

from __future__ import annotations

import re
from typing import Any


_VAR_RE = re.compile(r"\{\{\s*\.(\w+)\s*\}\}")
_IF_RE = re.compile(r"\{\{if\s+\.(\w+)\s*\}\}(.*?)\{\{end\}\}", re.DOTALL)


_TRUTHY_CHECKERS: list[tuple[tuple[type, ...], Any]] = [
    ((type(None),), lambda v: False),
    ((str,), lambda v: v.strip() != ""),
    ((int, float, bool), lambda v: bool(v)),
    ((list, dict, tuple, set), lambda v: len(v) > 0),
]


def _is_truthy(value: Any) -> bool:
    """判断值是否为真。"""
    for types, checker in _TRUTHY_CHECKERS:
        if isinstance(value, types):
            return checker(value)
    return bool(value)


def _sql_escape(value: Any) -> str:
    """Escape a value for safe interpolation into a SQL string literal.

    This is a *defensive fallback* — the primary SQL injection defense is
    parameterized queries. But MCP tool templates use Go-style
    ``{{.Param}}`` substitution which renders values directly into the SQL
    text, so we escape single quotes (and backslashes for MySQL-style
    dialects) to prevent breaking out of string literals.

    Maps to Go: internal/tools/sql utility escape functions.
    """
    if value is None:
        return ""
    # Render the value to string first
    s = str(value)
    # Escape backslash and single quote — the two characters that can
    # break out of a SQL string literal across major dialects
    # (PostgreSQL, MySQL, SQLite, MSSQL).
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "''")
    return s


def render_template(template: str, params: dict[str, Any]) -> str:
    """Render a ``statement`` template with the given parameters."""
    scope = params

    def _if_repl(match: re.Match) -> str:
        """替换模板中的 if 块。"""
        name = match.group(1)
        body = match.group(2)
        return body if _is_truthy(scope.get(name)) else ""

    # Resolve nested if-blocks first (iterate until stable).
    prev = None
    curr = template
    while prev != curr:
        prev = curr
        curr = _IF_RE.sub(_if_repl, curr)

    # Then substitute variables.
    # Use explicit None check instead of `or ""` to preserve falsy values
    # like 0, False, and empty list — Go's text/template renders these as
    # "0"/"false"/"" respectively, not as empty string.
    def _var_repl(m: re.Match) -> str:
        """替换模板中的变量占位符。"""
        val = scope.get(m.group(1), "")
        return "" if val is None else str(val)

    return _VAR_RE.sub(_var_repl, curr)


def render_sql_template(template: str, params: dict[str, Any]) -> str:
    """Render a SQL ``statement`` template with SQL-escaped parameters.

    Like :func:`render_template` but applies SQL string-literal escaping
    to all substituted values. This is a defensive fallback for the Go-style
    template approach where parameters are interpolated directly into SQL
    text rather than passed as bound parameters.

    Use this instead of ``render_template`` when the template output will
    be executed as a SQL statement (e.g., tool ``statement`` fields).
    """
    scope = params

    def _if_repl(match: re.Match) -> str:
        """替换模板中的 if 块。"""
        name = match.group(1)
        body = match.group(2)
        return body if _is_truthy(scope.get(name)) else ""

    # Resolve nested if-blocks first (iterate until stable).
    prev = None
    curr = template
    while prev != curr:
        prev = curr
        curr = _IF_RE.sub(_if_repl, curr)

    # Then substitute variables with SQL escaping.
    def _var_repl(m: re.Match) -> str:
        """替换模板中的变量占位符。"""
        val = scope.get(m.group(1), "")
        return _sql_escape(val)

    return _VAR_RE.sub(_var_repl, curr)
