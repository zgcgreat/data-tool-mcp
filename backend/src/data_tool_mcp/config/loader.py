"""Config loader — YAML files, prebuilt configs, or MySQL database.

Supports three config sources (listed by priority):
  1. YAML files (--config / --configs / --config-folder) — highest priority
  2. Database (--config-db-url) — set via env TOOLBOX_CONFIG_DB_URL
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


def substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} patterns in config values.

    Supports:
      ${PG_PASSWORD}          → os.environ["PG_PASSWORD"]
      ${PG_PASSWORD:-default} → os.environ.get("PG_PASSWORD", "default")

    Maps to Go: internal/util/util.go SubstituteEnvVars
    """
    if isinstance(value, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return env_val
            if default is not None:
                return default
            raise ValueError(
                f"environment variable {var_name!r} not set and no default provided"
            )
        return _ENV_PATTERN.sub(_replace, value)

    if isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    return value


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
    
    # Each document is a resource entry
    result: list[dict[str, Any]] = []
    for doc in docs:
        if doc is None:
            continue
        if isinstance(doc, dict):
            # Substitute env vars in this document
            doc = substitute_env_vars(doc)
            result.append(doc)
        elif isinstance(doc, list):
            # If it's a list, process each item
            for item in doc:
                if isinstance(item, dict):
                    item = substitute_env_vars(item)
                    result.append(item)
    return result


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two config dicts. override wins on conflicts.

    Maps to Go: cmd/internal/config.go mergeConfigs
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
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
    # 1. authRequired / useClientOAuth mutual exclusivity
    if config.get("authRequired") is not None and config.get("useClientOAuth") is True:
        raise ValueError(
            f"tool {name!r}: `authRequired` and `useClientOAuth` are mutually exclusive. "
            f"Choose only one authentication method"
        )

    # 2. scopesRequired validation
    scopes_required = config.get("scopesRequired")
    if scopes_required is not None:
        if not isinstance(scopes_required, list):
            raise ValueError(
                f"tool {name!r}: scopesRequired must be a list of strings"
            )
        # Validate each item is a string
        for i, scope in enumerate(scopes_required):
            if not isinstance(scope, str):
                raise ValueError(
                    f"tool {name!r}: scopesRequired[{i}] must be a string, got {type(scope).__name__}"
                )

    # 3. authRequired defaults to empty list if nil
    if config.get("authRequired") is None:
        config["authRequired"] = []

    # 4-5. valueFromParam reference validation
    parameters = config.get("parameters")
    if not isinstance(parameters, list):
        return

    # Build set of valid parameter names
    valid_param_names: set[str] = set()
    for p in parameters:
        if isinstance(p, dict):
            p_name = p.get("name", "")
            if isinstance(p_name, str) and p_name:
                valid_param_names.add(p_name)

    # Validate references
    for i, p in enumerate(parameters):
        if not isinstance(p, dict):
            continue
        p_name = p.get("name", "")
        ref_name = p.get("valueFromParam", "")
        if not isinstance(ref_name, str) or not ref_name:
            continue
        # Check if the referenced parameter exists
        if ref_name not in valid_param_names:
            raise ValueError(
                f"tool {name!r} config error: parameter {p_name!r} (index {i}) "
                f"references {ref_name!r} in the 'valueFromParam' field, "
                f"which is not a defined parameter"
            )
        # Check for self-reference
        if ref_name == p_name:
            raise ValueError(
                f"tool {name!r} config error: parameter {p_name!r} cannot copy value from itself"
            )


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


def load_config_from_file(path: Path) -> ToolboxFile:
    """Load and parse a single YAML config file into a ToolboxFile.

    Maps to Go: internal/server/config.go UnmarshalResourceConfig
    Supports multi-document YAML files where each document is a resource.
    """
    docs = load_yaml_file(path)
    sources = {}
    tools = {}
    toolsets = {}
    prompts = {}
    promptsets = {}
    embeddingModels = {}

    # Each document is a resource entry with kind/name fields
    for entry in docs:
        kind, name, config_data = parse_resource_entry(entry)
        if kind == "source":
            sources[name] = config_data
        elif kind == "tool":
            tools[name] = config_data
        elif kind == "toolset":
            toolsets[name] = config_data
        elif kind == "prompt":
            prompts[name] = config_data
        elif kind == "promptset":
            promptsets[name] = config_data
        elif kind == "embeddingModel":
            embeddingModels[name] = config_data
        else:
            # Unknown kind, skip with warning
            import warnings
            warnings.warn(f"Unknown resource kind {kind!r} for resource {name!r}")

    return ToolboxFile(
        sources=sources,
        tools=tools,
        toolsets=toolsets,
        prompts=prompts,
        promptsets=promptsets,
        embeddingModels=embeddingModels,
    )


def load_config_from_prebuilt(name: str) -> ToolboxFile:
    """Load and parse a prebuilt config by name into a ToolboxFile.

    Prebuilt configs use ``---`` document separators, so each document
    is parsed separately as a source, tool, or toolset entry.
    """
    docs = load_prebuilt_config(name)
    sources: dict[str, Any] = {}
    tools: dict[str, Any] = {}
    toolsets: dict[str, Any] = {}

    for entry in docs:
        kind, entry_name, config_data = parse_resource_entry(entry)
        if kind == "source":
            sources[entry_name] = substitute_env_vars(config_data)
        elif kind == "tool":
            tools[entry_name] = substitute_env_vars(config_data)
        elif kind == "toolset":
            toolsets[entry_name] = substitute_env_vars(config_data)

    return ToolboxFile(sources=sources, tools=tools, toolsets=toolsets)


async def load_config(server_config: ServerConfig) -> ServerConfig:
    """Load and merge all config files based on ServerConfig settings.

    Supports --prebuilt flag to load bundled configuration by name
    (comma-separated). Prebuilt configs are loaded first, then user
    config files are merged on top (user configs take precedence).

    Maps to Go: cmd/internal/options.go LoadConfig
    """
    merged = ToolboxFile()
    files_to_load: list[Path] = []

    # --prebuilt: comma-separated prebuilt config names (loaded first)
    if server_config.prebuilt:
        for name in server_config.prebuilt.split(","):
            name = name.strip()
            if name:
                tf = load_config_from_prebuilt(name)
                _merge_toolbox_file(merged, tf)

    # --config-db-url: load from MySQL database
    db_url = server_config.config_db_url or os.environ.get("TOOLBOX_CONFIG_DB_URL", "")
    if db_url:
        from data_tool_mcp.config.db_reader import load_config_from_db

        db_tf = await load_config_from_db(
            db_url=db_url,
            env_passwords_json=server_config.env_passwords,
        )
        merged.sources.update(db_tf.get("sources", {}))
        merged.tools.update(db_tf.get("tools", {}))
        merged.toolsets.update(db_tf.get("toolsets", {}))

    # --config single file
    if server_config.config_file:
        files_to_load.append(Path(server_config.config_file))

    # --configs multiple files
    for f in server_config.config_files:
        files_to_load.append(Path(f))

    # --config-folder: scan all .yaml/.yml files
    if server_config.config_folder:
        folder = Path(server_config.config_folder)
        if folder.is_dir():
            for ext in ("*.yaml", "*.yml"):
                for p in sorted(folder.glob(ext)):
                    files_to_load.append(p)

    # Load and merge user config files (override prebuilt)
    for f in files_to_load:
        if not f.exists():
            raise FileNotFoundError(f"config file not found: {f}")
        tf = load_config_from_file(f)
        _merge_toolbox_file(merged, tf)

    # Validate all resource names and tool configs
    # Maps to Go: internal/server/config.go validation in LoadConfig
    for name in merged.sources.keys():
        validate_resource_name(name, "source")
    for name, config in merged.tools.items():
        validate_resource_name(name, "tool")
        validate_tool_config(name, config)
    for name in merged.toolsets.keys():
        validate_resource_name(name, "toolset")
    for name in merged.prompts.keys():
        validate_resource_name(name, "prompt")
    for name in merged.promptsets.keys():
        validate_resource_name(name, "promptset")

    # Update server config with parsed data
    server_config.source_configs = merged.sources
    server_config.tool_configs = merged.tools
    server_config.toolset_configs = merged.toolsets
    server_config.prompt_configs = merged.prompts
    server_config.promptset_configs = merged.promptsets
    server_config.embedding_model_configs = merged.embeddingModels

    return server_config


def _merge_toolbox_file(target: ToolboxFile, source: ToolboxFile) -> None:
    """Merge a ToolboxFile into another. source entries override target."""
    target.sources.update(source.sources)
    target.tools.update(source.tools)
    target.toolsets.update(source.toolsets)
    target.prompts.update(source.prompts)
    target.promptsets.update(source.promptsets)
    target.embeddingModels.update(source.embeddingModels)
