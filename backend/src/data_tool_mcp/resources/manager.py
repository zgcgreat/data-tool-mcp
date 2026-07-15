"""Resource manager — thread-safe (asyncio) container for sources, tools, toolsets,
prompts, and promptsets.

Maps to Go: internal/server/resources/resources.go
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources import Source
from data_tool_mcp.tools import Tool


class Toolset:
    """A named collection of tools for department-level routing.

    Maps to Go: internal/tools/tools.go Toolset
    """

    def __init__(self, name: str, tools: list[str] | None = None):
        self.name = name
        self.tool_names: list[str] = tools or []

    def add_tool(self, tool_name: str) -> None:
        if tool_name not in self.tool_names:
            self.tool_names.append(tool_name)

    def manifest(self, server_version: str = "0.1.0") -> ToolsetManifest:
        """Generate the toolset manifest.

        Maps to Go: Toolset.Manifest / PromptsetManifest
        """
        return ToolsetManifest(
            server_version=server_version,
            tool_names=list(self.tool_names),
        )


@dataclass
class ToolsetManifest:
    """Manifest for a toolset.

    Maps to Go: ToolsetManifest / PromptsetManifest
    """
    server_version: str
    tool_names: list[str] = field(default_factory=list)


class ResourceManager:
    """Central registry for all runtime resources.

    Maps to Go: ResourceManager struct with sync.RWMutex.
    Python asyncio is single-threaded for the event loop, so no
    locks are needed for concurrent reads.  However, hot-reload
    runs on a watchdog thread, so we use threading.Lock for
    thread-safety when set_resources() is called from that thread.
    """

    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}
        self._source_configs: dict[str, dict[str, Any]] = {}  # source name → raw config dict
        self._tools: dict[str, Tool] = {}
        self._tool_types: dict[str, str] = {}  # tool name → original type string
        self._toolsets: dict[str, Toolset] = {}
        self._prompts: dict[str, Any] = {}
        self._promptsets: dict[str, Any] = {}
        self._embedding_models: dict[str, Any] = {}
        # Thread lock for set_resources (called from watchdog thread)
        import threading
        self._lock = threading.Lock()

    # -- Sources --

    def get_source(self, source_name: str) -> Source | None:
        return self._sources.get(source_name)

    def get_sources_map(self) -> dict[str, Source]:
        return dict(self._sources)

    async def close(self) -> None:
        """Close all sources' underlying connections (engines/clients).

        必须在事件循环关闭前调用,否则底层驱动(如 aiomysql)的连接对象
        在 GC 时会尝试调用 close(),此时事件循环已关闭导致 RuntimeError。
        """
        with self._lock:
            sources = dict(self._sources)
        for name, source in sources.items():
            try:
                await source.close()
            except Exception:
                pass

    def add_source(self, name: str, source: Source, config: dict[str, Any] | None = None) -> None:
        """Add (or replace) a source at runtime. Thread-safe."""
        with self._lock:
            self._sources[name] = source
            if config is not None:
                self._source_configs[name] = dict(config)

    def remove_source(self, name: str) -> None:
        """Remove a source at runtime. Thread-safe."""
        with self._lock:
            self._sources.pop(name, None)
            self._source_configs.pop(name, None)

    def get_source_config(self, source_name: str) -> dict[str, Any] | None:
        """Return the raw config dict for a source, or None."""
        cfg = self._source_configs.get(source_name)
        return dict(cfg) if cfg is not None else None

    def get_all_source_configs(self) -> dict[str, dict[str, Any]]:
        """Return all source configs (name → config dict)."""
        with self._lock:
            return {name: dict(cfg) for name, cfg in self._source_configs.items()}

    # -- Tools --

    def get_tool(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def get_tools_map(self) -> dict[str, Tool]:
        return dict(self._tools)

    def add_tool(self, name: str, tool: Tool, tool_type: str = "") -> None:
        """Register a tool at runtime. Thread-safe.

        新工具自动添加到默认 toolset（空名）、对应数据源的同名 toolset、
        以及对应 {system_id}-{environment} 的 toolset 中,确保 MCP 客户端通过
        /sse、/{source}/sse、/{systemId}/{environment}/{sourceName}/sse 都能列出工具。
        """
        with self._lock:
            self._tools[name] = tool
            if tool_type:
                self._tool_types[name] = tool_type
            # 自动添加到默认 toolset
            if "" not in self._toolsets:
                self._toolsets[""] = Toolset(name="", tools=[])
            if name not in self._toolsets[""].tool_names:
                self._toolsets[""].tool_names.append(name)
            # 自动添加到数据源同名 toolset
            src = getattr(tool, "source_name", None) or getattr(tool, "_source_name", None)
            if src:
                if src not in self._toolsets:
                    self._toolsets[src] = Toolset(name=src, tools=[])
                if name not in self._toolsets[src].tool_names:
                    self._toolsets[src].tool_names.append(name)
                # 自动添加到 {system_id}-{environment} toolset
                src_cfg = self._source_configs.get(src) or {}
                sid = str(src_cfg.get("systemId", "") or "").strip()
                env = str(src_cfg.get("environment", "") or "").strip()
                if sid and env:
                    ts_name = f"{sid}-{env}"
                    if ts_name not in self._toolsets:
                        self._toolsets[ts_name] = Toolset(name=ts_name, tools=[])
                    if name not in self._toolsets[ts_name].tool_names:
                        self._toolsets[ts_name].tool_names.append(name)

    def ensure_default_toolset(self) -> None:
        """确保默认 toolset（空名）存在，包含当前所有工具。

        同时为每个数据源创建同名 toolset，使 MCP 客户端可以通过
        /{source-name}/sse 路由只访问该数据源的工具。
        从持久化存储加载工具后调用。

        此外,按 {system_id}-{environment}(系统编号-环境)创建 toolset,使 MCP 客户端可以通过
        /{systemId}/{environment}/{sourceName}/sse 路由访问该系统该环境下所有数据源的工具。
        """
        with self._lock:
            # 默认 toolset（空名）：包含所有工具
            if "" not in self._toolsets:
                self._toolsets[""] = Toolset(name="", tools=list(self._tools.keys()))
            else:
                for tool_name in self._tools:
                    if tool_name not in self._toolsets[""].tool_names:
                        self._toolsets[""].tool_names.append(tool_name)

            # 为每个数据源创建同名 toolset（按工具的 source_name 分组）
            source_tool_map: dict[str, list[str]] = {}
            # 同时按 {system_id}-{environment} 分组工具
            system_env_tool_map: dict[str, list[str]] = {}
            for tool_name, tool in self._tools.items():
                src = getattr(tool, "source_name", None) or getattr(tool, "_source_name", None)
                if src:
                    source_tool_map.setdefault(src, []).append(tool_name)
                    # 查找该数据源的 system_id 和 environment
                    src_cfg = self._source_configs.get(src) or {}
                    sid = str(src_cfg.get("systemId", "") or "").strip()
                    env = str(src_cfg.get("environment", "") or "").strip()
                    if sid and env:
                        ts_name = f"{sid}-{env}"
                        system_env_tool_map.setdefault(ts_name, []).append(tool_name)
            for src_name, tool_names in source_tool_map.items():
                if src_name in self._toolsets:
                    # 已存在，补全缺失的工具
                    for tn in tool_names:
                        if tn not in self._toolsets[src_name].tool_names:
                            self._toolsets[src_name].tool_names.append(tn)
                else:
                    self._toolsets[src_name] = Toolset(name=src_name, tools=list(tool_names))

            # 按 {system_id}-{environment} 创建/更新 toolset
            for ts_name, tool_names in system_env_tool_map.items():
                if ts_name in self._toolsets:
                    # 已存在，补全缺失的工具
                    for tn in tool_names:
                        if tn not in self._toolsets[ts_name].tool_names:
                            self._toolsets[ts_name].tool_names.append(tn)
                else:
                    self._toolsets[ts_name] = Toolset(name=ts_name, tools=list(tool_names))

    def remove_tool(self, name: str) -> None:
        """Remove a tool at runtime. Thread-safe."""
        with self._lock:
            self._tools.pop(name, None)
            self._tool_types.pop(name, None)

    def get_tool_type(self, name: str) -> str:
        """Return the original type string for a tool, or 'unknown'."""
        return self._tool_types.get(name, "unknown")

    # -- Toolsets --

    def get_toolset(self, toolset_name: str) -> Toolset | None:
        return self._toolsets.get(toolset_name)

    def get_toolsets_map(self) -> dict[str, Toolset]:
        return dict(self._toolsets)

    def get_toolset_tools(self, toolset_name: str) -> list[Tool]:
        """Get all tools belonging to a toolset."""
        toolset = self._toolsets.get(toolset_name)
        if not toolset:
            return []
        return [
            self._tools[name]
            for name in toolset.tool_names
            if name in self._tools
        ]

    def get_toolset_manifest(self, toolset_name: str, server_version: str = "0.1.0") -> ToolsetManifest | None:
        """Get the manifest for a specific toolset."""
        toolset = self._toolsets.get(toolset_name)
        if not toolset:
            return None
        return toolset.manifest(server_version)

    # -- Prompts --

    def get_prompt(self, prompt_name: str) -> Any | None:
        return self._prompts.get(prompt_name)

    def get_prompts_map(self) -> dict[str, Any]:
        return dict(self._prompts)

    # -- Promptsets --

    def get_promptset(self, promptset_name: str) -> Any | None:
        return self._promptsets.get(promptset_name)

    def get_promptsets_map(self) -> dict[str, Any]:
        return dict(self._promptsets)

    def get_promptset_prompts(self, promptset_name: str) -> list[Any]:
        """Get all prompts belonging to a promptset."""
        promptset = self._promptsets.get(promptset_name)
        if not promptset:
            return []
        return [
            self._prompts[name]
            for name in promptset.prompt_names
            if name in self._prompts
        ]

    # -- Embedding models --

    def get_embedding_model(self, embedding_model_name: str) -> Any | None:
        return self._embedding_models.get(embedding_model_name)

    def get_embedding_models_map(self) -> dict[str, Any]:
        return dict(self._embedding_models)

    # -- Batch update (hot-reload) --

    def set_resources(
        self,
        sources: dict[str, Source] | None = None,
        tools: dict[str, Tool] | None = None,
        toolsets: dict[str, Toolset] | None = None,
        prompts: dict[str, Any] | None = None,
        promptsets: dict[str, Any] | None = None,
        embedding_models: dict[str, Any] | None = None,
        tool_types: dict[str, str] | None = None,
        source_configs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Replace all resources atomically.

        Maps to Go: ResourceManager.SetResources (with Lock).
        Thread-safe: acquires lock so watchdog thread and asyncio
        event loop don't corrupt each other's reads.
        """
        with self._lock:
            if sources is not None:
                self._sources = sources
            if source_configs is not None:
                self._source_configs = source_configs
            if tools is not None:
                self._tools = tools
            if toolsets is not None:
                self._toolsets = toolsets
            if prompts is not None:
                self._prompts = prompts
            if promptsets is not None:
                self._promptsets = promptsets
            if embedding_models is not None:
                self._embedding_models = embedding_models
            if tool_types is not None:
                self._tool_types = tool_types
            
            # Create default toolset if none exists
            # Maps to Go: server.go L292-300
            if not self._toolsets and self._tools:
                default_toolset = Toolset(name="", tool_names=list(self._tools.keys()))
                self._toolsets[""] = default_toolset
            
            # Create default promptset if none exists
            # Maps to Go: server.go L183-191
            if not self._promptsets and self._prompts:
                from data_tool_mcp.prompts.base import Promptset
                default_promptset = Promptset(name="", prompt_names=list(self._prompts.keys()))
                self._promptsets[""] = default_promptset
