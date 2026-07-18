"""Tool base classes and decorator registry.

Maps to Go: internal/tools/tools.go
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from data_tool_mcp.sources import Source
from data_tool_mcp.tools.template import render_sql_template


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass
class ParameterManifest:
    """Parameter description sent to MCP clients.

    Maps to Go: internal/util/parameters/parameters.go ParameterManifest
    """

    name: str
    type: str  # "string", "number", "integer", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    default: Any = None
    items: dict[str, Any] | None = None  # for array type
    allowed_values: list[Any] | None = None
    excluded_values: list[Any] | None = None


@dataclass
class ToolAnnotations:
    """Maps to Go ToolAnnotations.

    MCP 2025-06-18+ specification: clients use these hints to decide
    whether to require user confirmation before invoking a tool.
    """

    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None
    read_only_hint: bool | None = None

    def to_dict(self) -> dict[str, bool]:
        """Serialize non-None annotations for MCP responses."""
        pairs = {
            "destructiveHint": self.destructive_hint,
            "idempotentHint": self.idempotent_hint,
            "openWorldHint": self.open_world_hint,
            "readOnlyHint": self.read_only_hint,
        }
        return {k: v for k, v in pairs.items() if v is not None}


def read_only_annotations() -> ToolAnnotations:
    """Create default annotations for a read-only tool.

    Maps to Go: NewReadOnlyAnnotations()
    """
    return ToolAnnotations(read_only_hint=True)


def destructive_annotations() -> ToolAnnotations:
    """Create default annotations for a destructive tool.

    Maps to Go: NewDestructiveAnnotations()
    """
    return ToolAnnotations(read_only_hint=False, destructive_hint=True)


def write_annotations() -> ToolAnnotations:
    """Create default annotations for a non-destructive write tool.

    Maps to Go: NewWriteAnnotations()
    """
    return ToolAnnotations(read_only_hint=False)


@dataclass
class ToolManifest:
    """Tool description sent to MCP clients.

    Maps to Go Manifest struct.
    """

    description: str
    parameters: list[ParameterManifest]
    auth_required: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool name validation
# ---------------------------------------------------------------------------

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]*$")


def validate_name(name: str) -> bool:
    """Validate a tool or source name.

    Maps to Go: tools.IsValidName()
    Rules: only [a-zA-Z0-9_-], no length limit, no dots
    """
    return bool(_VALID_NAME_RE.match(name))


# ---------------------------------------------------------------------------
# ToolMeta (read-only view of config)
# ---------------------------------------------------------------------------


class ToolMeta(Protocol):
    """Protocol for the config fields that BaseTool reads.

    Maps to Go ToolMeta interface.
    """

    name: str
    description: str
    auth_required: list[str]
    scopes_required: list[str]


# ---------------------------------------------------------------------------
# ConfigBase
# ---------------------------------------------------------------------------


@dataclass
class ConfigBase:
    """Shared YAML fields that every tool's Config has.

    Maps to Go ConfigBase struct.
    """

    name: str
    description: str = ""
    auth_required: list[str] = field(default_factory=list)
    scopes_required: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool interface
# ---------------------------------------------------------------------------


class Tool(ABC):
    """Tool interface.

    Maps to Go Tool interface (14 methods). Python provides default
    implementations via BaseTool for methods that have sensible defaults.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """返回工具名称。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """返回工具描述。"""
        ...

    @property
    @abstractmethod
    def auth_required(self) -> list[str]:
        """返回工具所需的授权服务列表。"""
        ...

    @abstractmethod
    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: "SourceProvider | None" = None,
        access_token: str = "",
    ) -> Any:
        """Execute the tool with the given parameters.

        Maps to Go: Invoke(ctx, SourceProvider, ParamValues, AccessToken) (any, ToolboxError)

        Args:
            params: Tool invocation parameters from the MCP client.
            source_provider: Provides access to configured sources (e.g. databases).
            access_token: OAuth access token if auth is required.
        """
        ...

    @abstractmethod
    def manifest(self, sources: dict[str, Source] | None = None) -> ToolManifest:
        """Return the tool manifest for MCP clients.

        Maps to Go: Manifest(map[string]sources.Source) (Manifest, error)
        """
        ...

    @abstractmethod
    def get_annotations(self) -> ToolAnnotations | None:
        """Return the tool's annotations.

        Maps to Go: GetAnnotations() *ToolAnnotations
        MCP clients use annotations to decide whether to require user
        confirmation (e.g., destructiveHint → always confirm).
        """
        ...

    @abstractmethod
    def static_manifest(self) -> ToolManifest:
        """Return manifest without source resolution (for offline generation).

        Maps to Go: StaticManifest() Manifest
        """
        ...

    @abstractmethod
    def get_parameters(self, sources: dict[str, Source] | None = None) -> list[ParameterManifest]:
        """Return the tool's parameter definitions.

        Maps to Go: GetParameters(map[string]sources.Source) (Parameters, error)
        Dynamic tools override this to resolve params against a live source.
        """
        ...

    def authorized(self, verified_auth_services: list[str]) -> bool:
        """Check if the tool is authorized given verified auth services.

        Maps to Go: Authorized([]string) bool
        """
        if not self.auth_required:
            return True
        return any(a in verified_auth_services for a in self.auth_required)

    @property
    def scopes_required(self) -> list[str]:
        """Return OAuth scopes required by this tool.

        Maps to Go: GetScopesRequired() []string
        """
        return []

    def requires_client_authorization(
        self, source_provider: "SourceProvider | None" = None
    ) -> bool:
        """Check if the tool requires client-provided authorization.

        Maps to Go: RequiresClientAuthorization(SourceProvider) (bool, error)
        Default: False (no client auth needed for enterprise intranet).
        """
        return False

    def get_auth_token_header_name(self, source_provider: "SourceProvider | None" = None) -> str:
        """Return the header name for the auth token.

        Maps to Go: GetAuthTokenHeaderName(SourceProvider) (string, error)
        Default: "Authorization"
        """
        return "Authorization"

    def to_config(self) -> "ToolConfig":
        """Convert back to config. Optional override.

        Maps to Go: ToConfig() ToolConfig
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ToolConfig interface
# ---------------------------------------------------------------------------


