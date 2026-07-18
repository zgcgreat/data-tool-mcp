"""Prebuilt configuration YAML access module.

Provides functions to list, read, and parse the bundled YAML configuration
files that ship with mcp-toolbox. Each YAML file uses ``---`` separators to
define source, tool, and toolset entries (language-independent).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

import yaml


_YAML_PACKAGE = "data_tool_mcp.prebuiltconfigs"


def _resources_dir() -> Path:
    """Return the filesystem path to the bundled YAML directory."""
    ref = importlib.resources.files(_YAML_PACKAGE)
    # importlib.resources may return a Traversable; convert to Path
    return Path(str(ref))


def list_prebuilt_configs() -> list[str]:
    """Return the names of all available prebuilt configs (without .yaml extension).

    Example::

        >>> list_prebuilt_configs()[:3]
        ['alloydb-omni', 'alloydb-postgres-admin', 'alloydb-postgres-observability']
    """
    directory = _resources_dir()
    names: list[str] = []
    for p in sorted(directory.glob("*.yaml")):
        names.append(p.stem)
    return names


def get_prebuilt_config(name: str) -> str:
    """Return the raw YAML content of a prebuilt config by name.

    Args:
        name: Config name without extension, e.g. ``"postgres"``.

    Returns:
        The full YAML file content as a string.

    Raises:
        FileNotFoundError: If no prebuilt config with that name exists.
    """
    directory = _resources_dir()
    path = directory / f"{name}.yaml"
    if not path.exists():
        available = list_prebuilt_configs()
        raise FileNotFoundError(f"prebuilt config {name!r} not found. Available: {available}")
    return path.read_text(encoding="utf-8")


def load_prebuilt_config(name: str) -> list[dict[str, Any]]:
    """Parse a prebuilt config and return a list of source/tool/toolset dicts.

    Each YAML file uses ``---`` document separators. This function parses
    each document and returns them as a list of dictionaries, one per
    document (source, tool, or toolset definition).

    Args:
        name: Config name without extension, e.g. ``"postgres"``.

    Returns:
        List of dicts, each with at least ``kind`` and ``name`` keys.

    Raises:
        FileNotFoundError: If no prebuilt config with that name exists.
    """
    content = get_prebuilt_config(name)
    docs: list[dict[str, Any]] = []
    for doc in yaml.safe_load_all(content):
        if doc is not None:
            docs.append(doc)
    return docs
