"""SQL 查询 / 表列表辅助函数。

从 admin/router.py 拆分而来,集中处理:
  - /query 路由的入参校验、SQL 执行计时、响应构造
  - /sources/{name}/tables 路由的方言 SQL 选择、表名提取
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from data_tool_mcp.admin._constants import DEFAULT_TABLES_SQL, DIALECT_TABLES_SQL


# ---------------------------------------------------------------------------
# execute_query 辅助函数
# ---------------------------------------------------------------------------


def _validate_query_input(source_name: str, statement: str) -> None:
    """校验查询接口入参:sourceName 和 statement 均必填。"""
    if not source_name or not statement:
        raise HTTPException(status_code=400, detail="sourceName and statement are required")


def _validate_source_sql_support(source, source_name: str) -> None:
    """校验数据源是否支持 SQL 查询。"""
    if not hasattr(source, "execute_sql"):
        raise HTTPException(
            status_code=400, detail=f"source {source_name!r} does not support SQL queries"
        )


async def _execute_sql_with_timing(source, statement: str) -> tuple[list[dict[str, Any]], int]:
    """执行 SQL 并返回 (rows, duration_ms)。"""
    import time

    start = time.monotonic()
    rows = await source.execute_sql(statement)
    duration_ms = int((time.monotonic() - start) * 1000)
    return rows, duration_ms


def _build_sql_query_response(rows: list[dict[str, Any]], duration_ms: int) -> dict[str, Any]:
    """构造 SQL 查询响应 dict。"""
    columns = list(rows[0].keys()) if rows else []
    return {
        "columns": columns,
        "rows": [list(r.values()) for r in rows],
        "rowCount": len(rows),
        "durationMs": duration_ms,
    }


async def _run_sql_query(source, statement: str) -> dict[str, Any]:
    """执行 SQL 查询并返回 columns/rows/rowCount/durationMs。"""
    try:
        rows, duration_ms = await _execute_sql_with_timing(source, statement)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _build_sql_query_response(rows, duration_ms)


# ---------------------------------------------------------------------------
# list_source_tables 辅助函数
# ---------------------------------------------------------------------------


def _get_dialect_tables_sql(src_type: str) -> str:
    """根据数据源类型返回对应的表元数据查询 SQL。"""
    return DIALECT_TABLES_SQL.get(src_type, DEFAULT_TABLES_SQL)


def _extract_single_table_name(row: dict[str, Any]) -> Any:
    """从单行查询结果中提取表名。"""
    return row.get("name") or row.get("tablename") or list(row.values())[0]


def _filter_non_empty(items: list) -> list:
    """过滤掉列表中的 falsy 值。"""
    return [t for t in items if t]


def _extract_table_names(rows: list[dict[str, Any]]) -> list[str]:
    """从查询结果中提取表名列表。"""
    tables = [_extract_single_table_name(r) for r in rows]
    return _filter_non_empty(tables)


async def _query_source_tables(source) -> dict[str, Any]:
    """查询数据源中的表列表。"""
    # Detect dialect for the right metadata query
    src_type = getattr(source, "source_type", "")
    sql = _get_dialect_tables_sql(src_type)
    try:
        rows = await source.execute_sql(sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"tables": _extract_table_names(rows)}
