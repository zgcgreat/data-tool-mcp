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


async def _query_today_requests_from_store(store) -> int | None:
    """从 store 查询今日 MCP 请求数。

    返回值语义:
      - int: store 查询成功(包括 0,表示今日确无请求)
      - None: store 不可用或查询失败,调用方应回退到内存计数器
    """
    if not is_store_usable(store):
        return None
    try:
        from datetime import date

        today_str = date.today().isoformat()
        stats = await store.query_mcp_stats(start_date=today_str, end_date=today_str)
        return stats.get("summary", {}).get("total", 0)
    except Exception as exc:
        logger.warning("查询今日 MCP 请求数失败: %s", exc)
        return None


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
    """构造 health 接口中单个数据源的健康状态项(默认 unknown,实际状态由 _check_source_health 填充)。"""
    return {
        "name": name,
        "status": "unknown",
        "latency": None,
        "lastError": None,
    }


async def _check_source_health(rm, store, name: str, timeout: float = 5.0) -> dict[str, Any]:
    """对单个数据源执行健康检测,返回带真实 status/latency/lastError 的健康项。

    流程:
      1. 通过 _get_source_for_action 获取 source 实例(多实例一致性: store 优先 + 惰性加载)
      2. 调用 source.connect()(SQL 源执行 SELECT 1,GCP 源为 no-op)测量延迟
      3. 一定超时内未完成视为不可达
      4. 无论成功失败都 release_source,避免引用计数泄漏

    返回字段:
      - status: "healthy" | "unhealthy" | "unknown"(获取 source 失败且非连接问题)
      - latency: 毫秒(失败时为 None)
      - lastError: 错误消息(成功时为 None)
    """
    import asyncio

    from data_tool_mcp.admin._sources import _get_source_for_action, _measure_source_connect_latency

    item = _build_source_health_item(name)
    # 获取 source 实例(失败说明配置缺失或初始化失败,标记为 unknown)
    try:
        source = await _get_source_for_action(rm, store, name)
    except Exception as exc:
        item["status"] = "unknown"
        item["lastError"] = f"acquire source failed: {exc}"
        return item
    if source is None:
        item["status"] = "unknown"
        item["lastError"] = "source not found in store or rm"
        return item
    # 测量连接延迟(带超时,防止单个慢源阻塞整个 /health 响应)
    try:
        result = await asyncio.wait_for(
            _measure_source_connect_latency(source), timeout=timeout
        )
        if result.get("ok"):
            item["status"] = "healthy"
            item["latency"] = result.get("latency")
            item["lastError"] = None
        else:
            item["status"] = "unhealthy"
            item["latency"] = None
            item["lastError"] = result.get("error")
    except asyncio.TimeoutError:
        item["status"] = "unhealthy"
        item["latency"] = None
        item["lastError"] = f"health check timed out after {timeout}s"
    except Exception as exc:
        item["status"] = "unhealthy"
        item["latency"] = None
        item["lastError"] = str(exc)
    finally:
        try:
            await rm.release_source(name)
        except Exception:
            # release 失败不影响健康检测结果
            pass
    return item


async def _build_source_health_list(rm, store, names: list[str]) -> list[dict[str, Any]]:
    """并发检测多个数据源的健康状态(控制并发度避免瞬时连接风暴)。"""
    import asyncio

    if not names:
        return []
    # 并发检测,但限制最大并发数避免一次打开太多连接
    semaphore = asyncio.Semaphore(min(10, len(names)))

    async def _check_with_limit(name: str) -> dict[str, Any]:
        async with semaphore:
            return await _check_source_health(rm, store, name)

    return await asyncio.gather(*[_check_with_limit(n) for n in names])


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


async def _validate_toolset_exists(rm, store, effective_toolset: str) -> None:
    """如果指定了 toolset,校验其是否存在,不存在抛 404。

    store 优先 / rm 回退:多实例一致性保证。
    创建数据源后,即便本实例 rm 内存尚未热重载,也能从 store 立即查到(0 延迟)。

    toolsets 表已移除:store 校验通过动态聚合 tools 表实现(5 种 toolset 类型)。
    """
    if not effective_toolset:
        return
    # store 优先:从 tools 表动态聚合判断
    if is_store_usable(store):
        try:
            exists = await _check_toolset_exists_in_store(store, effective_toolset)
            if exists:
                return
            # store 确认不存在,直接 404(store 是事实源,无需回退 rm)
            raise HTTPException(
                status_code=404,
                detail=f"toolset {effective_toolset!r} not found",
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "store 查询 toolset %r 失败,回退 rm: %s", effective_toolset, exc
            )
    # rm 回退:单机模式或 store 异常
    toolset = rm.get_toolset(effective_toolset)
    if toolset is None:
        raise HTTPException(
            status_code=404, detail=f"toolset {effective_toolset!r} not found"
        )


async def _check_toolset_exists_in_store(store, name: str) -> bool:
    """从 tools 表动态聚合判断 toolset 是否存在(5 种类型)。

    - all: 任意工具存在即返回 True(空 store 视为存在,由调用方决定)
    - source: 存在 source_name == name 的工具
    - system: 存在 system_id == name 的工具
    - system-env: 存在 {system_id}-{environment} == name 的工具
    - custom: 存在 toolsetNames 包含 name 的工具
    """
    tools_list = await store.load_tools()
    for t in tools_list:
        # source toolset
        if t.get("source", "") == name:
            return True
        # system toolset
        sid = str(t.get("systemId", "") or "").strip()
        if sid and sid == name:
            return True
        # system-env toolset
        env = str(t.get("environment", "") or "").strip()
        if sid and env and f"{sid}-{env}" == name:
            return True
        # custom toolset
        ts_names = t.get("toolsetNames") or []
        if isinstance(ts_names, list) and name in ts_names:
            return True
    return False


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
