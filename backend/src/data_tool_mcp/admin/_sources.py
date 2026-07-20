"""数据源 CRUD / 持久化 / 校验 / 响应构造辅助函数。

从 admin/router.py 拆分而来,集中处理:
  - prebuilt yaml 工具加载
  - 自动建工具 (prebuilt + fallback)
  - 数据源存在性检查 / 配置加载 / 工具计数
  - _source_to_dict 字段处理与密码脱敏
  - 创建/更新数据源入参校验、唯一性检查、白名单校验
  - 更新/删除时清理旧工具与旧 store 记录
  - /sources /source-types 路由的响应构造辅助
"""

from __future__ import annotations

import os
import re
from typing import Any

import yaml
from fastapi import HTTPException

from data_tool_mcp.admin._common import (
    extract_env_keys,
    get_enabled_source_types,
    get_source_env_keys_from_cfg,
    is_store_usable,
    is_whitelist_active,
    logger,
)
from data_tool_mcp.admin._constants import (
    ENVIRONMENTS,
    PREBUILT_DIR,
    PREBUILT_YAML_OVERRIDES,
    SOURCE_DEFAULT_TOOLS,
    SOURCE_TYPE_SCHEMAS,
)
from data_tool_mcp.config.store import get_store
from data_tool_mcp.sources import decode_source_config
from data_tool_mcp.tools import decode_tool_config
from data_tool_mcp.utils.errors import format_error_message


# ---------------------------------------------------------------------------
# prebuilt yaml 工具加载相关辅助函数
# ---------------------------------------------------------------------------


