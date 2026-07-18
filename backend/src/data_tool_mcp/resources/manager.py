"""Resource manager — thread-safe (asyncio) container for sources, tools, toolsets,
prompts, and promptsets.

Maps to Go: internal/server/resources/resources.go

方案 C 改造（Source cache-aside + LRU + 引用计数）:
  - Source: LRU 缓存 + 惰性加载 + 引用计数,查缓存→查 config→initialize→存缓存→acquire
  - Tool/Toolset/SourceConfig: 全量内存缓存,同步访问
  - Admin API 写入后调用 invalidate_source 主动失效缓存
  - get_source 为 async,调用方必须 try/finally release_source
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.resources.lru_cache import LRUCache
from data_tool_mcp.sources import Source
from data_tool_mcp.tools import Tool

logger = logging.getLogger(__name__)


async def _close_source_callback(source: Any) -> None:
    """LRU 淘汰时关闭 source 的连接池。"""
    if hasattr(source, "close"):
        await source.close()


def _schedule_source_close(old: Any) -> None:
    """异步关闭旧 source（不阻塞当前调用）。"""
    if old is not None and hasattr(old, "close"):
        asyncio.create_task(_close_source_callback(old))


def _strip_str(val: Any) -> str:
    """将 val 转字符串并去除空白,None 视为空串。"""
    return str(val or "").strip()


def _extract_system_env(src_cfg: dict[str, Any]) -> tuple[str, str] | None:
    """从 source 配置中提取 (system_id, environment)，缺失则返回 None。"""
    sid = _strip_str(src_cfg.get("systemId"))
    env = _strip_str(src_cfg.get("environment"))
    if not sid or not env:
        return None
    return sid, env


def _extract_system(src_cfg: dict[str, Any]) -> str | None:
    """从 source 配置中提取 system_id，缺失返回 None。

    与 _extract_system_env 不同:仅要求 system_id 非空,environment 可空。
    用于创建 system-only toolset({systemId}),支持 /{systemId}/sse 路径访问。
    """
    sid = _strip_str(src_cfg.get("systemId"))
    return sid or None


def _filter_by_names(items: dict[str, Any], names: list[str]) -> list[Any]:
    """根据名称列表过滤出存在的项。"""
    return [items[name] for name in names if name in items]


class Toolset:
    """A named collection of tools for department-level routing.

    Maps to Go: internal/tools/tools.go Toolset
    """

    def __init__(self, name: str, tools: list[str] | None = None):
        """初始化实例。"""
        self.name = name
        self.tool_names: list[str] = tools or []

    def add_tool(self, tool_name: str) -> None:
        """将工具名添加到工具集(已存在则跳过)。"""
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

    Source 采用 cache-aside + LRU + 引用计数:
      - get_source (async): 查 LRU 缓存 → miss 时从 SourceConfig 惰性 initialize → 存入缓存 → acquire
      - release_source (async): 引用计数 -1,归零且标记待淘汰时真正淘汰
      - invalidate_source (async): Admin API 写入后主动失效
      - add_source_config (sync): 仅存配置(启动时 DB 加载,不 initialize)
      - add_source (async): 存入已初始化的 source(YAML 路径 + Admin create/update)

    Tool/Toolset/SourceConfig 全量内存缓存,同步访问。

    Python asyncio 是单线程事件循环,读操作无需锁。但 hot-reload 的
    watchdog 运行在独立线程,set_resources 用 threading.Lock 保证线程安全。
    """

    def __init__(self, source_cache_maxsize: int = 128) -> None:
        """初始化实例。"""
        # Source: LRU cache-aside(惰性加载 + 引用计数)
        self._source_cache = LRUCache(
            maxsize=source_cache_maxsize,
            close_callback=_close_source_callback,
        )
        # SourceConfig: 全量内存缓存(同步访问),source name → raw config dict
        self._source_configs: dict[str, dict[str, Any]] = {}
        # Tool/Toolset: 全量内存缓存(同步访问)
        self._tools: dict[str, Tool] = {}
        self._tool_types: dict[str, str] = {}  # tool name → original type string
        self._toolsets: dict[str, Toolset] = {}
        self._prompts: dict[str, Any] = {}
        self._promptsets: dict[str, Any] = {}
        self._embedding_models: dict[str, Any] = {}
        # Per-source init lock: 防止并发初始化同一个 source
        self._init_locks: dict[str, asyncio.Lock] = {}
        self._init_locks_guard = asyncio.Lock()
        # Thread lock for set_resources (called from watchdog thread)
        import threading

        self._lock = threading.Lock()

    # -- Sources (cache-aside + LRU) --

    async def get_source(self, source_name: str) -> Source | None:
        """获取 source(cache-aside + 惰性初始化)。

        命中: acquire(引用计数 +1)并返回。
        未命中: 查 SourceConfig → initialize → 存入缓存 → acquire。
        调用方必须在 try/finally 中调用 release_source()。

        Maps to Go: ResourceManager.GetSource (同步) — Python 改为 async 以支持惰性初始化。
        """
        # 快速路径: 缓存命中
        source = self._source_cache.get(source_name)
        if source is not None:
            self._source_cache.acquire(source_name)
            return source
        # 慢速路径: 惰性初始化(per-source lock 防并发)
        source = await self._get_or_create_source(source_name)
        if source is not None:
            self._source_cache.acquire(source_name)
        return source

    async def release_source(self, source_name: str) -> None:
        """释放 source(引用计数 -1)。必须与 get_source 配对调用。"""
        await self._source_cache.release(source_name)

    async def invalidate_source(self, source_name: str) -> None:
        """主动失效 source 缓存(Admin API 写入后调用)。

        引用计数为 0 时立即淘汰并关闭连接池;
        引用计数 > 0 时标记待淘汰,等引用归零时真正淘汰。
        """
        await self._source_cache.evict(source_name)

    async def _get_or_create_source(self, name: str) -> Source | None:
        """惰性初始化 source(per-source lock 防止并发初始化)。"""
        lock = await self._get_init_lock(name)
        async with lock:
            source = self._source_cache.get(name)
            if source is not None:
                return source
            return await self._init_source_from_config(name)

    async def _get_init_lock(self, name: str) -> asyncio.Lock:
        """获取(或创建)per-source 初始化锁。"""
        async with self._init_locks_guard:
            lock = self._init_locks.get(name)
            if lock is None:
                lock = asyncio.Lock()
                self._init_locks[name] = lock
            return lock

    async def _init_source_from_config(self, name: str) -> Source | None:
        """从配置解码并初始化 source，存入缓存后返回。"""
        cfg = self._source_configs.get(name)
        if cfg is None:
            return None
        source = await self._decode_and_initialize_source(name, cfg)
        if source is None:
            return None
        self._replace_cached_source(name, source)
        logger.debug(
            "数据源 %r 惰性初始化成功,已存入 LRU 缓存(当前 %d/%d)",
            name,
            self._source_cache.size(),
            self._source_cache._maxsize,
        )
        return source

    async def _decode_and_initialize_source(self, name: str, cfg: dict[str, Any]) -> Source | None:
        """解码并初始化 source，失败时返回 None。"""
        try:
            from data_tool_mcp.sources import decode_source_config

            src_type = cfg.get("type", "")
            source_config = decode_source_config(src_type, name, cfg)
            return await source_config.initialize()
        except Exception as exc:
            logger.warning("初始化数据源 %r 失败: %s", name, exc)
            return None

    def _replace_cached_source(self, name: str, source: Source) -> None:
        """用 replace 替换缓存项并异步关闭旧值。"""
        old = self._source_cache.replace(name, source)
        _schedule_source_close(old)

    def has_source(self, source_name: str) -> bool:
        """检查 source 配置是否存在(不检查是否已缓存)。用于存在性检查。"""
        return source_name in self._source_configs

    def get_sources_map(self) -> dict[str, Source]:
        """返回当前已缓存的 source 快照(不含未惰性初始化的)。

        注意: 仅返回已缓存的 source,可能不包含所有已配置的 source。
        存在性检查请用 has_source(),完整配置列表请用 get_all_source_configs()。
        主要用于 hot-reload 捕获旧 source 以便关闭连接池。
        """
        return self._source_cache.snapshot()

    async def close(self) -> None:
        """关闭所有已缓存的 source 连接池。

        必须在事件循环关闭前调用,否则底层驱动(如 aiomysql)的连接对象
        在 GC 时会尝试调用 close(),此时事件循环已关闭导致 RuntimeError。
        """
        await self._source_cache.clear()
        with self._lock:
            self._source_configs.clear()
            self._init_locks.clear()

    async def add_source(
        self, name: str, source: Source, config: dict[str, Any] | None = None
    ) -> None:
        """添加(或替换)一个已初始化的 source 到缓存。

        用于 YAML 配置加载路径和 Admin create/update(需立即测试连接)。
        原子替换旧缓存项,异步关闭旧 source 连接池。

        注意: 如果旧 source 正在被使用(refcount>0),旧连接池关闭后,
        持有旧 source 引用的请求会失败。这是 update 场景的预期行为
        (配置已变,旧连接应失效)。
        """
        old = self._source_cache.replace(name, source)
        if config is not None:
            with self._lock:
                self._source_configs[name] = dict(config)
        _schedule_source_close(old)

    def add_source_config(self, name: str, config: dict[str, Any]) -> None:
        """仅存储 source 配置,不初始化(首次 get_source 时惰性初始化)。

        用于 DB 持久化加载路径: 启动时不建立连接,首次 MCP 调用时才 initialize。
        """
        with self._lock:
            self._source_configs[name] = dict(config)

    async def remove_source(self, name: str) -> None:
        """移除 source(淘汰缓存 + 删除配置)。"""
        with self._lock:
            self._source_configs.pop(name, None)
        await self._source_cache.evict(name)

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
        """获取指定名称的工具实例。"""
        return self._tools.get(tool_name)

    def get_tools_map(self) -> dict[str, Tool]:
        """返回所有工具的 dict 副本。"""
        return dict(self._tools)

    def add_tool(self, name: str, tool: Tool, tool_type: str = "") -> None:
        """Register a tool at runtime. Thread-safe.

        新工具自动添加到默认 toolset（空名）、对应数据源的同名 toolset、
        以及对应 {system_id}-{environment} 的 toolset 中,确保 MCP 客户端通过
        /sse、/{source}/sse、/{systemId}/{environment}/{sourceName}/sse 都能列出工具。
        """
        with self._lock:
            self._register_tool(name, tool, tool_type)
            self._add_tool_to_all_toolsets(name, tool)

    def _register_tool(self, name: str, tool: Tool, tool_type: str) -> None:
        """将工具与类型注册到内部 dict。"""
        self._tools[name] = tool
        if tool_type:
            self._tool_types[name] = tool_type

    def _add_tool_to_all_toolsets(self, name: str, tool: Tool) -> None:
        """将工具添加到默认、数据源同名、{system_id}、{system_id}-{environment} toolset。"""
        self._add_tool_to_toolset("", name)
        src = self._tool_source_name(tool)
        if not src:
            return
        self._add_tool_to_toolset(src, name)
        self._add_tool_to_system_toolset(src, name)
        self._add_tool_to_system_env_toolset(src, name)

    def _tool_source_name(self, tool: Tool) -> str | None:
        """获取工具关联的数据源名称。"""
        return getattr(tool, "source_name", None) or getattr(tool, "_source_name", None)

    def _add_tool_to_toolset(self, ts_name: str, tool_name: str) -> None:
        """添加工具到指定 toolset（不存在则创建）。"""
        if ts_name not in self._toolsets:
            self._toolsets[ts_name] = Toolset(name=ts_name, tools=[])
        if tool_name not in self._toolsets[ts_name].tool_names:
            self._toolsets[ts_name].tool_names.append(tool_name)

    def _add_tool_to_system_env_toolset(self, src: str, name: str) -> None:
        """添加工具到 {system_id}-{environment} toolset。"""
        sid_env = _extract_system_env(self._source_configs.get(src) or {})
        if not sid_env:
            return
        self._add_tool_to_toolset(f"{sid_env[0]}-{sid_env[1]}", name)

    def _add_tool_to_system_toolset(self, src: str, name: str) -> None:
        """添加工具到 {system_id} toolset(系统级聚合,不区分环境)。

        支持 MCP 客户端通过 /{systemId}/sse 路径访问该系统全部工具。
        """
        sid = _extract_system(self._source_configs.get(src) or {})
        if not sid:
            return
        self._add_tool_to_toolset(sid, name)

    def ensure_default_toolset(self) -> None:
        """确保默认 toolset（空名）存在，包含当前所有工具。

        同时为每个数据源创建同名 toolset，使 MCP 客户端可以通过
        /{source-name}/sse 路由只访问该数据源的工具。
        从持久化存储加载工具后调用。

        此外,按 {system_id}(系统编号)和 {system_id}-{environment}(系统编号-环境)创建 toolset,
        使 MCP 客户端可以通过 /{systemId}/sse 或 /{systemId}/{environment}/{sourceName}/sse
        路由访问该系统(及环境)下所有数据源的工具。
        """
        with self._lock:
            self._ensure_default_toolset_has_all_tools()
            source_tool_map, system_tool_map, system_env_tool_map = self._group_tools_by_source()
            self._apply_toolset_groups(source_tool_map)
            self._apply_toolset_groups(system_tool_map)
            self._apply_toolset_groups(system_env_tool_map)

    def _ensure_default_toolset_has_all_tools(self) -> None:
        """确保默认 toolset（空名）存在且包含所有工具。"""
        if "" not in self._toolsets:
            self._toolsets[""] = Toolset(name="", tools=list(self._tools.keys()))
            return
        self._merge_tools_into_toolset("")

    def _merge_tools_into_toolset(self, ts_name: str) -> None:
        """将所有工具合并到已存在的 toolset 中（补全缺失项）。"""
        for tool_name in self._tools:
            if tool_name not in self._toolsets[ts_name].tool_names:
                self._toolsets[ts_name].tool_names.append(tool_name)

    def _group_tools_by_source(
        self,
    ) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
        """按数据源、{system_id}、{system_id}-{environment} 分组工具。"""
        source_tool_map: dict[str, list[str]] = {}
        system_tool_map: dict[str, list[str]] = {}
        system_env_tool_map: dict[str, list[str]] = {}
        for tool_name, tool in self._tools.items():
            src = self._tool_source_name(tool)
            if not src:
                continue
            source_tool_map.setdefault(src, []).append(tool_name)
            self._add_to_system_group(src, tool_name, system_tool_map)
            self._add_to_system_env_group(src, tool_name, system_env_tool_map)
        return source_tool_map, system_tool_map, system_env_tool_map

    def _add_to_system_group(
        self, src: str, tool_name: str, system_tool_map: dict[str, list[str]]
    ) -> None:
        """将工具归入对应的 {system_id} 分组(系统级,不区分环境)。"""
        sid = _extract_system(self._source_configs.get(src) or {})
        if not sid:
            return
        system_tool_map.setdefault(sid, []).append(tool_name)

    def _add_to_system_env_group(
        self, src: str, tool_name: str, system_env_tool_map: dict[str, list[str]]
    ) -> None:
        """将工具归入对应的 {system_id}-{environment} 分组。"""
        sid_env = _extract_system_env(self._source_configs.get(src) or {})
        if not sid_env:
            return
        ts_name = f"{sid_env[0]}-{sid_env[1]}"
        system_env_tool_map.setdefault(ts_name, []).append(tool_name)

    def _apply_toolset_groups(self, groups: dict[str, list[str]]) -> None:
        """根据分组创建或更新 toolset。"""
        for ts_name, tool_names in groups.items():
            self._apply_one_toolset_group(ts_name, tool_names)

    def _apply_one_toolset_group(self, ts_name: str, tool_names: list[str]) -> None:
        """应用单个 toolset 分组(已存在则合并,否则新建)。"""
        if ts_name in self._toolsets:
            self._merge_names_into_toolset(ts_name, tool_names)
            return
        self._toolsets[ts_name] = Toolset(name=ts_name, tools=list(tool_names))

    def _merge_names_into_toolset(self, ts_name: str, tool_names: list[str]) -> None:
        """将指定工具名合并到已存在的 toolset 中（补全缺失项）。"""
        for tn in tool_names:
            if tn not in self._toolsets[ts_name].tool_names:
                self._toolsets[ts_name].tool_names.append(tn)

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
        """获取指定名称的工具集。"""
        return self._toolsets.get(toolset_name)

    def get_toolsets_map(self) -> dict[str, Toolset]:
        """返回所有 toolset 的 dict 副本。"""
        return dict(self._toolsets)

    def get_toolset_tools(self, toolset_name: str) -> list[Tool]:
        """Get all tools belonging to a toolset."""
        toolset = self._toolsets.get(toolset_name)
        if not toolset:
            return []
        return _filter_by_names(self._tools, toolset.tool_names)

    def get_toolset_manifest(
        self, toolset_name: str, server_version: str = "0.1.0"
    ) -> ToolsetManifest | None:
        """Get the manifest for a specific toolset."""
        toolset = self._toolsets.get(toolset_name)
        if not toolset:
            return None
        return toolset.manifest(server_version)

    # -- Prompts --

    def get_prompt(self, prompt_name: str) -> Any | None:
        """获取指定名称的 prompt。"""
        return self._prompts.get(prompt_name)

    def get_prompts_map(self) -> dict[str, Any]:
        """返回所有 prompt 的 dict 副本。"""
        return dict(self._prompts)

    # -- Promptsets --

    def get_promptset(self, promptset_name: str) -> Any | None:
        """获取指定名称的 promptset。"""
        return self._promptsets.get(promptset_name)

    def get_promptsets_map(self) -> dict[str, Any]:
        """返回所有 promptset 的 dict 副本。"""
        return dict(self._promptsets)

    def get_promptset_prompts(self, promptset_name: str) -> list[Any]:
        """Get all prompts belonging to a promptset."""
        promptset = self._promptsets.get(promptset_name)
        if not promptset:
            return []
        return _filter_by_names(self._prompts, promptset.prompt_names)

    # -- Embedding models --

    def get_embedding_model(self, embedding_model_name: str) -> Any | None:
        """获取指定名称的 embedding model。"""
        return self._embedding_models.get(embedding_model_name)

    def get_embedding_models_map(self) -> dict[str, Any]:
        """返回所有 embedding model 的 dict 副本。"""
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

        注意: sources 替换时不关闭旧 source(由调用方在调用前捕获 old_sources
        并在调用后单独关闭,见 hotreload._reload_resources)。
        """
        with self._lock:
            if sources is not None:
                # 替换 LRU 缓存内容(不关闭旧项,调用方负责)
                self._source_cache.reset(sources)
            self._apply_config_updates(
                source_configs,
                tools,
                toolsets,
                prompts,
                promptsets,
                embedding_models,
                tool_types,
            )
            self._ensure_default_toolset_if_needed()
            self._ensure_default_promptset_if_needed()

    def _apply_config_updates(
        self,
        source_configs: dict[str, dict[str, Any]] | None,
        tools: dict[str, Tool] | None,
        toolsets: dict[str, Toolset] | None,
        prompts: dict[str, Any] | None,
        promptsets: dict[str, Any] | None,
        embedding_models: dict[str, Any] | None,
        tool_types: dict[str, str] | None,
    ) -> None:
        """批量更新非 source 缓存的资源配置（仅非 None 的项）。"""
        updates = {
            "_source_configs": source_configs,
            "_tools": tools,
            "_toolsets": toolsets,
            "_prompts": prompts,
            "_promptsets": promptsets,
            "_embedding_models": embedding_models,
            "_tool_types": tool_types,
        }
        for attr, value in updates.items():
            if value is not None:
                setattr(self, attr, value)

    def _ensure_default_toolset_if_needed(self) -> None:
        """无 toolset 但有工具时创建默认 toolset。"""
        if self._toolsets or not self._tools:
            return
        self._toolsets[""] = Toolset(name="", tool_names=list(self._tools.keys()))

    def _ensure_default_promptset_if_needed(self) -> None:
        """无 promptset 但有 prompt 时创建默认 promptset。"""
        if self._promptsets or not self._prompts:
            return
        from data_tool_mcp.prompts.base import Promptset

        self._promptsets[""] = Promptset(name="", prompt_names=list(self._prompts.keys()))