class ToolConfig(ABC):
    """Tool configuration interface.

    Maps to Go ToolConfig interface.
    """

    @property
    @abstractmethod
    def tool_type(self) -> str:
        """Return the tool type identifier (e.g., 'postgres-exec-sql')."""
        ...

    @abstractmethod
    async def initialize(self) -> Tool:
        """Create and initialize a Tool from this config."""
        ...


# ---------------------------------------------------------------------------
# BaseTool — default implementations
# ---------------------------------------------------------------------------


class BaseTool(Tool):
    """Provides default implementations of Tool methods.

    Maps to Go BaseTool[T ToolMeta] struct.
    Concrete tools embed this and override only what they need.
    """

    def __init__(
        self,
        cfg: ConfigBase,
        annotations: ToolAnnotations | None = None,
        metadata: ToolManifest | None = None,
        static_parameters: list[ParameterManifest] | None = None,
    ):
        """初始化工具配置。"""
        self._cfg = cfg
        self._annotations = annotations
        self._metadata = metadata
        self._static_parameters = static_parameters or []

    @property
    def name(self) -> str:
        """返回工具名称。"""
        return self._cfg.name

    @property
    def description(self) -> str:
        """返回工具描述。"""
        return self._cfg.description

    @property
    def source_name(self) -> str | None:
        """Return the bound source name, or None for source-less tools."""
        return getattr(self, "_source_name", None)

    @property
    def auth_required(self) -> list[str]:
        """返回工具所需的授权服务列表。"""
        return self._cfg.auth_required

    @property
    def scopes_required(self) -> list[str]:
        """返回工具所需的 OAuth 作用域列表。"""
        return self._cfg.scopes_required

    def manifest(self, sources: dict[str, Source] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        if self._metadata:
            return self._metadata
        return ToolManifest(
            description=self.description,
            parameters=[],
            auth_required=self.auth_required,
        )

    def static_manifest(self) -> ToolManifest:
        """Return manifest without source resolution (for offline generation).

        Maps to Go: BaseTool.StaticManifest() Manifest
        """
        return self.manifest(sources=None)

    def get_annotations(self) -> ToolAnnotations | None:
        """Return the tool's annotations.

        Maps to Go: BaseTool.GetAnnotations() *ToolAnnotations
        """
        return self._annotations

    def get_parameters(self, sources: dict[str, Source] | None = None) -> list[ParameterManifest]:
        """Return the tool's parameter definitions.

        Maps to Go: BaseTool.GetParameters() Parameters
        Dynamic tools override this to resolve params against a live source.
        """
        return self._static_parameters


# ---------------------------------------------------------------------------
# SourceProvider
# ---------------------------------------------------------------------------


class SourceProvider(Protocol):
    """Minimal view of ResourceManager that Tool package needs.

    Maps to Go SourceProvider interface.

    方案 C: get_source 改为 async(cache-aside + 惰性初始化)。
    调用方必须 try/finally release_source 释放引用计数。
    """

    async def get_source(self, source_name: str) -> Source | None:
        """根据名称获取 source 实例。"""
        ...

    async def release_source(self, source_name: str) -> None:
        """释放 source 的引用计数。"""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_tool_registry: dict[str, type[ToolConfig]] = {}
_tool_aliases: dict[str, str] = {}  # alias -> canonical name


def register_tool(tool_type: str):
    """Decorator: register a ToolConfig class for a given tool type.

    Raises ValueError if the tool type is already registered (matching Go's
    panic-on-duplicate behavior).  This prevents accidental shadowing of
    core tools by extended modules.

    Usage:
        @register_tool("postgres-execute-sql")
        class ExecSQLToolConfig(ToolConfig):
            ...
    """

    def decorator(cls: type[ToolConfig]) -> type[ToolConfig]:
        """将 ToolConfig 子类注册到全局注册表。"""
        if tool_type in _tool_registry:
            existing = _tool_registry[tool_type]
            raise ValueError(
                f"tool type {tool_type!r} already registered by {existing.__name__}; "
                f"cannot re-register as {cls.__name__}"
            )
        _tool_registry[tool_type] = cls
        return cls

    return decorator


def _check_tool_alias_conflict(alias: str) -> None:
    """检查别名是否与已注册的工具类型或别名冲突。"""
    if alias in _tool_registry:
        raise ValueError(
            f"cannot register alias {alias!r}: already registered as a primary tool type"
        )
    if alias in _tool_aliases:
        existing_target = _tool_aliases[alias]
        raise ValueError(f"alias {alias!r} already registered -> {existing_target!r}")


def register_tool_alias(alias: str, canonical: str):
    """Register an alias for an existing tool type.

    This allows backward compatibility: old names still resolve to the
    same ToolConfig class.  Raises ValueError if the alias is already
    registered (as a primary name or another alias).
    """
    _check_tool_alias_conflict(alias)
    if canonical not in _tool_registry:
        raise ValueError(
            f"cannot register alias {alias!r} -> {canonical!r}: "
            f"canonical tool type {canonical!r} is not registered"
        )
    _tool_aliases[alias] = canonical


def get_tool_config_class(tool_type: str) -> type[ToolConfig]:
    """Look up a registered ToolConfig class by type, resolving aliases."""
    cls = _tool_registry.get(tool_type)
    if cls is None:
        cls = _tool_registry.get(_tool_aliases.get(tool_type, ""))
    if cls is None:
        raise ValueError(f"unknown tool type: {tool_type!r}")
    return cls


def list_tool_types() -> list[str]:
    """Return all registered tool type names, including aliases."""
    return sorted(set(_tool_registry.keys()) | set(_tool_aliases.keys()))


def decode_tool_config(tool_type: str, name: str, config_data: dict[str, Any]) -> ToolConfig:
    """Decode a tool config from raw dict data using the registered class."""
    cls = get_tool_config_class(tool_type)
    return cls.from_dict(name, config_data)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 共享辅助函数 — 供各 tool 模块复用,降低圈复杂度
# ---------------------------------------------------------------------------


def _source_resolution_error(
    source_name: str, tool_name: str, source: Any, expected_type: type | None = None
) -> Exception:
    """根据 source 解析结果构造对应的异常对象。"""
    if source is None:
        return ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    type_hint = expected_type.__name__ if expected_type else "expected"
    return TypeError(f"source {source_name!r} is not a {type_hint} source")


async def _release_and_raise(
    source_provider: "SourceProvider", source_name: str, exc: Exception
) -> None:
    """释放 source 引用并抛出指定异常。"""
    await source_provider.release_source(source_name)
    raise exc


async def _get_typed_source_async(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
    expected_type: type,
) -> Any:
    """从 SourceProvider 解析指定类型的 source,失败时释放引用并抛错。"""
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if isinstance(source, expected_type):
        return source
    exc = _source_resolution_error(source_name, tool_name, source, expected_type)
    await _release_and_raise(source_provider, source_name, exc)


def _param_manifest_from_dict(p: dict[str, Any]) -> ParameterManifest:
    """从字典构造单个 ParameterManifest。"""
    return ParameterManifest(
        name=p.get("name", ""),
        type=p.get("type", "string"),
        description=p.get("description", ""),
        required=p.get("required", False),
        default=p.get("default"),
    )


def _manifests_from_dicts(param_defs: list[dict[str, Any]]) -> list[ParameterManifest]:
    """将字典列表转为 ParameterManifest 列表。"""
    return [_param_manifest_from_dict(p) for p in param_defs]


def _build_sql_tool_parameters(
    param_defs: list[dict[str, Any]],
    statement: str,
    sql_description: str,
) -> list[ParameterManifest]:
    """根据 param_defs/statement 构建参数清单。"""
    if param_defs:
        return _manifests_from_dicts(param_defs)
    if not statement:
        return [
            ParameterManifest(name="sql", type="string", description=sql_description, required=True)
        ]
    return []


def _bind_param_values(parameters: list[dict[str, Any]], params: dict[str, Any]) -> list[Any]:
    """根据 parameters 定义从 params 提取绑定值列表。"""
    return [params.get(p["name"]) for p in parameters]


async def _execute_user_sql(source: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    """执行用户在 params['sql'] 中提供的 SQL。"""
    sql = params.get("sql", "")
    if not sql:
        raise ValueError("missing 'sql' parameter")
    return await source.execute_sql(sql)


async def _execute_with_statement(
    source: Any,
    statement: str,
    template_parameters: list[dict[str, Any]],
    parameters: list[dict[str, Any]],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """statement 已存在,根据参数模式选择执行方式。"""
    if template_parameters:
        return await source.execute_sql(render_sql_template(statement, params))
    if parameters:
        return await source.execute_sql(statement, _bind_param_values(parameters, params))
    return await source.execute_sql(statement)


async def _execute_sql_with_modes(
    source: Any,
    statement: str,
    template_parameters: list[dict[str, Any]],
    parameters: list[dict[str, Any]],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """根据 statement/templateParameters/parameters 模式执行 SQL。"""
    if not statement:
        return await _execute_user_sql(source, params)
    return await _execute_with_statement(source, statement, template_parameters, parameters, params)
