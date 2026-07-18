"""Prompt base classes, message types, argument types, promptsets, and decorator registry.

Maps to Go:
  internal/prompts/prompts.go: PromptConfig + Prompt interface + registry
  internal/prompts/arguments.go: Argument definition
  internal/prompts/messages.go: Message (Role + Content)
  internal/prompts/promptsets.go: PromptsetConfig + Promptset + Manifest
  internal/prompts/custom/custom.go: Custom prompt implementation
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.tools.base import validate_name


# ---------------------------------------------------------------------------
# Argument (maps to Go Argument struct)
# ---------------------------------------------------------------------------


@dataclass
class ArgumentManifest:
    """Argument description sent to MCP clients.

    Maps to Go: parameters.ParameterManifest
    """

    name: str
    description: str = ""
    required: bool = True


@dataclass
class Argument:
    """Prompt argument definition.

    Maps to Go: Argument struct
    """

    name: str
    description: str = ""
    required: bool = True

    def manifest(self) -> ArgumentManifest:
        """生成参数的 manifest 描述。"""
        return ArgumentManifest(
            name=self.name,
            description=self.description,
            required=self.required,
        )


# ---------------------------------------------------------------------------
# Message (maps to Go Message struct)
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A message in a prompt's content.

    Maps to Go: Message struct with Role + Content + template substitution.
    """

    role: str  # "user" or "assistant"
    content: str  # May contain {{param}} template placeholders

    def substitute(self, params: dict[str, Any]) -> Message:
        """Replace {{param}} placeholders with actual values.

        Maps to Go: Message.SubstituteParams
        """
        content = self.content
        for key, value in params.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
        return Message(role=self.role, content=content)


# ---------------------------------------------------------------------------
# Prompt Manifest
# ---------------------------------------------------------------------------


@dataclass
class PromptManifest:
    """Prompt description sent to MCP clients.

    Maps to Go: prompts.Manifest
    """

    description: str
    arguments: list[ArgumentManifest] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt interface
# ---------------------------------------------------------------------------


class PromptConfig(ABC):
    """Prompt configuration interface.

    Maps to Go: PromptConfig interface.
    """

    @property
    @abstractmethod
    def prompt_type(self) -> str:
        """Return the prompt type identifier."""
        ...

    @abstractmethod
    async def initialize(self) -> Prompt:
        """Create and initialize a Prompt from this config."""
        ...


class Prompt(ABC):
    """Prompt interface.

    Maps to Go: Prompt interface (6 methods).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """返回 prompt 名称。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """返回 prompt 描述。"""
        ...

    @abstractmethod
    def get_arguments(self) -> list[Argument]:
        """Return the prompt's argument definitions.

        Maps to Go: GetArguments() Arguments
        """
        ...

    @abstractmethod
    def manifest(self) -> PromptManifest:
        """Return the prompt manifest for MCP clients.

        Maps to Go: Manifest() Manifest
        """
        ...

    @abstractmethod
    def substitute_params(self, param_values: dict[str, Any]) -> dict[str, Any]:
        """Substitute parameters into prompt messages.

        Maps to Go: SubstituteParams(ParamValues) (any, error)
        Returns the MCP prompt/get response format:
        {
            "description": "...",
            "messages": [{"role": "user/assistant", "content": {"type": "text", "text": "..."}}]
        }
        """
        ...

    @abstractmethod
    def to_config(self) -> PromptConfig:
        """Convert back to config.

        Maps to Go: ToConfig() PromptConfig
        """
        ...


# ---------------------------------------------------------------------------
# Custom Prompt implementation
# ---------------------------------------------------------------------------


class CustomPrompt(Prompt):
    """Custom prompt with user-defined messages and arguments.

    Maps to Go: custom/custom.go CustomPrompt
    """

    def __init__(
        self,
        name: str,
        description: str,
        messages: list[Message],
        arguments: list[Argument] | None = None,
    ):
        """初始化实例。"""
        self._name = name
        self._description = description
        self._messages = messages
        self._arguments = arguments or []

    @property
    def name(self) -> str:
        """返回 prompt 名称。"""
        return self._name

    @property
    def description(self) -> str:
        """返回 prompt 描述。"""
        return self._description

    def get_arguments(self) -> list[Argument]:
        """返回 prompt 的参数定义列表。"""
        return self._arguments

    def manifest(self) -> PromptManifest:
        """生成 prompt 的 manifest 描述。"""
        return PromptManifest(
            description=self._description,
            arguments=[a.manifest() for a in self._arguments],
        )

    def substitute_params(self, param_values: dict[str, Any]) -> dict[str, Any]:
        """Substitute parameters into messages and return MCP response format."""
        substituted_messages = [msg.substitute(param_values) for msg in self._messages]
        return {
            "description": self._description,
            "messages": [
                {
                    "role": msg.role,
                    "content": {"type": "text", "text": msg.content},
                }
                for msg in substituted_messages
            ],
        }

    def to_config(self) -> CustomPromptConfig:
        """将 prompt 转换回配置对象。"""
        return CustomPromptConfig(
            name=self._name,
            description=self._description,
            messages=self._messages,
            arguments=self._arguments,
        )


