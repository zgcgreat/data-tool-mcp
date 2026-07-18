"""Configuration hot-reload using watchdog.

Maps to Go: cmd/root.go handleDynamicReload + fsnotify
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from watchdog.observers import Observer

from data_tool_mcp.config.loader import load_config
from data_tool_mcp.config.models import ServerConfig
from data_tool_mcp.resources import ResourceManager

logger = logging.getLogger(__name__)


class ConfigChangeHandler(FileSystemEventHandler):
    """Watchdog handler that triggers config reload on YAML file changes.

    Thread-safety: the watchdog observer runs on a background thread,
    so we schedule the actual reload on the asyncio event loop via
    loop.call_soon_threadsafe().  This avoids races with the
    ResourceManager.set_resources() lock.
    """

    def __init__(
        self,
        config: ServerConfig,
        resource_manager: ResourceManager,
        debounce_seconds: float = 1.0,
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        """初始化实例。"""
        self.config = config
        self.resource_manager = resource_manager
        self.debounce_seconds = debounce_seconds
        self._loop = loop or asyncio.get_event_loop()
        self._reload_task: asyncio.Task | None = None
        self._pending: bool = False
        self._lock = threading.Lock()

    def on_modified(self, event: FileModifiedEvent) -> None:
        """YAML 文件修改事件回调，触发去抖重载。"""
        if not event.src_path.endswith((".yaml", ".yml")):
            return
        logger.info("config file changed: %s", event.src_path)
        self._schedule_reload()

    def _schedule_reload(self) -> None:
        """Schedule a debounced reload on the asyncio event loop."""
        with self._lock:
            if self._pending:
                return  # already scheduled, debounce will cover it
            self._pending = True
        self._loop.call_soon_threadsafe(self._do_debounced_reload)

    async def _do_reload(self) -> None:
        """Reload config after debounce delay."""
        await asyncio.sleep(self.debounce_seconds)
        self._pending = False
        try:
            await _reload_resources(self.config, self.resource_manager)
            logger.info("config reloaded successfully")
        except Exception as exc:
            logger.error("config reload failed: %s", exc)

    def _do_debounced_reload(self) -> None:
        """Callback scheduled from watchdog thread to event loop."""
        if self._reload_task and not self._reload_task.done():
            self._reload_task.cancel()
        self._reload_task = self._loop.create_task(self._do_reload())


async def _close_source(src: Any) -> None:
    """关闭单个数据源连接池，失败时仅记录日志。"""
    if not hasattr(src, "close"):
        return
    try:
        await src.close()
    except Exception as exc:
        logger.warning("error closing old source during reload: %s", exc)


async def _close_old_sources(old_sources: dict[str, Any]) -> None:
    """关闭旧数据源连接池以避免连接泄漏。"""
    for src in old_sources.values():
        await _close_source(src)


async def _reload_resources(config: ServerConfig, rm: ResourceManager) -> None:
    """Reload all resources from config files.

    Closes old data source connection pools before replacing them to
    prevent connection leaks.
    """
    from data_tool_mcp.cli.main import _initialize_resources

    # Capture old sources so we can close their connection pools after reload
    old_sources = rm.get_sources_map()

    config = await load_config(config)
    await _initialize_resources(config, rm)

    await _close_old_sources(old_sources)


async def _run_observer_keepalive(observer: Observer) -> None:
    """保持 watchdog observer 活动直到被取消。"""
    try:
        while True:
            await asyncio.sleep(3600)  # Keep alive
    except asyncio.CancelledError:
        observer.stop()


async def start_hot_reload(config_folder: str, config: ServerConfig, rm: ResourceManager) -> None:
    """Start watching a config folder for changes.

    Maps to Go: fsnotify watcher in cmd/root.go
    """
    folder = Path(config_folder)
    if not folder.is_dir():
        logger.warning("config folder does not exist: %s", config_folder)
        return

    loop = asyncio.get_running_loop()
    handler = ConfigChangeHandler(config, rm, loop=loop)
    observer = Observer()
    observer.schedule(handler, str(folder), recursive=True)
    observer.start()
    logger.info("watching config folder: %s", config_folder)

    await _run_observer_keepalive(observer)
    observer.join()
