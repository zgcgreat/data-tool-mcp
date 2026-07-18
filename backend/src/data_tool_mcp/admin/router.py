"""Admin UI 后端路由处理器。

仅保留 FastAPI 路由定义,所有业务逻辑辅助函数已拆分到:
  - _constants.py    静态数据与常量
  - _common.py       共享小型辅助 (logger / request helper / store check)
  - _sources.py      数据源 CRUD / 持久化 / 校验 / 响应构造
  - _tools.py        工具 / 工具集 / 系统聚合
  - _query.py        SQL 查询 / 表列表
  - _stats.py        仪表盘 / 健康 / MCP 测试 / 统计

外部入口: `router` (APIRouter prefix="/mcp-api")
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from data_tool_mcp.admin._common import (
    get_config,
    get_rm,
    get_source_env_keys_from_cfg,
    is_store_usable,
    logger,
)
from data_tool_mcp.admin._constants import ENVIRONMENTS
from data_tool_mcp.admin._query import (
    _query_source_tables,
    _run_sql_query,
    _validate_query_input,
    _validate_source_sql_support,
)
from data_tool_mcp.admin._sources import (
    _auto_create_tools,
    _build_config_data,
    _build_source_or_raise,
    _build_source_response,
    _build_sources_response_from_rm,
    _build_sources_response_from_rm_filtered,
    _build_sources_response_from_store_list,
    _check_source_exists,
    _check_source_uniqueness,
    _delete_old_source_record,
    _filter_schemas_by_whitelist,
    _get_password_ciphertext,
    _get_source_config_or_empty,
    _get_tools_for_source,
    _load_all_source_configs,
    _load_source_config,
    _measure_source_connect_latency,
    _normalize_sqlite_config,
    _persist_delete_source,
    _persist_new_source,
    _persist_source,
    _remove_source_tools,
    _remove_tools_for_update,
    _source_to_dict,
    _validate_create_source_input,
    _validate_name_param,
    _validate_update_source_input,
)
from data_tool_mcp.admin._stats import (
    _build_mcp_test_response,
    _build_no_persistence_logs_response,
    _build_no_persistence_stats_response,
    _build_source_health_item,
    _load_source_names,
    _parse_mcp_test_input,
    _query_dashboard_counts,
    _query_today_requests_from_store,
    _resolve_date_range,
    _resolve_effective_toolset,
    _validate_toolset_exists,
)
from data_tool_mcp.admin._tools import (
    _aggregate_systems,
    _build_tool_detail,
    _build_tool_list_item,
    _build_toolsets_from_rm,
    _build_toolsets_from_store,
    _invoke_tool_safe,
)
from data_tool_mcp.config.store import get_store

router = APIRouter(prefix="/mcp-api", tags=["Admin"])


# ===========================================================================
# 路由处理器
# ===========================================================================


@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    """返回 dashboard 概览数据(版本、计数、今日请求数等)。"""
    rm = get_rm(request)
    config = get_config(request)
    store = get_store()
    # 今日请求数 — 优先从数据库 mcp_request_logs 表查询（持久化，重启不丢）
    # 回退到内存计数器（未启用持久化时）
    today_requests = await _query_today_requests_from_store(store)
    if today_requests == 0:
        from data_tool_mcp.server.stats import get_request_counter

        today_requests = get_request_counter().get_today_count()
    # 数据源/工具计数 — 优先从数据库查询（多实例一致性），回退到 rm 内存
    source_count, tool_count = await _query_dashboard_counts(store, rm)
    return {
        "version": getattr(config, "version", "0.1.0"),
        "uptime": None,
        "sourceCount": source_count,
        "sourceOnline": source_count,
        "toolCount": tool_count,
        "todayRequests": today_requests,
        "sourceHealth": [],
        "recentErrors": [],
        # MCP 服务实际监听端口 — 前端据此构造 MCP 端点 URL,
        # 避免误用前端/nginx 端口（如 5173/8080）。
        "mcpPort": config.port,
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """返回数据源健康状态和服务运行状态。"""
    rm = get_rm(request)
    store = get_store()
    # 数据源名列表 — 优先从数据库查询（多实例一致性），回退到 rm 内存
    source_names = await _load_source_names(rm, store)
    source_health = [_build_source_health_item(name) for name in source_names]
    return {"sources": source_health, "server": "running"}


@router.get("/source-types")
async def source_types(request: Request) -> dict[str, Any]:
    """返回所有已注册的数据源类型及其字段 schema。

    若 ServerConfig.enabled_source_types 非空,仅返回白名单内的类型;
    空 = 全部启用(默认)。前端据此自动隐藏被禁用的类型。
    """
    config = get_config(request)
    # 严格判断 list 类型,避免 MagicMock 等非 list 对象误判为 truthy
    enabled = getattr(config, "enabled_source_types", []) or []
    return _filter_schemas_by_whitelist(enabled)


@router.get("/environments")
async def list_environments() -> list[str]:
    """返回预设环境列表，供前端下拉选择。"""
    return ENVIRONMENTS


@router.get("/systems")
async def list_systems(request: Request) -> list[dict[str, Any]]:
    """列出所有系统编号及其数据源数量,供 MCP 配置按系统筛选使用。"""
    rm = get_rm(request)
    store = get_store()
    configs = await _load_all_source_configs(rm, store)
    return _aggregate_systems(configs)


@router.get("/systems/{system_id}/sources")
async def list_sources_by_system(request: Request, system_id: str) -> list[dict[str, Any]]:
    """按系统编号列出该系统下所有数据源。"""
    rm = get_rm(request)
    store = get_store()
    if is_store_usable(store):
        try:
            sources_list = await store.load_sources_by_system(system_id)
            return await _build_sources_response_from_store_list(sources_list, store)
        except Exception as exc:
            logger.warning("查询系统 %r 数据源失败: %s", system_id, exc)
    # 回退到 rm
    return await _build_sources_response_from_rm_filtered(rm, system_id)


@router.get("/sources")
async def list_sources(request: Request) -> list[dict[str, Any]]:
    """列出所有数据源(优先从 store,回退到 rm 内存)。"""
    rm = get_rm(request)
    store = get_store()
    if is_store_usable(store):
        try:
            sources_list = await store.load_sources()
            return await _build_sources_response_from_store_list(sources_list, store)
        except Exception as exc:
            logger.warning("查询数据源列表失败: %s", exc)
    # 回退到 rm
    return await _build_sources_response_from_rm(rm)


@router.post("/sources")
async def create_source(request: Request) -> dict[str, Any]:
    """创建数据源并自动生成默认工具,持久化到 ConfigStore。"""
    body = await request.json()
    config = get_config(request)
    name, src_type, system_id, environment = _validate_create_source_input(body, config)
    rm = get_rm(request)
    store = get_store()
    # 数据源主键包含系统编号+环境: 同一系统同一环境下数据源名不可重复,不同系统/环境可同名
    # 优先从 store 查询唯一性（多实例一致性），回退到 rm 内存
    await _check_source_uniqueness(rm, store, name, system_id, environment)
    # Normalize field names: frontend sends "database" for sqlite, backend expects "path"
    config_data = {k: v for k, v in body.items() if k not in ("name", "type")}
    _normalize_sqlite_config(src_type, config_data)
    source = await _build_source_or_raise(src_type, name, config_data, "创建数据源失败")
    await rm.add_source(name, source, config=config_data)
    created_tools = await _auto_create_tools(rm, src_type, name)
    # 持久化到 ConfigStore（store 已在上方唯一性校验时获取）
    persisted = await _persist_new_source(store, name, src_type, config_data)
    # 创建后从 store 读取配置（多实例一致性），回退到 config_data + rm
    result = await _build_source_response(rm, store, name, src_type, config_data)
    result["createdTools"] = created_tools
    result["persisted"] = persisted
    return result


@router.get("/sources/{name}")
async def get_source(request: Request, name: str) -> dict[str, Any]:
    """获取指定数据源详情,支持编辑场景回填密文密码。"""
    _validate_name_param(name)
    rm = get_rm(request)
    store = get_store()
    # 存在性检查 + 配置读取: 优先用 store, 回退到 rm
    src_cfg = await _load_source_config(rm, store, name)
    if src_cfg is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    # 编辑场景: 优先从持久化存储读取密文, 前端原样回传即可保持密码不变;
    # 回退到 ResourceManager 内存配置中的明文密码(未启用持久化时),
    # 前端原样回传时 _normalize_password_for_storage 会加密后落库。
    password_ciphertext = await _get_password_ciphertext(store, src_cfg, name)
    return await _source_to_dict(
        name, src_cfg, password_ciphertext=password_ciphertext, store=store
    )


@router.put("/sources/{name}")
async def update_source(request: Request, name: str) -> dict[str, Any]:
    """更新数据源,清理旧工具后重新生成并持久化。"""
    _validate_name_param(name)
    body = await request.json()
    config = get_config(request)
    rm = get_rm(request)
    store = get_store()
    # 存在性检查: 优先用 store, 回退到 rm
    if not await _check_source_exists(rm, store, name):
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    # 失效旧 source 缓存(关闭旧连接池)
    old_cfg = _get_source_config_or_empty(rm, name)
    # V1: 校验 systemId / environment / type 白名单,防止绕过创建时的约束
    src_type = _validate_update_source_input(body, config, old_cfg)
    await rm.invalidate_source(name)
    config_data = _build_config_data(body)
    _normalize_sqlite_config(src_type, config_data)
    # Remove old tools bound to this source before recreating
    old_tools = await _get_tools_for_source(rm, store, name)
    await _remove_tools_for_update(rm, store, name, old_cfg, old_tools)
    source = await _build_source_or_raise(src_type, name, config_data, "更新数据源失败")
    await rm.add_source(name, source, config=config_data)
    await _auto_create_tools(rm, src_type, name)
    # 持久化更新数据源到 ConfigStore（工具已在 _auto_create_tools 中持久化）
    persisted = await _persist_source(store, name, src_type, config_data)
    # T2: 仅在持久化成功后才删除旧 store 记录,防止中间异常导致数据丢失。
    # save_source 以 (name, system_id, environment) 为复合键做 upsert,
    # 当键值变更时会插入新记录而非更新,旧记录需手动清除。
    if persisted:
        await _delete_old_source_record(store, name, old_cfg, config_data)
    # 更新后从 store 读取配置（多实例一致性），回退到 config_data + rm
    result = await _build_source_response(rm, store, name, src_type, config_data)
    result["persisted"] = persisted
    return result


@router.delete("/sources/{name}", status_code=204)
async def delete_source(request: Request, name: str):
    """删除数据源及其绑定工具,并从默认 toolset 移除。"""
    _validate_name_param(name)
    rm = get_rm(request)
    store = get_store()
    # 存在性检查: 优先用 store, 回退到 rm
    if not await _check_source_exists(rm, store, name):
        return
    # 持久化删除前先取出 system_id + environment，用于精确删除 store 中记录
    old_cfg = _get_source_config_or_empty(rm, name)
    sid, env = get_source_env_keys_from_cfg(old_cfg)
    await rm.remove_source(name)
    # Remove tools bound to this source (auto-generated or manual) and
    # drop them from the default toolset so no orphan tools remain.
    # 优先从 store 查询（多实例一致性），回退到 rm 内存
    await _remove_source_tools(rm, store, name)
    # 持久化删除到 ConfigStore
    await _persist_delete_source(store, name, sid, env)


@router.post("/sources/{name}/test")
async def test_source(request: Request, name: str) -> dict[str, Any]:
    """测试数据源连通性,返回 ok/latency/error。"""
    _validate_name_param(name)
    rm = get_rm(request)
    if not rm.has_source(name):
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    source = await rm.get_source(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    try:
        result = await _measure_source_connect_latency(source)
        return result
    finally:
        await rm.release_source(name)


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    """列出所有工具及其分类信息。"""
    rm = get_rm(request)
    tools = rm.get_tools_map()
    return [_build_tool_list_item(rm, name, tool) for name, tool in tools.items()]


@router.get("/tools/{name}")
async def get_tool(request: Request, name: str) -> dict[str, Any]:
    """获取指定工具详情(含 inputSchema)。"""
    rm = get_rm(request)
    tool = rm.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool {name!r} not found")
    return _build_tool_detail(rm, name, tool)


@router.post("/tools/{name}/invoke")
async def invoke_tool(request: Request, name: str) -> dict[str, Any]:
    """调用指定工具并返回结果。"""
    rm = get_rm(request)
    tool = rm.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool {name!r} not found")
    body = await request.json()
    params = body.get("params", {})
    return await _invoke_tool_safe(tool, params, rm)


@router.delete("/tools/{name}", status_code=204)
async def delete_tool(request: Request, name: str):
    """删除指定工具,并持久化到 ConfigStore。"""
    rm = get_rm(request)
    rm.remove_tool(name)
    # 持久化删除到 ConfigStore
    store = get_store()
    if not is_store_usable(store):
        return
    try:
        await store.delete_tool(name)
    except Exception as exc:
        logger.warning("持久化删除工具 %r 失败: %s", name, exc)


@router.get("/config")
async def get_config_endpoint(request: Request) -> dict[str, Any]:
    """返回服务端配置概览(YAML + parsed)。"""
    config = get_config(request)
    prebuilt = config.prebuilt.split(",") if config.prebuilt else []
    parsed = {
        "address": config.address,
        "port": config.port,
        "log_level": config.log_level,
        "sources": len(config.source_configs),
        "tools": len(config.tool_configs),
        "toolsets": len(config.toolset_configs),
    }
    yaml_lines = [
        "# Server Config",
        f"address: {config.address}",
        f"port: {config.port}",
        f"log_level: {config.log_level}",
        f"sources: {len(config.source_configs)} configured",
        f"tools: {len(config.tool_configs)} configured",
        f"toolsets: {len(config.toolset_configs)} configured",
    ]
    return {
        "yaml": "\n".join(yaml_lines),
        "parsed": parsed,
        "prebuiltNames": prebuilt,
    }


@router.post("/config/reload")
async def reload_config(request: Request) -> dict[str, Any]:
    """触发配置重载(占位实现)。"""
    return {"ok": True, "errors": None}


@router.post("/query")
async def execute_query(request: Request) -> dict[str, Any]:
    """在指定数据源上执行 SQL 查询并返回结果。"""
    body = await request.json()
    source_name = body.get("sourceName", "")
    statement = body.get("statement", "")
    _validate_query_input(source_name, statement)
    rm = get_rm(request)
    source = await rm.get_source(source_name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {source_name!r} not found")
    try:
        _validate_source_sql_support(source, source_name)
        return await _run_sql_query(source, statement)
    finally:
        await rm.release_source(source_name)


@router.get("/sources/{name}/tables")
async def list_source_tables(request: Request, name: str) -> dict[str, Any]:
    """List tables in a SQL data source, for the query console sidebar."""
    _validate_name_param(name)
    rm = get_rm(request)
    source = await rm.get_source(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    try:
        if not hasattr(source, "execute_sql"):
            raise HTTPException(
                status_code=400, detail=f"source {name!r} does not support SQL queries"
            )
        return await _query_source_tables(source)
    finally:
        await rm.release_source(name)


@router.post("/mcp-test")
async def mcp_test(request: Request) -> dict[str, Any]:
    """模拟 MCP 客户端调用 tools/list，验证端点配置是否可用。

    内部构造 MCPProtocol 并调用 handle_tools_list，与真实 MCP 客户端
    调用 /sse 或 / 端点的 tools/list 方法走完全相同的代码路径。

    过滤逻辑与 MCP 路由一致：
      - 选了数据源(toolset) → 按数据源 toolset 过滤
      - 仅选系统编号+环境(systemId/environment) → 按系统-环境 toolset 过滤
      - 都未选 → 返回全部工具
    """
    body = await request.json()
    toolset_name, system_id, environment = _parse_mcp_test_input(body)
    rm = get_rm(request)

    # 确定最终用于过滤的 toolset 名称:
    #   选了数据源 → 用数据源名(数据源本身就是一个 toolset)
    #   仅选系统编号+环境 → 优先用 {system_id}-{environment} 格式
    effective_toolset = _resolve_effective_toolset(toolset_name, system_id, environment)
    _validate_toolset_exists(rm, effective_toolset)

    from data_tool_mcp.server.mcp.protocol import MCPProtocol

    protocol = MCPProtocol(rm, toolset_name=effective_toolset)
    result = await protocol.handle_tools_list({})
    return _build_mcp_test_response(result)


@router.get("/toolsets")
async def list_toolsets(request: Request) -> list[dict[str, Any]]:
    """列出所有 toolset（工具集），供 MCP 配置的 toolset 选择下拉框使用。

    返回每个 toolset 的名称和工具数量。空名 toolset（默认包含所有工具）
    显示为 "全部工具"。标注 toolset 类型(source/system/custom)以便前端分组。
    """
    store = get_store()
    if is_store_usable(store):
        result = await _build_toolsets_from_store(store)
        if result:
            return result
    # store 不可用或返回空列表时回退到 rm 内存
    rm = get_rm(request)
    return _build_toolsets_from_rm(rm)


@router.get("/mcp-stats")
async def mcp_stats(
    request: Request,
    start_date: str | None = None,
    end_date: str | None = None,
    system_id: str = "",
    source_name: str = "",
) -> dict[str, Any]:
    """MCP 请求统计接口 — 支持按系统、数据源、日期范围聚合查询。

    参数:
        start_date: YYYY-MM-DD（含），默认今天往前 30 天
        end_date:   YYYY-MM-DD（含），默认今天
        system_id:  筛选系统编号，空串表示不限
        source_name: 筛选数据源名称，空串表示不限

    返回:
        summary / by_system / by_source / by_tool / timeline
    """
    store = get_store()
    if not is_store_usable(store):
        return _build_no_persistence_stats_response()

    start_date, end_date = _resolve_date_range(start_date, end_date)
    result = await store.query_mcp_stats(
        start_date=start_date,
        end_date=end_date,
        system_id=system_id.strip(),
        source_name=source_name.strip(),
    )
    result["start_date"] = start_date
    result["end_date"] = end_date
    return result


@router.get("/mcp-logs")
async def mcp_logs(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    system_id: str = "",
    source_name: str = "",
) -> dict[str, Any]:
    """MCP 请求记录分页查询 — 最新记录排在最前面。

    参数:
        page: 页码（从 1 开始）
        page_size: 每页条数（最大 100）
        start_date / end_date / system_id / source_name: 筛选条件（与 mcp-stats 共享）
    """
    store = get_store()
    if not is_store_usable(store):
        return _build_no_persistence_logs_response(page, page_size)

    start_date, end_date = _resolve_date_range(start_date, end_date)
    result = await store.query_mcp_logs(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        system_id=system_id.strip(),
        source_name=source_name.strip(),
    )
    result["start_date"] = start_date
    result["end_date"] = end_date
    return result
