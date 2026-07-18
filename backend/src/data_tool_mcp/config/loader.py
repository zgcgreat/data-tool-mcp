"""Config loader — YAML files, prebuilt configs, or MySQL database.

Supports three config sources (listed by priority):
  1. YAML files (--config / --configs / --config-folder) — highest priority
  2. Database (--config-db-url) — set via env DATA_TOOL_MCP_CONFIG_DB_URL
  3. Prebuilt configs (--prebuilt) — lowest priority, loaded first

When --config-db-url is set, the DB is the primary config source.
YAML files can still override specific entries on top of DB config.

Maps to Go: cmd/internal/config.go LoadConfig + mergeConfigs + ENV replacement
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from data_tool_mcp.config.models import ServerConfig, ToolboxFile
from data_tool_mcp.prebuiltconfigs import load_prebuilt_config

# Pattern for ${ENV_VAR} and ${ENV_VAR:-default} substitution
_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def _replace_env_match(match: re.Match) -> str:
    """根据 ${VAR} 或 ${VAR:-default} 匹配替换为环境变量值。"""
    var_name = match.group(1)
    default = match.group(2)
    env_val = os.environ.get(var_name)
    if env_val is not None:
        return env_val
    if default is not None:
        return default
    raise ValueError(f"environment variable {var_name!r} not set and no default provided")


def _substitute_in_dict(value: dict[str, Any]) -> dict[str, Any]:
    """对 dict 中的每个值递归替换环境变量。"""
    return {k: substitute_env_vars(v) for k, v in value.items()}


def _substitute_in_list(value: list[Any]) -> list[Any]:
    """对 list 中的每个元素递归替换环境变量。"""
    return [substitute_env_vars(item) for item in value]


def _substitute_container(value: Any) -> Any:
    """对 dict/list 容器递归替换环境变量；其他类型原样返回。"""
    if isinstance(value, dict):
        return _substitute_in_dict(value)
    if isinstance(value, list):
        return _substitute_in_list(value)
    return value


def substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} patterns in config values.

    Supports:
      ${PG_PASSWORD}          → os.environ["PG_PASSWORD"]
      ${PG_PASSWORD:-default} → os.environ.get("PG_PASSWORD", "default")

    Maps to Go: internal/util/util.go SubstituteEnvVars
    """
    if isinstance(value, str):
        return _ENV_PATTERN.sub(_replace_env_match, value)
    return _substitute_container(value)


def _should_deep_merge(base_val: Any, override_val: Any) -> bool:
    """判断是否需要递归深合并（两者都是 dict）。"""
    return isinstance(base_val, dict) and isinstance(override_val, dict)