@dataclass
class CustomPromptConfig(PromptConfig):
    """Configuration for a custom prompt.

    Maps to Go: custom/custom.go CustomPromptConfig
    """

    name: str = ""
    description: str = ""
    messages: list[Message] = field(default_factory=list)
    arguments: list[Argument] = field(default_factory=list)

    @property
    def prompt_type(self) -> str:
        """返回 prompt 类型标识。"""
        return "custom"

    async def initialize(self) -> CustomPrompt:
        """校验名称并创建 CustomPrompt 实例。"""
        if not validate_name(self.name):
            raise ValueError(f"invalid prompt name: {self.name}")
        return CustomPrompt(
            name=self.name,
            description=self.description,
            messages=self.messages,
            arguments=self.arguments,
        )


# ---------------------------------------------------------------------------
# Promptset (maps to Go Promptset)
# ---------------------------------------------------------------------------


@dataclass
class PromptsetManifest:
    """Manifest for a promptset.

    Maps to Go: PromptsetManifest
    """

    server_version: str
    prompts_manifest: dict[str, PromptManifest] = field(default_factory=dict)


class Promptset:
    """A named collection of prompts.

    Maps to Go: Promptset struct
    """

    def __init__(self, name: str, prompt_names: list[str] | None = None):
        """初始化实例。"""
        self.name = name
        self.prompt_names: list[str] = prompt_names or []
        self._prompts: dict[str, Prompt] = {}
        self._manifest: PromptsetManifest | None = None

    def contains_prompt(self, name: str) -> bool:
        """Check if the promptset includes a prompt with the given name.

        Maps to Go: ContainsPrompt(name) bool
        """
        return name in self.prompt_names

    def _build_prompts_and_manifest(
        self,
        prompts_map: dict[str, Prompt],
    ) -> dict[str, PromptManifest]:
        """构建 prompts 字典和 manifest 字典,缺少 prompt 时抛出 ValueError。"""
        self._prompts = {}
        prompts_manifest: dict[str, PromptManifest] = {}
        for prompt_name in self.prompt_names:
            prompt = prompts_map.get(prompt_name)
            if prompt is None:
                raise ValueError(f"prompt does not exist: {prompt_name}")
            self._prompts[prompt_name] = prompt
            prompts_manifest[prompt_name] = prompt.manifest()
        return prompts_manifest

    def initialize(
        self,
        server_version: str,
        prompts_map: dict[str, Prompt],
    ) -> Promptset:
        """Initialize the promptset with resolved prompts.

        Maps to Go: PromptsetConfig.Initialize()
        """
        if not validate_name(self.name):
            raise ValueError(f"invalid promptset name: {self.name}")

        prompts_manifest = self._build_prompts_and_manifest(prompts_map)

        self._manifest = PromptsetManifest(
            server_version=server_version,
            prompts_manifest=prompts_manifest,
        )
        return self


@dataclass
class PromptsetConfig:
    """Configuration for a promptset.

    Maps to Go: PromptsetConfig
    """

    name: str
    prompt_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_prompt_registry: dict[str, type[PromptConfig]] = {}


def register_prompt(prompt_type: str):
    """Decorator: register a PromptConfig class for a given prompt type.

    Maps to Go: prompts.Register(resourceType, factory)

    Usage:
        @register_prompt("custom")
        class CustomPromptConfig(PromptConfig):
            ...
    """

    def decorator(cls: type[PromptConfig]) -> type[PromptConfig]:
        """将 PromptConfig 子类注册到全局 registry。"""
        if prompt_type in _prompt_registry:
            raise ValueError(f"prompt type {prompt_type!r} already registered")
        _prompt_registry[prompt_type] = cls
        return cls

    return decorator


def get_prompt_config_class(prompt_type: str) -> type[PromptConfig]:
    """Look up a registered PromptConfig class by type."""
    cls = _prompt_registry.get(prompt_type)
    if cls is None:
        raise ValueError(f"unknown prompt type: {prompt_type!r}")
    return cls


def list_prompt_types() -> list[str]:
    """Return all registered prompt type names."""
    return sorted(_prompt_registry.keys())


# Register custom prompt type by default
register_prompt("custom")(CustomPromptConfig)
