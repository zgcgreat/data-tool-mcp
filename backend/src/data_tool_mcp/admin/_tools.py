"""工具 / 工具集 / 系统聚合相关辅助函数。

从 admin/router.py 拆分而来,集中处理:
  - 工具分类 (sql / oneclick / parameterized)
  - 工具 input schema 构造 (manifest.parameters → JSON Schema)
  - list_tools / get_tool 响应项构造
  - 工具调用 _invoke_tool_safe
  - 按 systemId 聚合数据源
  - toolset 分类 (all / system / source / custom) 与排序
  - list_toolsets 响应构造 (store / rm 两个数据源)
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from data_tool_mcp.admin._common import (
    extract_env_keys,
    extract_source_names,
    get_source_env_keys_from_cfg,
    logger,
)
from data_tool_mcp.admin._constants import TOOLSET_TYPE_ORDER


# ---------------------------------------------------------------------------
# 工具分类辅助函数
# ---------------------------------------------------------------------------


def _get_tool_params(tool: Any) -> list:
    """获取工具的参数清单,无 manifest 时返回空列表。"""
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    return manifest.parameters if manifest else []


def _is_sql_only_param(params: list) -> bool:
    """判断参数列表是否仅含一个名为 sql 的参数。"""
    return len(params) == 1 and params[0].name == "sql"


def _classify_by_required(params: list) -> str:
    """根据是否有必填参数返回 parameterized / oneclick。"""
    return "parameterized" if any(p.default is None for p in params) else "oneclick"


def _classify_tool(tool: Any, tool_type: str) -> str:
    """Classify a tool for UI display based on its manifest parameters.

    Categories:
      - "sql":          Manifest's only parameter is 'sql' — user must provide
                        full SQL text. (e.g. postgres-execute-sql, sqlite-execute-sql)
      - "oneclick":     No parameters, or every parameter has a default value —
                        user can just click Execute. (e.g. list-tables, list-views)
      - "parameterized":Has required parameters (no default) — user must fill in
                        form fields. (e.g. get-column-cardinality, get-query-plan)
    """
    params = _get_tool_params(tool)
    if not params:
        return "oneclick"
    if _is_sql_only_param(params):
        return "sql"
    return _classify_by_required(params)


# ---------------------------------------------------------------------------
# get_tool 输入 schema 构造辅助函数
# ---------------------------------------------------------------------------


def _build_param_property(param) -> dict[str, Any]:
    """将单个 ParameterManifest 转为 JSON Schema property。"""
    prop: dict[str, Any] = {
        "type": param.type,
        "description": param.description,
    }
    if param.default is not None:
        prop["default"] = param.default
    if param.allowed_values:
        prop["enum"] = param.allowed_values
    return prop


def _has_manifest_params(manifest) -> bool:
    """判断 manifest 是否有参数。"""
    return bool(manifest and manifest.parameters)


def _collect_param_props(parameters: list) -> tuple[dict[str, Any], list[str]]:
    """收集参数的 properties 和 required 列表。"""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in parameters:
        properties[param.name] = _build_param_property(param)
        if param.required:
            required.append(param.name)
    return properties, required


def _build_input_schema(manifest) -> dict[str, Any] | None:
    """将 manifest.parameters 转为前端使用的 JSON Schema 格式。"""
    if not _has_manifest_params(manifest):
        return None
    properties, required = _collect_param_props(manifest.parameters)
    return {"properties": properties, "required": required}


# ---------------------------------------------------------------------------
# list_tools / get_tool 响应项构造
# ---------------------------------------------------------------------------


def _get_tool_env_keys(rm, source_name: str | None) -> tuple[str, str]:
    """从数据源配置中提取工具的 (systemId, environment)。"""
    if not source_name:
        return "", ""
    src_cfg = rm.get_source_config(source_name) or {}
    return get_source_env_keys_from_cfg(src_cfg)


def _build_tool_list_item(rm, name: str, tool) -> dict[str, Any]:
    """构造 list_tools 接口中单个工具的响应项。"""
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    tool_type = rm.get_tool_type(name)
    source_name = getattr(tool, "source_name", None)
    system_id, environment = _get_tool_env_keys(rm, source_name)
    return {
        "name": name,
        "type": tool_type,
        "source": source_name,
        "description": manifest.description if manifest else None,
        "category": _classify_tool(tool, tool_type),
        "systemId": system_id,
        "environment": environment,
    }


def _build_tool_detail(rm, name: str, tool) -> dict[str, Any]:
    """构造 get_tool 接口的工具详情响应。"""
    manifest = tool.manifest() if hasattr(tool, "manifest") else None
    tool_type = rm.get_tool_type(name)
    return {
        "name": name,
        "type": tool_type,
        "source": getattr(tool, "source_name", None),
        "description": manifest.description if manifest else None,
        "inputSchema": _build_input_schema(manifest),
        "category": _classify_tool(tool, tool_type),
    }


async def _invoke_tool_safe(tool, params: dict[str, Any], rm) -> dict[str, Any]:
    """调用工具并处理异常:ValueError 转 400,其他转 500。"""
    try:
        result = await tool.invoke(params, source_provider=rm)
        return {"result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# store 优先 / rm 回退 的工具查询辅助函数
# ---------------------------------------------------------------------------


def _is_sql_tool_type(tool_type: str) -> bool:
    """判断工具类型是否为 SQL 工具(以 -sql 或 -execute-sql 结尾)。

    这类工具在无 statement 且无 templateParameters 时,默认有单个 sql 参数,
    用户需输入 SQL 语句。
    """
    return tool_type.endswith("-sql") or tool_type.endswith("-execute-sql")


def _classify_tool_from_stored_data(tool_data: dict[str, Any], tool_type: str) -> str:
    """从 store 数据分类工具(无 rm Tool 实例时的回退方案)。

    规则与 _classify_tool 保持一致:
      - 有 templateParameters → 按参数分类(sql / parameterized / oneclick)
      - 无 templateParameters + 有 statement → oneclick(内置 SQL,无用户参数)
      - 无 templateParameters + 无 statement + SQL 工具类型 → sql(用户输入 SQL)
      - 其它 → oneclick(无参数工具,如 list-tables)
    """
    from data_tool_mcp.tools.base import _manifests_from_dicts

    template_params = tool_data.get("templateParameters") or []
    if template_params:
        params = _manifests_from_dicts(template_params)
        if not params:
            return "oneclick"
        if len(params) == 1 and params[0].name == "sql":
            return "sql"
        return "parameterized" if any(p.default is None for p in params) else "oneclick"
    # 无 templateParameters
    statement = tool_data.get("statement", "")
    if statement:
        # 内置 statement,无用户参数
        return "oneclick"
    # 无 statement:SQL 工具类型默认有 sql 参数,其它视为无参工具
    if _is_sql_tool_type(tool_type):
        return "sql"
    return "oneclick"


def _build_input_schema_from_stored_data(
    tool_data: dict[str, Any], tool_type: str
) -> dict[str, Any] | None:
    """从 store 数据构造 inputSchema(无 rm Tool 实例时的回退方案)。"""
    from data_tool_mcp.tools.base import ParameterManifest, ToolManifest, _manifests_from_dicts

    template_params = tool_data.get("templateParameters") or []
    if template_params:
        params = _manifests_from_dicts(template_params)
        manifest = ToolManifest(
            description=tool_data.get("description", ""), parameters=params
        )
        return _build_input_schema(manifest)
    # 无 templateParameters
    statement = tool_data.get("statement", "")
    if statement:
        # 内置 statement,无参数
        return None
    # 无 statement + SQL 工具类型:默认有 sql 参数
    if _is_sql_tool_type(tool_type):
        params = [
            ParameterManifest(
                name="sql",
                type="string",
                description="SQL statement to execute",
                required=True,
            )
        ]
        manifest = ToolManifest(
            description=tool_data.get("description", ""), parameters=params
        )
        return _build_input_schema(manifest)
    # 无参工具
    return None


def _build_tool_list_item_from_store(
    rm, tool_data: dict[str, Any]
) -> dict[str, Any]:
    """从 store 数据构造 list_tools 接口中单个工具的响应项。

    category 优先从 rm 内存获取(精确,能反映运行时 manifest),
    回退到 store 数据分类(基于 templateParameters / statement / tool_type)。
    """
    name = tool_data.get("name", "")
    tool_type = tool_data.get("type", "unknown")
    source_name = tool_data.get("source", "")
    description = tool_data.get("description", "")
    system_id = str(tool_data.get("systemId", "") or "").strip()
    environment = str(tool_data.get("environment", "") or "").strip()
    # 优先从 rm 内存获取精确的 category 和 description
    tool = rm.get_tool(name)
    if tool is not None:
        manifest = tool.manifest() if hasattr(tool, "manifest") else None
        if manifest:
            description = manifest.description
        category = _classify_tool(tool, tool_type)
    else:
        category = _classify_tool_from_stored_data(tool_data, tool_type)
    return {
        "name": name,
        "type": tool_type,
        "source": source_name,
        "description": description,
        "category": category,
        "systemId": system_id,
        "environment": environment,
    }


def _build_tool_detail_from_store(
    rm, tool_data: dict[str, Any]
) -> dict[str, Any]:
    """从 store 数据构造 get_tool 接口的工具详情响应。

    inputSchema 和 category 优先从 rm 内存获取(精确),
    回退到 store 数据构造(基于 templateParameters / statement / tool_type)。
    """
    name = tool_data.get("name", "")
    tool_type = tool_data.get("type", "unknown")
    # rm 命中时直接用 rm 的工具实例构造(最精确)
    tool = rm.get_tool(name)
    if tool is not None:
        return _build_tool_detail(rm, name, tool)
    # rm 未命中,从 store 数据构造
    source_name = tool_data.get("source", "")
    description = tool_data.get("description", "")
    category = _classify_tool_from_stored_data(tool_data, tool_type)
    input_schema = _build_input_schema_from_stored_data(tool_data, tool_type)
    return {
        "name": name,
        "type": tool_type,
        "source": source_name,
        "description": description,
        "inputSchema": input_schema,
        "category": category,
    }


async def _build_tools_response_from_store(
    rm, store
) -> list[dict[str, Any]] | None:
    """从 store 构造工具列表响应,失败时返回 None 触发回退到 rm。"""
    try:
        tools_list = await store.load_tools()
    except Exception as exc:
        logger.warning("查询工具列表失败: %s", exc)
        return None
    return [_build_tool_list_item_from_store(rm, t) for t in tools_list]


async def _build_tool_detail_response_from_store(
    rm, store, name: str
) -> dict[str, Any] | None:
    """从 store 构造工具详情响应,失败或不存在时返回 None 触发回退到 rm。"""
    try:
        tool_data = await store.get_tool(name)
    except Exception as exc:
        logger.warning("查询工具 %r 失败: %s", name, exc)
        return None
    if tool_data is None:
        return None
    return _build_tool_detail_from_store(rm, tool_data)


async def _check_tool_exists(rm, store, name: str) -> bool:
    """工具存在性检查,优先用 store,回退到 rm。"""
    if not store or not store.is_persistent:
        return rm.get_tool(name) is not None
    try:
        existing = await store.get_tool(name)
        return existing is not None
    except Exception as exc:
        logger.warning("查询工具 %r 失败: %s", name, exc)
        return rm.get_tool(name) is not None


async def _get_tool_for_action(rm, store, name: str):
    """多实例一致性辅助:获取 Tool 实例用于 invoke 操作。

    流程:
      1. rm.get_tool 命中直接返回(常见路径,无 DB 开销)
      2. rm 未命中但 store 命中:从 store 加载 tool_data,
         调用 decode_tool_config + initialize 构造 Tool 实例并注册到 rm
      3. store 也未命中:返回 None(404)

    多实例场景: 实例 A 创建数据源自动生成工具后写入 store,实例 B 在 5s
    热重载窗口内 rm 内存无此工具,通过本函数可从 store 立即加载并执行(0 延迟)。

    副作用治理: 加载工具前先确保 source 配置已注入 rm,否则 _add_tool_to_all_toolsets
    无法创建 system/system-env toolset,会导致 /{systemId}/sse 路径查不到该工具。
    """
    tool = rm.get_tool(name)
    if tool is not None:
        return tool
    if not store or not store.is_persistent:
        return None
    try:
        tool_data = await store.get_tool(name)
    except Exception as exc:
        logger.warning("查询工具 %r 失败: %s", name, exc)
        return None
    if tool_data is None:
        return None
    # 从 store 数据构造 Tool 实例并注册到 rm(下次直接命中内存)
    try:
        from data_tool_mcp.admin._sources import _try_add_tool

        tool_type = tool_data.get("type", "")
        source_name = tool_data.get("source", "")
        # 加载工具前先确保 source 配置已注入 rm,使 _add_tool_to_all_toolsets
        # 能正确创建 source/system/system-env toolset(多实例一致性)
        await _ensure_source_config_in_rm(rm, store, source_name)
        # _try_add_tool 内部会调用 decode_tool_config + initialize + rm.add_tool
        # persist=False 避免重复写回 store(数据源就是从 store 读出来的)
        await _try_add_tool(rm, name, tool_type, tool_data, source_name, persist=False)
        return rm.get_tool(name)
    except Exception as exc:
        logger.warning("从 store 按需加载工具 %r 失败: %s", name, exc)
        return None


async def _ensure_source_config_in_rm(rm, store, source_name: str) -> None:
    """确保 source 配置已注入 rm 内存(多实例一致性)。

    若 rm 未缓存该 source 配置,从 store 加载并注入,使后续 _add_tool_to_all_toolsets
    能正确创建 system/system-env toolset。失败仅告警,不阻断工具加载。
    """
    if not source_name or rm.has_source(source_name):
        return
    if not store or not store.is_persistent:
        return
    try:
        src_cfg = await store.get_source(source_name)
    except Exception as exc:
        logger.warning("按需加载 source 配置 %r 失败: %s", source_name, exc)
        return
    if src_cfg is None:
        return
    try:
        rm.add_source_config(source_name, src_cfg)
    except Exception as exc:
        logger.warning("注入 source 配置 %r 到 rm 失败: %s", source_name, exc)


# ---------------------------------------------------------------------------
# 系统聚合相关辅助函数
# ---------------------------------------------------------------------------


def _init_system_entry(sid: str) -> dict[str, Any]:
    """构造 systems dict 中单个系统的初始结构。"""
    return {
        "systemId": sid,
        "sourceCount": 0,
        "sources": [],
        "environments": [],
    }


def _append_env_to_system(system_entry: dict[str, Any], env: str) -> None:
    """将环境编号追加到系统条目(去重)。"""
    if env and env not in system_entry["environments"]:
        system_entry["environments"].append(env)


def _add_source_to_systems(
    systems: dict[str, dict[str, Any]],
    name: str,
    cfg: dict[str, Any],
) -> None:
    """将单个数据源聚合到 systems dict 中。"""
    sid, env = extract_env_keys(cfg)
    if not sid:
        return
    if sid not in systems:
        systems[sid] = _init_system_entry(sid)
    systems[sid]["sourceCount"] += 1
    systems[sid]["sources"].append(name)
    _append_env_to_system(systems[sid], env)


def _aggregate_systems(configs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """按 systemId 聚合数据源,返回排序后的系统列表。"""
    systems: dict[str, dict[str, Any]] = {}
    for name, cfg in configs.items():
        _add_source_to_systems(systems, name, cfg)
    return sorted(systems.values(), key=lambda x: x["systemId"])


# ---------------------------------------------------------------------------
# Toolset 分类相关辅助函数
# ---------------------------------------------------------------------------


def _classify_named_toolset_type(
    name: str, source_names: set[str], system_ids: set[str]
) -> str:
    """判断具名 toolset 类型: system / source / custom。"""
    if name in system_ids:
        return "system"
    if name in source_names:
        return "source"
    return "custom"


def _classify_toolset_type(
    name: str, source_names: set[str], system_ids: set[str]
) -> str:
    """判断 toolset 类型: all / system / source / custom。"""
    if not name:
        return "all"
    return _classify_named_toolset_type(name, source_names, system_ids)


def _build_toolset_item(name: str, tool_count: int, ts_type: str) -> dict[str, Any]:
    """构造单个 toolset 响应项。"""
    return {
        "name": name,
        "displayName": "全部工具" if not name else name,
        "toolCount": tool_count,
        "type": ts_type,
    }


def _sort_toolsets(result: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """排序: 全部 → system → source → custom, 每组内按名称排序。"""
    result.sort(key=lambda x: (TOOLSET_TYPE_ORDER.get(x["type"], 9), x["name"]))
    return result


def _extract_system_ids(items) -> set[str]:
    """从 items 中提取非空 systemId 集合。"""
    result: set[str] = set()
    for item in items:
        sid, _ = extract_env_keys(item)
        if sid:
            result.add(sid)
    return result


def _extract_source_and_system_names(
    sources_list: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    """从 sources_list 中提取 (source_names, system_ids) 集合。"""
    source_names = set(extract_source_names(sources_list))
    system_ids = _extract_system_ids(sources_list)
    return source_names, system_ids


def _extract_source_and_system_names_from_rm(rm) -> tuple[set[str], set[str]]:
    """从 rm 中提取 (source_names, system_ids) 集合。"""
    configs = rm.get_all_source_configs()
    source_names = set(configs.keys())
    system_ids = _extract_system_ids(configs.values())
    return source_names, system_ids


def _build_toolset_entry(
    item: dict[str, Any],
    source_names: set[str],
    system_ids: set[str],
) -> dict[str, Any]:
    """从 store 返回的单个 toolset 项构造响应项。"""
    name = item.get("name", "")
    tools = item.get("tools", []) or []
    ts_type = _classify_toolset_type(name, source_names, system_ids)
    return _build_toolset_item(name, len(tools), ts_type)


async def _build_toolsets_from_store(store) -> list[dict[str, Any]] | None:
    """从 store 动态聚合 toolset 响应列表,失败时返回 None 触发回退。

    toolsets 表已移除:从 tools 表实时推导 5 类 toolset:
      - all: 全量工具
      - source: 按 source_name 分组
      - system: 按 system_id 分组
      - system-env: 按 system_id + environment 分组(命名 {systemId}-{environment})
      - custom: 按 toolsetNames JSON 数组反向聚合
    """
    try:
        tools_list = await store.load_tools()
    except Exception as exc:
        logger.warning("查询 tools 列表用于聚合 toolset 失败: %s", exc)
        return None

    result: list[dict[str, Any]] = []
    # 1. all toolset:全量工具
    result.append(_build_toolset_item("", len(tools_list), "all"))

    # 2. source toolset:按 source_name 分组
    source_counts: dict[str, int] = {}
    for t in tools_list:
        src = t.get("source", "")
        if src:
            source_counts[src] = source_counts.get(src, 0) + 1
    for name, count in source_counts.items():
        result.append(_build_toolset_item(name, count, "source"))

    # 3. system toolset:按 system_id 分组
    system_counts: dict[str, int] = {}
    for t in tools_list:
        sid = str(t.get("systemId", "") or "").strip()
        if sid:
            system_counts[sid] = system_counts.get(sid, 0) + 1
    for name, count in system_counts.items():
        result.append(_build_toolset_item(name, count, "system"))

    # 4. system-env toolset:按 system_id + environment 分组
    # type 归类为 "custom"(沿用 _classify_named_toolset_type 现有逻辑:
    # 名字不在 system_ids 集合中,因为 system_ids 集合只含纯 systemId)
    system_env_counts: dict[str, int] = {}
    for t in tools_list:
        sid = str(t.get("systemId", "") or "").strip()
        env = str(t.get("environment", "") or "").strip()
        if sid and env:
            ts_name = f"{sid}-{env}"
            system_env_counts[ts_name] = system_env_counts.get(ts_name, 0) + 1
    for name, count in system_env_counts.items():
        # 名字含 "-" 不在 system_ids 集合中,自动归类为 "custom"
        result.append(_build_toolset_item(name, count, "custom"))

    # 5. custom toolset:按 toolsetNames JSON 数组反向聚合
    custom_counts: dict[str, int] = {}
    for t in tools_list:
        ts_names = t.get("toolsetNames") or []
        if not isinstance(ts_names, list):
            continue
        for ts_name in ts_names:
            if ts_name:
                custom_counts[ts_name] = custom_counts.get(ts_name, 0) + 1
    for name, count in custom_counts.items():
        # custom toolset 名称可能与 system-env 重名(理论上不会),去重处理:
        # 已存在的同名 toolset 跳过(以 system-env 优先)
        if not any(item["name"] == name for item in result):
            result.append(_build_toolset_item(name, count, "custom"))

    return _sort_toolsets(result)


def _build_toolsets_from_rm(rm) -> list[dict[str, Any]]:
    """从 rm 内存构造 toolset 响应列表。

    rm._toolsets 由 _add_tool_to_all_toolsets 动态维护,包含 5 类 toolset:
    all / source / system / system-env / custom。
    """
    toolsets = rm.get_toolsets_map()
    source_names, system_ids = _extract_source_and_system_names_from_rm(rm)
    result: list[dict[str, Any]] = []
    for name, toolset in toolsets.items():
        ts_type = _classify_toolset_type(name, source_names, system_ids)
        result.append(_build_toolset_item(name, len(toolset.tool_names), ts_type))
    return _sort_toolsets(result)
