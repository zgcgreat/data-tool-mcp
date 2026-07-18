"""admin 路由共享的小型辅助函数。

从 admin/router.py 拆分而来，集中存放被多个 helper 模块和 router.py
共同使用的"基础设施"辅助：
  - 日志器
  - 从 Request 取 ResourceManager / ServerConfig
  - ConfigStore 可用性检查
  - systemId / environment 提取
  - 数据源类型白名单检查
  - 从 list[dict] 提取 name 列表
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request

logger = logging.getLogger("data_tool_mcp.admin")


def get_rm(request: Request):
    """从 request.app.state 获取 ResourceManager。"""
    return request.app.state.resource_manager


def get_config(request: Request):
    """从 request.app.state 获取 ServerConfig。"""
    return request.app.state.config


def is_store_usable(store) -> bool:
    """store 非 None 且为持久化存储时返回 True。"""
    return store is not None and store.is_persistent


def extract_env_keys(src_cfg: dict[str, Any]) -> tuple[str, str]:
    """从数据源配置中提取 (systemId, environment),均去除空白。"""
    system_id = str(src_cfg.get("systemId", "") or "").strip()
    environment = str(src_cfg.get("environment", "") or "").strip()
    return system_id, environment


def get_source_env_keys_from_cfg(src_cfg: dict[str, Any]) -> tuple[str, str]:
    """从 source 配置中提取 (systemId, environment)。"""
    system_id = str(src_cfg.get("systemId", "") or "").strip()
    environment = str(src_cfg.get("environment", "") or "").strip()
    return system_id, environment


def get_enabled_source_types(config) -> list:
    """从 config 中读取已启用的数据源类型列表。"""
    return getattr(config, "enabled_source_types", []) or []


def is_whitelist_active(enabled: Any) -> bool:
    """判断白名单是否生效: 非空 list 表示启用白名单。"""
    return isinstance(enabled, list) and bool(enabled)


def extract_source_names(items) -> list[str]:
    """从 items 中提取非空 name 列表。"""
    return [s["name"] for s in items if s.get("name")]
