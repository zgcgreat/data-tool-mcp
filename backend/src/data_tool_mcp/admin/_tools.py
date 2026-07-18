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
    """从 store 构造 toolset 响应列表,失败时返回 None 触发回退。"""
    try:
        toolsets_list = await store.load_toolsets()
        sources_list = await store.load_sources()
    except Exception as exc:
        logger.warning("查询 toolset 列表失败: %s", exc)
        return None
    source_names, system_ids = _extract_source_and_system_names(sources_list)
    result = [_build_toolset_entry(item, source_names, system_ids) for item in toolsets_list]
    return _sort_toolsets(result)


def _build_toolsets_from_rm(rm) -> list[dict[str, Any]]:
    """从 rm 内存构造 toolset 响应列表。"""
    toolsets = rm.get_toolsets_map()
    source_names, system_ids = _extract_source_and_system_names_from_rm(rm)
    result: list[dict[str, Any]] = []
    for name, toolset in toolsets.items():
        ts_type = _classify_toolset_type(name, source_names, system_ids)
        result.append(_build_toolset_item(name, len(toolset.tool_names), ts_type))
    return _sort_toolsets(result)
