"""Prompt config decoding from raw data.

Maps to Go: prompts.DecodeConfig()
"""

from __future__ import annotations

from typing import Any

from data_tool_mcp.prompts.base import (
    Argument,
    CustomPromptConfig,
    Message,
    PromptConfig,
    get_prompt_config_class,
)


def decode_prompt_config(
    prompt_type: str,
    name: str,
    config_data: dict[str, Any],
) -> PromptConfig:
    """Decode a prompt config from raw dict data.

    Maps to Go: prompts.DecodeConfig(ctx, resourceType, name, decoder)

    If prompt_type is empty, defaults to "custom".
    """
    if not prompt_type:
        prompt_type = "custom"

    if prompt_type == "custom":
        return _decode_custom_prompt(name, config_data)

    # For other registered types, use from_dict if available
    cls = get_prompt_config_class(prompt_type)
    if hasattr(cls, "from_dict"):
        return cls.from_dict(name, config_data)  # type: ignore[attr-defined]

    raise ValueError(f"unknown prompt type: {prompt_type!r}")


def _decode_custom_prompt(name: str, data: dict[str, Any]) -> CustomPromptConfig:
    """Decode a custom prompt from YAML data.

    Maps to Go: custom/custom.go decode()
    """
    description = data.get("description", "")
    messages = []
    for msg_data in data.get("messages", []):
        messages.append(Message(
            role=msg_data.get("role", "user"),
            content=msg_data.get("content", ""),
        ))

    arguments = []
    for arg_data in data.get("arguments", []):
        arguments.append(Argument(
            name=arg_data.get("name", ""),
            description=arg_data.get("description", ""),
            required=arg_data.get("required", True),
        ))

    return CustomPromptConfig(
        name=name,
        description=description,
        messages=messages,
        arguments=arguments,
    )