def _merge_one(result: dict[str, Any], key: str, value: Any) -> None:
    """合并单个 key；若两边都是 dict 则递归深合并，否则用 override 覆盖。"""
    if key not in result:
        result[key] = value
        return
    if _should_deep_merge(result[key], value):
        result[key] = merge_configs(result[key], value)
        return
    result[key] = value


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two config dicts. override wins on conflicts.

    Maps to Go: cmd/internal/config.go mergeConfigs
    """
    result = base.copy()
    for key, value in override.items():
        _merge_one(result, key, value)
    return result


def _append_substituted(result: list[dict[str, Any]], item: Any) -> None:
    """对 dict 项进行环境变量替换后追加到 result；非 dict 忽略。"""
    if not isinstance(item, dict):
        return
    result.append(substitute_env_vars(item))


def _append_list_docs(result: list[dict[str, Any]], doc: list) -> None:
    """将 list 类型 document 中的 dict 项追加到 result。"""
    for item in doc:
        _append_substituted(result, item)


def _append_doc_value(result: list[dict[str, Any]], doc: Any) -> None:
    """根据 doc 类型分发追加逻辑。"""
    if isinstance(doc, dict):
        result.append(substitute_env_vars(doc))
        return
    if isinstance(doc, list):
        _append_list_docs(result, doc)


def _append_doc_items(result: list[dict[str, Any]], doc: Any) -> None:
    """将单个 YAML document 的项追加到 result；None 跳过。"""
    if doc is None:
        return
    _append_doc_value(result, doc)


def load_yaml_file(path: Path) -> list[dict[str, Any]]:
    """Load a YAML file and return a list of resource entries.

    Maps to Go: internal/server/config.go UnmarshalResourceConfig
    Supports multi-document YAML files (separated by ---).
    Each document is treated as a separate resource with kind/name fields.
    """
    content = path.read_text(encoding="utf-8")
    docs = list(yaml.safe_load_all(content))
    if not docs:
        return []

    result: list[dict[str, Any]] = []
    for doc in docs:
        _append_doc_items(result, doc)
    return result


# Valid resource name pattern — matches Go: internal/server/config.go NameValidation
# 1-128 characters, only [a-zA-Z0-9_.-]
_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{1,128}$")


def validate_resource_name(name: str, kind: str) -> None:
    """Validate a resource name matches Go's NameValidation rules.

    Maps to Go: internal/server/config.go NameValidation
    Rules: 1-128 characters, only [a-zA-Z0-9_.-]
    """
    if not _VALID_NAME_RE.match(name):
        raise ValueError(
            f"invalid {kind} name {name!r}: "
            f"must be 1-128 characters, only uppercase/lowercase ASCII letters, "
            f"digits, underscore, hyphen, and dot allowed"
        )


def _validate_auth_exclusivity(name: str, config: dict[str, Any]) -> None:
    """authRequired 与 useClientOAuth 互斥校验。"""
    if config.get("authRequired") is None:
        return
    if config.get("useClientOAuth") is True:
        raise ValueError(
            f"tool {name!r}: `authRequired` and `useClientOAuth` are mutually exclusive. "
            f"Choose only one authentication method"
        )


def _validate_scope_items(name: str, scopes: list) -> None:
    """校验每个 scope 都是字符串。"""
    for i, scope in enumerate(scopes):
        if not isinstance(scope, str):
            raise ValueError(
                f"tool {name!r}: scopesRequired[{i}] must be a string, got {type(scope).__name__}"
            )


def _validate_scopes_required(name: str, config: dict[str, Any]) -> None:
    """scopesRequired 必须是字符串列表。"""
    scopes_required = config.get("scopesRequired")
    if scopes_required is None:
        return
    if not isinstance(scopes_required, list):
        raise ValueError(f"tool {name!r}: scopesRequired must be a list of strings")
    _validate_scope_items(name, scopes_required)


def _add_param_name(names: set[str], p_name: Any) -> None:
    """将合法的参数名加入集合。"""
    if isinstance(p_name, str) and p_name:
        names.add(p_name)


def _collect_param_names(parameters: list) -> set[str]:
    """收集 parameters 中所有合法的 name。"""
    names: set[str] = set()
    for p in parameters:
        if not isinstance(p, dict):
            continue
        _add_param_name(names, p.get("name", ""))
    return names


def _is_valid_ref_name(ref_name: Any) -> bool:
    """valueFromParam 必须是非空字符串。"""
    return isinstance(ref_name, str) and bool(ref_name)


def _check_ref_exists(name: str, i: int, p_name: str, ref_name: str, valid_names: set[str]) -> None:
    """校验引用的参数名存在。"""
    if ref_name in valid_names:
        return
    raise ValueError(
        f"tool {name!r} config error: parameter {p_name!r} (index {i}) "
        f"references {ref_name!r} in the 'valueFromParam' field, "
        f"which is not a defined parameter"
    )


def _check_no_self_ref(name: str, p_name: str, ref_name: str) -> None:
    """校验参数不引用自身。"""
    if ref_name != p_name:
        return
    raise ValueError(
        f"tool {name!r} config error: parameter {p_name!r} cannot copy value from itself"
    )


def _validate_single_param_ref(name: str, i: int, p: dict, valid_names: set[str]) -> None:
    """校验单个参数的 valueFromParam 引用。"""
    p_name = p.get("name", "")
    ref_name = p.get("valueFromParam", "")
    if not _is_valid_ref_name(ref_name):
        return
    _check_ref_exists(name, i, p_name, ref_name, valid_names)
    _check_no_self_ref(name, p_name, ref_name)


def _validate_param_references(name: str, parameters: list, valid_names: set[str]) -> None:
    """校验 valueFromParam 引用是否合法且无自引用。"""
    for i, p in enumerate(parameters):
        if not isinstance(p, dict):
            continue
        _validate_single_param_ref(name, i, p, valid_names)


def validate_tool_config(name: str, config: dict[str, Any]) -> None:
    """Validate a tool config entry — matches Go's UnmarshalYAMLToolConfig checks.

    Maps to Go: internal/server/config.go UnmarshalYAMLToolConfig
    Checks:
      1. authRequired and useClientOAuth are mutually exclusive
      2. scopesRequired must be a list of strings if present
      3. authRequired defaults to empty list if nil
      4. valueFromParam references must point to existing parameters
      5. valueFromParam cannot reference itself
    """
    _validate_auth_exclusivity(name, config)
    _validate_scopes_required(name, config)

    # authRequired 默认空列表
    if config.get("authRequired") is None:
        config["authRequired"] = []

    parameters = config.get("parameters")
    if not isinstance(parameters, list):
        return
    valid_names = _collect_param_names(parameters)
    _validate_param_references(name, parameters, valid_names)


def parse_resource_entry(raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Parse a single source/tool/toolset entry from YAML.

    Returns (kind, name, config_data) tuple.
    The 'kind' field determines if it's a source, tool, or toolset.
    The 'type' field within config_data identifies the specific driver.
    """
    kind = raw.get("kind", "")
    name = raw.get("name", "")
    if not kind or not name:
        raise ValueError(f"config entry missing 'kind' or 'name': {raw}")
    return kind, name, raw


