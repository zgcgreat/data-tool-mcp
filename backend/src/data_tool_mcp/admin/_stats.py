"""仪表盘 / 健康 / MCP 测试 / 统计辅助函数。

从 admin/router.py 拆分而来,集中处理:
  - /dashboard 计数查询 (今日请求数 + 数据源/工具计数)
  - /health 数据源名列表加载与健康状态项构造
  - /mcp-test toolset 解析、存在性校验、响应构造
  - /mcp-stats /mcp-logs 日期范围解析、空响应构造
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from data_tool_mcp.admin._common import (
    extract_env_keys,
    extract_source_names,
    is_store_usable,
    logger,
)


# ---------------------------------------------------------------------------
# dashboard / health 辅助函数
# ---------------------------------------------------------------------------


async def _query_today_requests_from_store(store) -> int:
    """从 store 查询今日 MCP 请求数,失败返回 0。"""
    if not is_store_usable(store):
        return 0
    try:
        from datetime import date

        today_str = date.today().isoformat()
        stats = await store.query_mcp_stats(start_date=today_str, end_date=today_str)
        return stats.get("summary", {}).get("total", 0)
    except Exception as exc:
        logger.warning("查询今日 MCP 请求数失败: %s", exc)
        return 0


async def _query_dashboard_counts(store, rm) -> tuple[int, int]:
    """查询 dashboard 所需的 source/tool 计数。"""
    if not is_store_usable(store):
        return len(rm.get_all_source_configs()), len(rm.get_tools_map())
    try:
        return await store.count_sources(), await store.count_tools()
    except Exception as exc:
        logger.warning("查询 dashboard 计数失败: %s", exc)
        return len(rm.get_all_source_configs()), len(rm.get_tools_map())


def _get_rm_source_names(rm) -> list[str]:
    """从 rm 内存中获取数据源名列表。"""
    return list(rm.get_all_source_configs().keys())


async def _load_source_names(rm, store) -> list[str]:
    """加载数据源名列表,优先用 store,回退到 rm。"""
    if not is_store_usable(store):
        return _get_rm_source_names(rm)
    try:
        sources_list = await store.load_sources()
        return extract_source_names(sources_list)
    except Exception as exc:
        logger.warning("查询 health 数据源列表失败: %s", exc)
        return _get_rm_source_names(rm)


def _build_source_health_item(name: str) -> dict[str, Any]:
    """构造 health 接口中单个数据源的健康状态项。"""
    return {
        "name": name,
        "status": "unknown",
        "latency": None,
        "lastError": None,
    }


# ---------------------------------------------------------------------------
# mcp_test 辅助函数
# ---------------------------------------------------------------------------


def _resolve_toolset_from_env(system_id: str, environment: str) -> str:
    """根据系统编号和环境推导 toolset 名称。"""
    if system_id and environment:
        return f"{system_id}-{environment}"
    return system_id


def _resolve_effective_toolset(toolset_name: str, system_id: str, environment: str) -> str:
    """确定最终用于过滤的 toolset 名称。"""
    if toolset_name:
        return toolset_name
    return _resolve_toolset_from_env(system_id, environment)


def _validate_toolset_exists(rm, effective_toolset: str) -> None:
    """如果指定了 toolset,校验其是否存在,不存在抛 404。"""
    if not effective_toolset:
        return
    toolset = rm.get_toolset(effective_toolset)
    if toolset is None:
        raise HTTPException(status_code=404, detail=f"toolset {effective_toolset!r} not found")


def _parse_mcp_test_input(body: dict[str, Any]) -> tuple[str, str, str]:
    """从 mcp_test 请求 body 中解析 (toolset_name, system_id, environment)。"""
    toolset_name = body.get("toolset", "") or ""
    system_id, environment = extract_env_keys(body)
    return toolset_name, system_id, environment


def _build_mcp_test_response(result: dict[str, Any]) -> dict[str, Any]:
    """构造 mcp_test 接口响应。"""
    tools = result.get("tools", [])
    return {
        "ok": True,
        "count": len(tools),
        "tools": [{"name": t["name"], "description": t.get("description", "")} for t in tools],
    }


# ---------------------------------------------------------------------------
# mcp_stats / mcp_logs 辅助函数
# ---------------------------------------------------------------------------


def _get_default_date_range() -> tuple[str, str]:
    """返回默认日期范围 (start_date, end_date): 今天往前 29 天 ~ 今天。"""
    from datetime import date, timedelta

    today = date.today()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")
    return start_date, end_date


def _fill_default_dates(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    """用默认值填充缺失的日期。"""
    default_start, default_end = _get_default_date_range()
    return start_date or default_start, end_date or default_end


def _resolve_date_range(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    """解析日期范围,缺省时使用默认值。"""
    if start_date and end_date:
        return start_date, end_date
    return _fill_default_dates(start_date, end_date)


def _build_no_persistence_stats_response() -> dict[str, Any]:
    """未启用持久化时返回的 mcp_stats 空响应。"""
    return {
        "summary": {"total": 0, "success": 0, "fail": 0, "avg_latency_ms": 0},
        "by_system": [],
        "by_source": [],
        "by_tool": [],
        "timeline": [],
        "note": "未启用持久化存储，无法统计 MCP 请求",
    }


def _build_no_persistence_logs_response(page: int, page_size: int) -> dict[str, Any]:
    """未启用持久化时返回的 mcp_logs 空响应。"""
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_pages": 1,
        "note": "未启用持久化存储，无法查询 MCP 请求记录",
    }