def _read_yaml_docs(path: str) -> list | None:
    """读取 yaml 文件并返回所有文档列表,失败返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return list(yaml.safe_load_all(f))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to read prebuilt yaml %s: %s", path, exc)
        return None


def _is_tool_doc(doc: Any) -> bool:
    """判断 yaml 文档是否为 tool 类型。"""
    return isinstance(doc, dict) and doc.get("kind") == "tool"


def _collect_tool_docs(docs: list) -> list[dict[str, Any]]:
    """从 yaml 文档列表中筛选 kind==tool 的文档。"""
    return [doc for doc in docs if _is_tool_doc(doc)]


def _filter_tool_docs(docs: list) -> list[dict[str, Any]] | None:
    """从 yaml 文档列表中筛选 kind==tool 的文档,空则返回 None。"""
    tools = _collect_tool_docs(docs)
    return tools or None


def _build_tool_to_toolsets_map(docs: list) -> dict[str, list[str]]:
    """从 yaml 文档列表反向构造 {tool_yaml_name: [toolset_name, ...]} 映射。

    遍历 kind: toolset 文档,将 toolset 名称反向注入到其所属工具的列表中。
    用于在创建 tool 时注入 toolsetNames 字段(替代独立的 toolsets 表)。
    """
    tool_to_toolsets: dict[str, list[str]] = {}
    for doc in docs:
        if not (isinstance(doc, dict) and doc.get("kind") == "toolset"):
            continue
        ts_name = doc.get("name")
        if not ts_name:
            continue
        for tool_ref in doc.get("tools", []) or []:
            tool_yaml_name = (
                tool_ref.get("name") if isinstance(tool_ref, dict) else None
            )
            if tool_yaml_name:
                tool_to_toolsets.setdefault(tool_yaml_name, []).append(ts_name)
    return tool_to_toolsets


def _load_prebuilt_tools(
    src_type: str,
) -> tuple[list[dict[str, Any]] | None, dict[str, list[str]]]:
    """Extract tool definitions from prebuiltconfigs/<src_type>.yaml.

    Returns:
        (tool_docs, tool_to_toolsets_map)
        - tool_docs: list of `kind: tool` docs (with the original tool name
          and full config such as `statement`/`templateParameters`), or None
          when there is no prebuilt yaml for this source type.
        - tool_to_toolsets_map: {tool_yaml_name: [toolset_name, ...]},
          反向映射工具到其所属 custom toolset(从 kind: toolset 块推导)。

    Using the prebuilt yaml as the source of truth guarantees the admin UI
    auto-generates EXACTLY the same tools `--prebuilt <src_type>` would, and
    stays in sync if the yaml changes.
    """
    yaml_name = PREBUILT_YAML_OVERRIDES.get(src_type, src_type)
    path = os.path.join(PREBUILT_DIR, f"{yaml_name}.yaml")
    if not os.path.exists(path):
        return None, {}
    docs = _read_yaml_docs(path)
    if docs is None:
        return None, {}
    tool_docs = _filter_tool_docs(docs)
    tool_to_toolsets = _build_tool_to_toolsets_map(docs)
    return tool_docs, tool_to_toolsets


# ---------------------------------------------------------------------------
# Source 构造辅助
# ---------------------------------------------------------------------------


async def _build_source(src_type: str, name: str, config_data: dict[str, Any]):
    """Build and initialize a Source from type + config dict."""
    source_config = decode_source_config(src_type, name, config_data)
    return await source_config.initialize()


# ---------------------------------------------------------------------------
# 持久化 / 自动建工具相关辅助函数
# ---------------------------------------------------------------------------


def _build_persist_config(tool_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """从 tool_data 中拆出 description 与剩余 config_data,供持久化使用。"""
    description = tool_data.get("description", "")
    config_data = {
        k: v for k, v in tool_data.items() if k not in ("name", "type", "source", "description")
    }
    return description, config_data


async def _persist_tool(
    tool_name: str, tool_type: str, source: str, tool_data: dict[str, Any]
) -> None:
    """将工具持久化到 ConfigStore（仅在持久化模式下生效）。"""
    store = get_store()
    if not is_store_usable(store):
        return
    try:
        description, config_data = _build_persist_config(tool_data)
        await store.save_tool(tool_name, tool_type, source, description, config_data)
    except Exception as exc:
        logger.warning("持久化工具 %r 失败: %s", tool_name, exc)


def _inject_env_keys(tool_data: dict[str, Any], system_id: str, environment: str) -> None:
    """将非空的 systemId / environment 注入到 tool_data。"""
    extras = {"systemId": system_id, "environment": environment}
    tool_data.update({k: v for k, v in extras.items() if v})


def _tool_already_exists(tool_name: str | None, rm) -> bool:
    """tool_name 为 None 或已存在时返回 True。"""
    return tool_name is None or tool_name in rm.get_tools_map()


def _build_tool_data(
    doc: dict[str, Any],
    name: str,
    tool_name: str,
    tool_type: str,
    system_id: str,
    environment: str,
) -> dict[str, Any]:
    """基于 prebuilt yaml doc 构造完整 tool_data。"""
    tool_data = {k: v for k, v in doc.items() if k not in ("kind", "name", "source")}
    tool_data["name"] = tool_name
    tool_data["source"] = name
    _inject_env_keys(tool_data, system_id, environment)
    tool_data.setdefault(
        "description",
        f"Auto-generated {tool_type} tool for source '{name}'.",
    )
    return tool_data


def _build_prebuilt_tool_doc(
    doc: dict[str, Any],
    name: str,
    system_id: str,
    environment: str,
    tool_to_toolsets: dict[str, list[str]],
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """从 prebuilt doc 构造 (tool_name, tool_type, tool_data);缺失字段返回 (None, None, None)。

    tool_to_toolsets 为 {tool_yaml_name: [toolset_name, ...]} 反向映射,
    用于注入 toolsetNames 字段(替代独立的 toolsets 表)。
    """
    yaml_name = doc.get("name")
    tool_type = doc.get("type")
    if not yaml_name or not tool_type:
        return None, None, None
    tool_name = f"{name}-{yaml_name}"
    tool_data = _build_tool_data(doc, name, tool_name, tool_type, system_id, environment)
    # 注入 toolsetNames(基于 yaml_name 反查)
    ts_names = tool_to_toolsets.get(yaml_name, [])
    if ts_names:
        tool_data["toolsetNames"] = list(ts_names)
    return tool_name, tool_type, tool_data


async def _try_add_tool(
    rm,
    tool_name: str,
    tool_type: str,
    tool_data: dict[str, Any],
    source_name: str,
    persist: bool,
) -> bool:
    """尝试初始化并注册一个工具,成功返回 True,失败仅告警。

    tool_data 中的 toolsetNames(custom toolset 归属)会透传到 Tool 实例,
    由 ResourceManager._add_tool_to_all_toolsets 读取并维护 custom toolset。
    """
    try:
        tool_config = decode_tool_config(tool_type, tool_name, tool_data)
        tool = await tool_config.initialize()
        # 透传 toolsetNames 到 Tool 实例(替代独立 toolsets 表)
        ts_names = tool_data.get("toolsetNames") or []
        if ts_names:
            # BaseTool 已有 toolset_names property,通过 _cfg 透传;
            # 直接 setattr 兼容非 BaseTool 实现或 _cfg 不可写的场景
            try:
                tool._cfg.toolset_names = list(ts_names)
            except (AttributeError, TypeError):
                setattr(tool, "toolset_names", list(ts_names))
        rm.add_tool(tool_name, tool, tool_type)
        if persist:
            await _persist_tool(tool_name, tool_type, source_name, tool_data)
        return True
    except Exception as exc:
        logger.warning("auto-create tool %r (%s) failed: %s", tool_name, tool_type, exc)
        return False


async def _try_create_prebuilt_tool(
    rm,
    doc: dict[str, Any],
    name: str,
    system_id: str,
    environment: str,
    tool_to_toolsets: dict[str, list[str]],
) -> str | None:
    """尝试基于单个 prebuilt doc 创建工具,返回创建的工具名(或 None)。"""
    tool_name, tool_type, tool_data = _build_prebuilt_tool_doc(
        doc, name, system_id, environment, tool_to_toolsets
    )
    if _tool_already_exists(tool_name, rm):
        return None
    if await _try_add_tool(rm, tool_name, tool_type, tool_data, name, persist=True):
        return tool_name
    return None


async def _create_prebuilt_tools(
    rm,
    prebuilt: list[dict[str, Any]],
    name: str,
    system_id: str,
    environment: str,
    tool_to_toolsets: dict[str, list[str]],
) -> list[str]:
    """基于 prebuilt yaml 文档列表创建工具。"""
    created: list[str] = []
    for doc in prebuilt:
        tool_name = await _try_create_prebuilt_tool(
            rm, doc, name, system_id, environment, tool_to_toolsets
        )
        if tool_name:
            created.append(tool_name)
    return created


def _build_default_tool_data(
    name: str,
    suffix: str,
    tool_type: str,
    system_id: str,
    environment: str,
) -> dict[str, Any]:
    """构造 fallback 工具的最小 tool_data。"""
    tool_name = f"{name}-{suffix}"
    tool_data: dict[str, Any] = {
        "name": tool_name,
        "type": tool_type,
        "source": name,
        "description": f"Auto-generated {tool_type} tool for source '{name}'.",
    }
    _inject_env_keys(tool_data, system_id, environment)
    return tool_data


async def _try_create_default_tool(
    rm,
    name: str,
    suffix: str,
    tool_type: str,
    system_id: str,
    environment: str,
) -> str | None:
    """尝试创建单个 fallback 工具,返回工具名(或 None)。"""
    tool_name = f"{name}-{suffix}"
    if _tool_already_exists(tool_name, rm):
        return None
    tool_data = _build_default_tool_data(name, suffix, tool_type, system_id, environment)
    if await _try_add_tool(rm, tool_name, tool_type, tool_data, name, persist=False):
        return tool_name
    return None


async def _create_default_tools(
    rm,
    src_type: str,
    name: str,
    system_id: str,
    environment: str,
) -> list[str]:
    """Fallback: 为无 prebuilt yaml 的数据源类型创建最小工具集。"""
    created: list[str] = []
    for suffix, tool_type in SOURCE_DEFAULT_TOOLS.get(src_type, []):
        tool_name = await _try_create_default_tool(
            rm, name, suffix, tool_type, system_id, environment
        )
        if tool_name:
            created.append(tool_name)
    return created


async def _auto_create_tools(rm, src_type: str, name: str) -> list[str]:
    """Auto-generate default tools for a newly-added source.

    Fulfills the admin UI promise ('添加数据源后会自动生成工具'): when a source
    is added at runtime we register its default tool(s) so they show up in
    GET /mcp-api/tools and are exposed via MCP (added to the default toolset).

    Strategy:
      1. If a prebuilt <src_type>.yaml exists, derive the COMPLETE tool set
         from it (name + full config such as inline SQL). This matches
         `--prebuilt <src_type>` exactly and stays in sync with the yaml.
      2. Otherwise fall back to the hardcoded SOURCE_DEFAULT_TOOLS specs
         (used for types without a prebuilt yaml, e.g. mongodb/redis/http).

    A failure creating one tool only warns and is skipped, so a single bad
    tool can never block adding the source.
    """
    src_cfg = rm.get_source_config(name) or {}
    system_id, environment = extract_env_keys(src_cfg)
    prebuilt, tool_to_toolsets = _load_prebuilt_tools(src_type)
    if prebuilt is not None:
        return await _create_prebuilt_tools(
            rm, prebuilt, name, system_id, environment, tool_to_toolsets
        )
    return await _create_default_tools(rm, src_type, name, system_id, environment)


# ---------------------------------------------------------------------------
# 数据源配置加载 / 存在性检查 / 工具计数相关辅助函数
# ---------------------------------------------------------------------------


async def _load_all_source_configs(rm, store) -> dict[str, dict[str, Any]]:
    """加载所有数据源配置,优先用 store,失败或非持久化时回退到 rm。"""
    if not is_store_usable(store):
        return rm.get_all_source_configs()
    try:
        sources_list = await store.load_sources()
        return _convert_sources_list_to_configs(sources_list)
    except Exception as exc:
        logger.warning("查询数据源列表失败: %s", exc)
        return rm.get_all_source_configs()


def _convert_sources_list_to_configs(
    sources_list: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """将 store 返回的 list 形式转为 {name: cfg} dict。"""
    configs: dict[str, dict[str, Any]] = {}
    for s in sources_list:
        sname = s.get("name", "")
        if sname:
            configs[sname] = s
    return configs


async def _check_source_exists(rm, store, name: str) -> bool:
    """数据源存在性检查,优先用 store,回退到 rm。"""
    if not is_store_usable(store):
        return rm.has_source(name)
    try:
        existing = await store.get_source(name)
        return existing is not None
    except Exception as exc:
        logger.warning("查询数据源 %r 失败: %s", name, exc)
        return rm.has_source(name)


def _get_tools_for_source_from_rm(rm, name: str) -> list[str]:
    """从 rm 内存中查询绑定到指定数据源的工具名列表。"""
    return [
        tname
        for tname, t in rm.get_tools_map().items()
        if getattr(t, "source_name", None) == name
    ]


def _extract_tool_names_from_list(tools_list: list[dict[str, Any]]) -> list[str]:
    """从工具列表中提取非空工具名。"""
    return [t["name"] for t in tools_list if t.get("name")]


async def _get_tools_for_source(rm, store, name: str) -> list[str]:
    """获取数据源绑定的工具名列表,优先用 store,回退到 rm。"""
    if not is_store_usable(store):
        return _get_tools_for_source_from_rm(rm, name)
    try:
        tools_list = await store.load_tools_by_source(name)
        return _extract_tool_names_from_list(tools_list)
    except Exception as exc:
        logger.warning("查询数据源 %r 的工具失败: %s", name, exc)
        return _get_tools_for_source_from_rm(rm, name)


def _compute_tool_count_from_rm(rm, name: str) -> int:
    """从 rm 内存计算绑定到指定数据源的工具数量。"""
    return sum(
        1 for t in rm.get_tools_map().values() if getattr(t, "source_name", None) == name
    )


def _needs_sqlite_normalize(src_type: str, config_data: dict[str, Any]) -> bool:
    """判断是否需要将 database 字段重命名为 path。"""
    return src_type == "sqlite" and "database" in config_data and "path" not in config_data


def _normalize_sqlite_config(src_type: str, config_data: dict[str, Any]) -> None:
    """sqlite 数据源: 将 frontend 传入的 database 字段重命名为 path。"""
    if not _needs_sqlite_normalize(src_type, config_data):
        return
    config_data["path"] = config_data.pop("database")


async def _build_source_or_raise(
    src_type: str,
    name: str,
    config_data: dict[str, Any],
    error_prefix: str,
):
    """构造并初始化 Source,失败时抛出对应的 HTTPException。"""
    try:
        return await _build_source(src_type, name, config_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=format_error_message(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{error_prefix}: {format_error_message(exc)}")


async def _persist_source(
    store, name: str, src_type: str, config_data: dict[str, Any]
) -> bool:
    """持久化数据源到 ConfigStore(仅在持久化模式下生效)。返回是否成功。"""
    if not is_store_usable(store):
        return True  # 无 store 视为成功(单机模式)
    try:
        await store.save_source(name, src_type, config_data)
        return True
    except Exception as exc:
        logger.warning("持久化数据源 %r 失败: %s", name, exc)
        return False


async def _build_source_response(
    rm,
    store,
    name: str,
    src_type: str,
    config_data: dict[str, Any],
) -> dict[str, Any]:
    """构造数据源响应 dict,持久化模式从 store 读取,回退到 config_data + rm。"""
    if is_store_usable(store):
        return await _source_to_dict(name, store=store)
    # 回退: 手动构造 source_config（config_data 缺少 name/type，补上）
    src_cfg = dict(config_data)
    src_cfg["name"] = name
    src_cfg["type"] = src_type
    result = await _source_to_dict(name, src_cfg)
    result["toolCount"] = _compute_tool_count_from_rm(rm, name)
    return result


async def _load_source_config_from_store(store, name: str) -> dict[str, Any] | None:
    """从 store 加载数据源配置,失败返回 None。"""
    if not is_store_usable(store):
        return None
    try:
        return await store.get_source(name)
    except Exception as exc:
        logger.warning("查询数据源 %r 失败: %s", name, exc)
        return None


def _load_source_config_from_rm(rm, name: str) -> dict[str, Any] | None:
    """从 rm 加载数据源配置,不存在时返回 None。"""
    if not rm.has_source(name):
        return None
    return rm.get_source_config(name) or {}


async def _load_source_config(rm, store, name: str) -> dict[str, Any] | None:
    """加载数据源配置: 优先用 store,回退到 rm;不存在时返回 None。"""
    src_cfg = await _load_source_config_from_store(store, name)
    if src_cfg is not None:
        return src_cfg
    return _load_source_config_from_rm(rm, name)


async def _get_source_for_action(rm, store, name: str):
    """多实例一致性辅助:获取 source 实例用于后续操作(test/query/tables)。

    流程:
      1. store 优先存在性检查;不存在直接返回 None(404)
      2. rm.get_source 命中直接返回(惰性初始化已建立连接池)
      3. rm 未命中但 store 命中:从 store 读取配置注入 rm,触发下次 get_source 惰性初始化

    多实例场景: 实例 A 创建数据源写入 store,实例 B 在 5s 热重载窗口内
    rm 内存未同步,通过本函数可从 store 立即获取并初始化 source(0 延迟)。
    """
    if not await _check_source_exists(rm, store, name):
        return None
    source = await rm.get_source(name)
    if source is not None:
        return source
    # rm 未缓存但 store 命中:主动注入配置触发惰性初始化
    src_cfg = await _load_source_config_from_store(store, name)
    if src_cfg is None:
        return None
    rm.add_source_config(name, src_cfg)
    return await rm.get_source(name)


async def _get_old_source_cfg(rm, store, name: str) -> dict[str, Any]:
    """获取更新/删除前的数据源配置(用于提取 system_id + environment)。

    多实例一致性: 优先从 store 获取(事实源),回退到 rm 内存。
    rm 未热重载时不能只读 rm,否则 sid/env 为空会误删同名数据源。
    """
    src_cfg = await _load_source_config(rm, store, name)
    return src_cfg or {}


def _get_password_from_cfg(src_cfg: dict[str, Any]) -> str:
    """从数据源配置中读取明文密码。"""
    return str(src_cfg.get("password", "") or "")


async def _get_password_ciphertext(store, src_cfg: dict[str, Any], name: str) -> str:
    """获取数据源密码密文,持久化模式从 store 读取,回退到内存明文密码。"""
    if not is_store_usable(store):
        return _get_password_from_cfg(src_cfg)
    try:
        sid, env = get_source_env_keys_from_cfg(src_cfg)
        return await store.get_source_password(name, sid, env)
    except Exception as exc:
        logger.warning("读取数据源 %r 密文失败: %s", name, exc)
        return _get_password_from_cfg(src_cfg)


def _filter_tool_names(existing: list[str], to_remove: list[str]) -> list[str]:
    """从 existing 中排除 to_remove 中的工具名。"""
    return [n for n in existing if n not in to_remove]


def _remove_tools_from_default_toolset(rm, tool_names: list[str]) -> None:
    """从默认 toolset(name=="")中移除指定工具名。"""
    default_ts = rm.get_toolset("")
    if default_ts is None:
        return
    default_ts.tool_names = _filter_tool_names(default_ts.tool_names, tool_names)


# ---------------------------------------------------------------------------
# _source_to_dict 及字段处理辅助函数
# ---------------------------------------------------------------------------


async def _compute_tool_count_from_store(store, name: str) -> int:
    """从 store 计算绑定到指定数据源的工具数量,失败返回 0。"""
    if store is None:
        return 0
    try:
        return await store.count_tools_by_source(name)
    except Exception:
        return 0


def _redact_password(value: Any, password_ciphertext: str) -> Any:
    """根据是否提供密文对 password 字段值进行脱敏/回填。"""
    if not value:
        return value
    if password_ciphertext:
        return password_ciphertext
    return "********"


def _build_source_base_dict(
    name: str, source_config: dict[str, Any], tool_count: int
) -> dict[str, Any]:
    """构造数据源响应的基础字段。"""
    return {
        "name": name,
        "type": source_config.get("type", "unknown"),
        "status": "connected",
        "latency": None,
        "error": None,
        "toolCount": tool_count,
    }


async def _source_to_dict(
    name: str,
    source_config: dict[str, Any] | None = None,
    *,
    password_ciphertext: str = "",
    store=None,
) -> dict[str, Any]:
    """转换单个数据源为响应 dict。

    Args:
        source_config: 数据源配置 dict（含 type/host/port/database/user/password/
            systemId/environment 等）。None 时从 store 查询（需要 store 参数）。
        password_ciphertext: 非空时直接作为 password 字段返回(供编辑场景使用,
            前端原样回传即可保持密码不变); 空字符串时密码字段统一脱敏为
            "********"(列表场景使用)。
        store: ConfigStore 实例，用于查询 tool_count 和 source_config。
    """
    if source_config is None:
        source_config = await _resolve_source_config(name, store)
    tool_count = await _compute_tool_count_from_store(store, name)
    result = _build_source_base_dict(name, source_config, tool_count)
    _apply_source_config_fields(result, source_config, password_ciphertext)
    return result


async def _resolve_source_config_from_store(name: str, store) -> dict[str, Any]:
    """从 store 读取数据源配置,失败返回空 dict。"""
    try:
        return await store.get_source(name) or {}
    except Exception:
        return {}


async def _resolve_source_config(name: str, store) -> dict[str, Any]:
    """从 store 读取数据源配置,失败或无 store 时返回空 dict。"""
    if store is None:
        return {}
    return await _resolve_source_config_from_store(name, store)


def _apply_source_config_field(
    result: dict[str, Any],
    k: str,
    v: Any,
    password_ciphertext: str,
) -> None:
    """将单个 source_config 字段写入 result,处理 password 脱敏。"""
    if k in ("name", "type"):
        return
    if k == "password":
        result[k] = _redact_password(v, password_ciphertext)
        return
    result[k] = v


def _apply_source_config_fields(
    result: dict[str, Any],
    source_config: dict[str, Any],
    password_ciphertext: str,
) -> None:
    """将 source_config 中的字段附加到 result,跳过 name/type,处理 password 脱敏。"""
    for k, v in source_config.items():
        _apply_source_config_field(result, k, v, password_ciphertext)


# ---------------------------------------------------------------------------
# 创建/更新数据源校验相关辅助函数
# ---------------------------------------------------------------------------


def _validate_required_fields(name: str, src_type: str) -> None:
    """校验必填字段 name / type。"""
    if not name or not src_type:
        raise HTTPException(status_code=400, detail="name and type are required")


def _validate_system_id(system_id: str) -> None:
    """校验 systemId 必填、长度不超过 10 位、仅含字母数字下划线横线。"""
    if not system_id:
        raise HTTPException(status_code=400, detail="systemId is required")
    if len(system_id) > 10:
        raise HTTPException(status_code=400, detail="systemId 长度不能超过 10 位")
    if not re.match(r"^[a-zA-Z0-9_-]+$", system_id):
        raise HTTPException(
            status_code=400,
            detail="systemId 只能包含字母、数字、下划线和横线",
        )


def _validate_environment(environment: str) -> None:
    """校验 environment 必填且属于预设环境列表。"""
    if not environment:
        raise HTTPException(status_code=400, detail="environment is required")
    if environment not in ENVIRONMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"environment 必须为 {ENVIRONMENTS} 之一",
        )


def _validate_source_type_whitelist(config, src_type: str) -> None:
    """数据源类型白名单校验: 防止绕过 UI 直接调用 API 创建被禁用类型。"""
    enabled = get_enabled_source_types(config)
    if not is_whitelist_active(enabled):
        return
    if src_type in enabled:
        return
    raise HTTPException(
        status_code=403,
        detail=f"数据源类型 {src_type!r} 未启用,请联系管理员调整 --enabled-source-types",
    )


def _validate_create_source_input(body: dict[str, Any], config) -> tuple[str, str, str, str]:
    """校验 create_source 入参,返回 (name, src_type, system_id, environment)。"""
    name = body.get("name", "")
    src_type = body.get("type", "")
    system_id = str(body.get("systemId", "") or "").strip()
    environment = str(body.get("environment", "") or "").strip()
    _validate_required_fields(name, src_type)
    _validate_name_param(name)
    _validate_system_id(system_id)
    _validate_environment(environment)
    _validate_source_type_whitelist(config, src_type)
    return name, src_type, system_id, environment


def _validate_name_param(name: str) -> None:
    """校验路径参数 name 格式:1-128 字符,仅 [a-zA-Z0-9_.-]。

    防止特殊字符注入日志、文件路径等非 SQL 场景。
    """
    from data_tool_mcp.config.loader import validate_resource_name

    try:
        validate_resource_name(name, "source")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=format_error_message(exc))


def _validate_update_source_input(
    body: dict[str, Any], config, old_cfg: dict[str, Any]
) -> str:
    """校验 update_source 入参,返回 src_type。

    name 来自路径参数(已在路由入口校验),type 可选(不传则沿用旧值)。
    systemId / environment / type 白名单必须校验,防止绕过创建时的约束。
    """
    src_type = body.get("type", old_cfg.get("type", ""))
    system_id = str(body.get("systemId", "") or "").strip()
    environment = str(body.get("environment", "") or "").strip()
    _validate_required_fields("", src_type)  # type 必填
    _validate_system_id(system_id)
    _validate_environment(environment)
    _validate_source_type_whitelist(config, src_type)
    return src_type


async def _check_source_uniqueness_in_rm(
    rm, name: str, system_id: str, environment: str
) -> None:
    """rm 内存模式下的数据源唯一性校验。"""
    for existing_name, existing_config in rm.get_all_source_configs().items():
        if _is_same_source(existing_name, existing_config, name, system_id, environment):
            raise HTTPException(
                status_code=409,
                detail=f"系统 {system_id} 环境 {environment} 下数据源 {name!r} 已存在",
            )


def _is_same_source(
    existing_name: str,
    existing_config: dict[str, Any],
    name: str,
    system_id: str,
    environment: str,
) -> bool:
    """判断已存在数据源是否与目标 (name, system_id, environment) 冲突。"""
    return (
        existing_name == name
        and existing_config.get("systemId") == system_id
        and existing_config.get("environment") == environment
    )


async def _check_source_uniqueness(
    rm, store, name: str, system_id: str, environment: str
) -> None:
    """数据源唯一性校验,优先用 store,回退到 rm。"""
    if not is_store_usable(store):
        await _check_source_uniqueness_in_rm(rm, name, system_id, environment)
        return
    existing = await store.get_source(name, system_id, environment)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"系统 {system_id} 环境 {environment} 下数据源 {name!r} 已存在",
        )


async def _save_source_to_store(
    store, name: str, src_type: str, config_data: dict[str, Any]
) -> bool:
    """保存数据源到 store,ValueError 转为 409,其他异常仅告警。返回是否成功。"""
    try:
        await store.save_source(name, src_type, config_data)
        return True
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=format_error_message(exc))
    except Exception as exc:
        logger.warning("持久化数据源 %r 失败: %s", name, exc)
        return False


async def _persist_new_source(
    store, name: str, src_type: str, config_data: dict[str, Any]
) -> bool:
    """持久化新建数据源,ValueError 转为 409,其他异常仅告警。返回是否成功。"""
    if not is_store_usable(store):
        return True  # 无 store 视为成功(单机模式)
    return await _save_source_to_store(store, name, src_type, config_data)


# ---------------------------------------------------------------------------
# 更新/删除数据源时清理旧工具的辅助函数
# ---------------------------------------------------------------------------


async def _clear_store_tools_for_source(
    store, rm, name: str, old_cfg: dict[str, Any]
) -> None:
    """同步清除 store 中该数据源的旧工具(随后 _auto_create_tools 会重新持久化)。"""
    if not is_store_usable(store):
        return
    try:
        old_sid, old_env = get_source_env_keys_from_cfg(old_cfg)
        await store.delete_tools_by_source(name, old_sid, old_env)
    except Exception as exc:
        logger.warning("清除数据源 %r 的旧工具失败: %s", name, exc)


async def _delete_old_source_record(
    store, name: str, old_cfg: dict[str, Any], new_config: dict[str, Any]
) -> None:
    """更新数据源时,若 system_id 或 environment 变更,删除旧的 store 记录。

    save_source 以 (name, system_id, environment) 为复合键做 upsert,
    当键值变更时会插入新记录而非更新,旧记录需手动清除。
    """
    if not is_store_usable(store):
        return
    old_sid, old_env = get_source_env_keys_from_cfg(old_cfg)
    new_sid = str(new_config.get("systemId", "") or "").strip()
    new_env = str(new_config.get("environment", "") or "").strip()
    if old_sid == new_sid and old_env == new_env:
        return
    try:
        await store.delete_source(name, old_sid, old_env)
    except Exception as exc:
        logger.warning("清除数据源 %r 的旧 store 记录失败: %s", name, exc)


async def _remove_tools_for_update(
    rm,
    store,
    name: str,
    old_cfg: dict[str, Any],
    old_tools: list[str],
) -> None:
    """更新数据源时清理旧工具:从 rm 内存 + 默认 toolset + store 中移除。"""
    for tname in old_tools:
        rm.remove_tool(tname)
    _remove_tools_from_default_toolset(rm, old_tools)
    # 同步清除 store 中该数据源的旧工具（随后 _auto_create_tools 会重新持久化）。
    # 旧工具仍属于更新前的 system_id + environment，需从旧 source config 中提取。
    await _clear_store_tools_for_source(store, rm, name, old_cfg)


async def _remove_source_tools(rm, store, name: str) -> None:
    """移除数据源绑定的所有工具:从 rm 内存 + 默认 toolset 中删除。"""
    removed = await _get_tools_for_source(rm, store, name)
    for tname in removed:
        rm.remove_tool(tname)
    _remove_tools_from_default_toolset(rm, removed)


async def _persist_delete_source(store, name: str, sid: str, env: str) -> None:
    """持久化删除数据源及其工具到 ConfigStore（单事务原子删除）。"""
    if not is_store_usable(store):
        return
    try:
        await store.delete_source_and_tools(name, sid, env)
    except Exception as exc:
        logger.warning("持久化删除数据源 %r 失败: %s", name, exc)


# ---------------------------------------------------------------------------
# 数据源响应构造辅助 (list/get/by_system)
# ---------------------------------------------------------------------------


def _get_source_config_or_empty(rm, name: str) -> dict[str, Any]:
    """从 rm 获取数据源配置,不存在时返回空 dict。"""
    return rm.get_source_config(name) or {}


def _build_config_data(body: dict[str, Any]) -> dict[str, Any]:
    """从请求 body 中提取 config_data(排除 name/type)。"""
    return {k: v for k, v in body.items() if k not in ("name", "type")}


async def _build_sources_response_from_store_list(
    sources_list: list[dict[str, Any]],
    store,
) -> list[dict[str, Any]]:
    """将 store 返回的数据源列表转为响应 dict 列表。"""
    result: list[dict[str, Any]] = []
    for s in sources_list:
        name = s.get("name")
        if not name:
            continue
        item = await _source_to_dict(name, s, store=store)
        result.append(item)
    return result


async def _build_rm_source_item(rm, name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """从 rm 内存构造单个数据源响应项,手动计算 tool_count。"""
    src_cfg = cfg or {}
    item = await _source_to_dict(name, src_cfg)
    item["toolCount"] = _compute_tool_count_from_rm(rm, name)
    return item


async def _build_sources_response_from_rm_filtered(
    rm,
    system_id: str,
) -> list[dict[str, Any]]:
    """从 rm 内存按 system_id 过滤并构造响应 dict 列表。"""
    configs = rm.get_all_source_configs()
    result: list[dict[str, Any]] = []
    for name, cfg in configs.items():
        sid, _ = extract_env_keys(cfg)
        if sid != system_id:
            continue
        result.append(await _build_rm_source_item(rm, name, cfg))
    return result


async def _build_sources_response_from_rm(rm) -> list[dict[str, Any]]:
    """从 rm 内存构造全部数据源的响应 dict 列表。"""
    configs = rm.get_all_source_configs()
    result: list[dict[str, Any]] = []
    for name, src_cfg in configs.items():
        src_cfg = src_cfg or {}
        item = await _source_to_dict(name, src_cfg)
        # 回退场景下手动计算 tool_count（_source_to_dict 在无 store 时返回 0）
        item["toolCount"] = _compute_tool_count_from_rm(rm, name)
        result.append(item)
    return result


async def _measure_source_connect_latency(source) -> dict[str, Any]:
    """测量 source.connect() 延迟,返回 ok/latency/error。"""
    import time

    try:
        start = time.monotonic()
        if hasattr(source, "connect"):
            await source.connect()
        latency = int((time.monotonic() - start) * 1000)
        return {"ok": True, "latency": latency, "error": None}
    except Exception as exc:
        return {"ok": False, "latency": 0, "error": format_error_message(exc)}


# ---------------------------------------------------------------------------
# source-types schema 过滤辅助
# ---------------------------------------------------------------------------


def _build_all_schemas_response() -> dict[str, dict[str, Any]]:
    """构造全部数据源类型 schema 响应。"""
    return {k: {"fields": v} for k, v in SOURCE_TYPE_SCHEMAS.items()}


def _build_filtered_schemas_response(enabled_set: set[str]) -> dict[str, dict[str, Any]]:
    """按白名单集合过滤 SOURCE_TYPE_SCHEMAS 响应。"""
    return {
        k: {"fields": v} for k, v in SOURCE_TYPE_SCHEMAS.items() if k in enabled_set
    }


def _filter_schemas_by_whitelist(enabled: list) -> dict[str, dict[str, Any]]:
    """按白名单过滤 SOURCE_TYPE_SCHEMAS,空列表表示全部启用。"""
    if not is_whitelist_active(enabled):
        return _build_all_schemas_response()
    return _build_filtered_schemas_response(set(enabled))