def _warn_unknown_kind(kind: str, name: str) -> None:
    """对未知资源类型发出警告。"""
    import warnings

    warnings.warn(f"Unknown resource kind {kind!r} for resource {name!r}")


_FILE_KIND_TO_BUCKET = {
    "source": "sources",
    "tool": "tools",
    "toolset": "toolsets",
    "prompt": "prompts",
    "promptset": "promptsets",
    "embeddingModel": "embeddingModels",
}


def load_config_from_file(path: Path) -> ToolboxFile:
    """Load and parse a single YAML config file into a ToolboxFile.

    Maps to Go: internal/server/config.go UnmarshalResourceConfig
    Supports multi-document YAML files where each document is a resource.
    """
    docs = load_yaml_file(path)
    buckets: dict[str, dict[str, Any]] = {
        "sources": {},
        "tools": {},
        "toolsets": {},
        "prompts": {},
        "promptsets": {},
        "embeddingModels": {},
    }

    for entry in docs:
        kind, name, config_data = parse_resource_entry(entry)
        bucket_key = _FILE_KIND_TO_BUCKET.get(kind)
        if bucket_key is None:
            _warn_unknown_kind(kind, name)
            continue
        buckets[bucket_key][name] = config_data

    return ToolboxFile(**buckets)


_PREBUILT_KIND_TO_BUCKET = {
    "source": "sources",
    "tool": "tools",
    "toolset": "toolsets",
}


def load_config_from_prebuilt(name: str) -> ToolboxFile:
    """Load and parse a prebuilt config by name into a ToolboxFile.

    Prebuilt configs use ``---`` document separators, so each document
    is parsed separately as a source, tool, or toolset entry.
    """
    docs = load_prebuilt_config(name)
    buckets: dict[str, dict[str, Any]] = {
        "sources": {},
        "tools": {},
        "toolsets": {},
    }

    for entry in docs:
        kind, entry_name, config_data = parse_resource_entry(entry)
        bucket_key = _PREBUILT_KIND_TO_BUCKET.get(kind)
        if bucket_key is None:
            continue
        buckets[bucket_key][entry_name] = substitute_env_vars(config_data)

    return ToolboxFile(**buckets)


def _merge_prebuilt_configs(merged: ToolboxFile, prebuilt: str) -> None:
    """加载并合并 comma 分隔的预置配置名。"""
    for name in prebuilt.split(","):
        name = name.strip()
        if not name:
            continue
        tf = load_config_from_prebuilt(name)
        _merge_toolbox_file(merged, tf)


