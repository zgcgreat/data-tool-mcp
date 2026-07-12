"""Prompts system for MCP Toolbox.

Maps to Go: internal/prompts/
- prompts.go: PromptConfig + Prompt interface + registry
- arguments.go: Argument definition
- messages.go: Message (Role + Content)
- promptsets.go: PromptsetConfig + Promptset + Manifest
- custom/custom.go: Custom prompt implementation
"""

from data_tool_mcp.prompts.base import (
    Argument,
    ArgumentManifest,
    CustomPrompt,
    CustomPromptConfig,
    Message,
    Prompt,
    PromptConfig,
    PromptManifest,
    Promptset,
    PromptsetConfig,
    PromptsetManifest,
    get_prompt_config_class,
    list_prompt_types,
    register_prompt,
)
from data_tool_mcp.prompts.registry import decode_prompt_config

__all__ = [
    "Argument",
    "ArgumentManifest",
    "CustomPrompt",
    "CustomPromptConfig",
    "Message",
    "Prompt",
    "PromptConfig",
    "PromptManifest",
    "Promptset",
    "PromptsetConfig",
    "PromptsetManifest",
    "decode_prompt_config",
    "get_prompt_config_class",
    "list_prompt_types",
    "register_prompt",
]