async def _merge_db_config(merged: ToolboxFile, server_config: ServerConfig) -> None:
    """从 MySQL 数据库加载配置并合并到 merged。"""
    db_url = server_config.config_db_url or os.environ.get("DATA_TOOL_MCP_CONFIG_DB_URL", "")
    if not db_url:
        return
    from data_tool_mcp.config.db_reader import load_config_from_db

    db_tf = await load_config_from_db(
        db_url=db_url,
        env_passwords_json=server_config.env_passwords,
    )
    merged.sources.update(db_tf.get("sources", {}))
    merged.tools.update(db_tf.get("tools", {}))
    merged.toolsets.update(db_tf.get("toolsets", {}))


def _collect_yaml_files(folder: Path) -> list[Path]:
    """扫描文件夹下所有 .yaml/.yml 文件。"""
    collected: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        collected.extend(sorted(folder.glob(ext)))
    return collected


def _add_single_config_file(files: list[Path], config_file: str) -> None:
    """添加 --config 单文件。"""
    if config_file:
        files.append(Path(config_file))


def _add_multiple_config_files(files: list[Path], config_files: list[str]) -> None:
    """添加 --configs 多文件。"""
    for f in config_files:
        files.append(Path(f))


def _add_folder_config_files(files: list[Path], config_folder: str) -> None:
    """添加 --config-folder 下的所有 YAML 文件。"""
    if not config_folder:
        return
    folder = Path(config_folder)
    if not folder.is_dir():
        return
    files.extend(_collect_yaml_files(folder))


def _collect_config_files(server_config: ServerConfig) -> list[Path]:
    """收集用户指定的所有配置文件路径。"""
    files: list[Path] = []
    _add_single_config_file(files, server_config.config_file)
    _add_multiple_config_files(files, server_config.config_files)
    _add_folder_config_files(files, server_config.config_folder)
    return files


def _load_and_merge_files(merged: ToolboxFile, files: list[Path]) -> None:
    """加载并合并所有用户配置文件（覆盖预置配置）。"""
    for f in files:
        if not f.exists():
            raise FileNotFoundError(f"config file not found: {f}")
        tf = load_config_from_file(f)
        _merge_toolbox_file(merged, tf)


def _validate_named_resources(items: dict[str, Any], kind: str) -> None:
    """校验资源名称合法性。"""
    for name in items:
        validate_resource_name(name, kind)


def _validate_tool_configs(tools: dict[str, Any]) -> None:
    """校验工具名称和配置。"""
    for name, config in tools.items():
        validate_resource_name(name, "tool")
        validate_tool_config(name, config)


def _validate_resource_names(merged: ToolboxFile) -> None:
    """校验所有资源名称和工具配置。"""
    _validate_named_resources(merged.sources, "source")
    _validate_tool_configs(merged.tools)
    _validate_named_resources(merged.toolsets, "toolset")
    _validate_named_resources(merged.prompts, "prompt")
    _validate_named_resources(merged.promptsets, "promptset")


def _apply_configs_to_server(server_config: ServerConfig, merged: ToolboxFile) -> None:
    """将合并后的配置写回 server_config。"""
    server_config.source_configs = merged.sources
    server_config.tool_configs = merged.tools
    server_config.toolset_configs = merged.toolsets
    server_config.prompt_configs = merged.prompts
    server_config.promptset_configs = merged.promptsets
    server_config.embedding_model_configs = merged.embeddingModels


async def load_config(server_config: ServerConfig) -> ServerConfig:
    """Load and merge all config files based on ServerConfig settings.

    Supports --prebuilt flag to load bundled configuration by name
    (comma-separated). Prebuilt configs are loaded first, then user
    config files are merged on top (user configs take precedence).

    Maps to Go: cmd/internal/options.go LoadConfig
    """
    merged = ToolboxFile()

    if server_config.prebuilt:
        _merge_prebuilt_configs(merged, server_config.prebuilt)

    await _merge_db_config(merged, server_config)

    files = _collect_config_files(server_config)
    _load_and_merge_files(merged, files)

    _validate_resource_names(merged)
    _apply_configs_to_server(server_config, merged)

    return server_config


def _merge_toolbox_file(target: ToolboxFile, source: ToolboxFile) -> None:
    """Merge a ToolboxFile into another. source entries override target."""
    target.sources.update(source.sources)
    target.tools.update(source.tools)
    target.toolsets.update(source.toolsets)
    target.prompts.update(source.prompts)
    target.promptsets.update(source.promptsets)
    target.embeddingModels.update(source.embeddingModels)
