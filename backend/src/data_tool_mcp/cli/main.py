"""CLI — main entry point.

Maps to Go: cmd/root.go + cmd/internal/serve/command.go + cmd/internal/flags.go
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from data_tool_mcp import __version__


def _load_dotenv() -> None:
    """Load .env file if present (no external dependency)."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolbox",
        description="MCP Toolbox for Databases — Python edition",
    )
    parser.add_argument("--version", "-v", action="version", version=f"mcp-toolbox v{__version__}")

    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the MCP Toolbox server")

    # Config
    serve.add_argument("--config", "-c", default=None, help="Path to config YAML file")
    serve.add_argument("--configs", nargs="*", default=None, help="Paths to config YAML files")
    serve.add_argument("--config-folder", default=None, help="Folder of config YAML files")
    serve.add_argument("--prebuilt", nargs="*", default=None, help="Prebuilt config name(s)")
    serve.add_argument("--config-db-url", default=os.environ.get("TOOLBOX_CONFIG_DB_URL"), help="MySQL URL for DB-backed config")
    serve.add_argument("--env-passwords", default=os.environ.get("ENV_PASSWORDS"), help="JSON mapping of ${VAR} placeholders")
    serve.add_argument("--api-key", default=os.environ.get("TOOLBOX_API_KEY"), help="API Key binding this instance to a single department via the api_keys table")

    # 配置持久化存储
    serve.add_argument("--store-url", default=os.environ.get("TOOLBOX_STORE_URL"),
                       help="配置持久化存储 URL（留空=默认在当前目录创建 SQLite 文件 toolbox_data.db；"
                            "MySQL 推荐 mysql://host:port/db 不含账号密码，配合 --store-username/--store-password）")
    serve.add_argument("--store-username", default=os.environ.get("TOOLBOX_STORE_USERNAME"),
                       help="配置持久化存储 MySQL 用户名（与 --store-url 分离，避免凭据写在 URL 中）")
    serve.add_argument("--store-password", default=os.environ.get("TOOLBOX_STORE_PASSWORD"),
                       help="配置持久化存储 MySQL 密码（与 --store-url 分离）")

    # Network
    serve.add_argument("--address", "-a", default="0.0.0.0", help="Listen address")
    serve.add_argument("--port", "-p", type=int, default=5000, help="Listen port")
    serve.add_argument("--stdio", action="store_true", help="Run in STDIO mode")

    # Logging
    serve.add_argument("--log-level", default="INFO", help="Log level: DEBUG, INFO, WARN, ERROR")
    serve.add_argument("--logging-format", default="standard", choices=["standard", "json"], help="Log format")

    # Features
    serve.add_argument("--disable-reload", action="store_true", help="Disable config hot-reload")
    serve.add_argument("--enable-api", action="store_true", help="Enable legacy /api HTTP endpoints")
    serve.add_argument("--enable-draft-specs", action="store_true", help="Enable draft MCP protocol specs")
    serve.add_argument("--ignore-unknown-tools", action="store_true", help="Ignore unknown tool types")

    # TLS
    serve.add_argument("--tls-cert", default=None, help="TLS certificate file path")
    serve.add_argument("--tls-key", default=None, help="TLS private key file path")

    # Telemetry
    serve.add_argument("--telemetry-otlp", default=None, help="OTLP endpoint")
    serve.add_argument("--telemetry-gcp", action="store_true", help="Enable Google Cloud telemetry")
    serve.add_argument("--telemetry-gcp-project", default=None, help="GCP project ID")
    serve.add_argument("--telemetry-service-name", default="toolbox", help="Telemetry service name")

    # Other
    serve.add_argument("--sql-commenter", action="store_true", help="Add SQLCommenter comments")
    serve.add_argument("--allowed-origins", nargs="*", default=None, help="Allowed CORS origins")
    serve.add_argument("--allowed-hosts", nargs="*", default=None, help="Allowed hosts")
    serve.add_argument("--user-agent-metadata", nargs="*", default=None, help="User-Agent metadata")

    return parser


def main() -> None:
    _load_dotenv()

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        _cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_serve(args: argparse.Namespace) -> None:
    from data_tool_mcp.config.models import ServerConfig

    server_config = ServerConfig(
        address=args.address,
        port=args.port,
        stdio=args.stdio,
        log_level=args.log_level,
        logging_format=args.logging_format,
        disable_reload=args.disable_reload,
        enable_api=args.enable_api,
        enable_draft_specs=args.enable_draft_specs,
        cert_file=args.tls_cert or "",
        key_file=args.tls_key or "",
        config_file=args.config or "",
        config_files=args.configs or [],
        config_folder=args.config_folder or "",
        prebuilt=",".join(args.prebuilt) if args.prebuilt else "",
        config_db_url=args.config_db_url or "",
        env_passwords=args.env_passwords or "",
        api_key=args.api_key or "",
        telemetry_otlp=args.telemetry_otlp or "",
        telemetry_gcp=args.telemetry_gcp,
        telemetry_gcp_project=args.telemetry_gcp_project or "",
        telemetry_service_name=args.telemetry_service_name,
        sql_commenter=args.sql_commenter,
        allowed_origins=args.allowed_origins or ["*"],
        # Default to [] -> middleware treats empty list as None and allows all hosts
        # (development mode). Passing ["*"] would enable checking against a literal "*"
        # host and reject everything, so we never default to ["*"].
        allowed_hosts=args.allowed_hosts or [],
        ignore_unknown_tools=args.ignore_unknown_tools,
        user_agent_metadata=args.user_agent_metadata or [],
        store_url=args.store_url or "",
        store_username=args.store_username or "",
        store_password=args.store_password or "",
    )

    if args.stdio:
        asyncio.run(_run_stdio(server_config))
    else:
        asyncio.run(_run_http(server_config))


async def _run_http(config: "ServerConfig") -> None:
    """Start HTTP server (SSE + Streamable)."""
    import uvicorn

    from data_tool_mcp.config.loader import load_config
    from data_tool_mcp.resources import ResourceManager
    from data_tool_mcp.server.app import create_app

    # Setup OpenTelemetry before anything else
    if config.telemetry_otlp or config.telemetry_gcp:
        from data_tool_mcp.telemetry import setup_otel
        setup_otel(
            otlp_endpoint=config.telemetry_otlp,
            gcp_project=config.telemetry_gcp_project if config.telemetry_gcp else None,
            service_name=config.telemetry_service_name,
        )

    # Load config
    config = await load_config(config)

    # Initialize resources
    rm = ResourceManager()
    await _initialize_resources(config, rm)

    # 初始化配置持久化存储（默认在当前目录创建 SQLite 文件 toolbox_data.db）
    from data_tool_mcp.config.store import init_store
    store = await init_store(config.store_url, config.store_username, config.store_password)
    if store.is_persistent:
        await _load_persisted_resources(config, rm, store)

    # Create app
    app = create_app(config, rm)

    # Start hot-reload watcher (if enabled)
    if not config.disable_reload and config.config_folder:
        from data_tool_mcp.config.hotreload import start_hot_reload
        _reload_task = asyncio.create_task(start_hot_reload(config.config_folder, config, rm))

    # Warn if Host header validation is disabled (security risk in production)
    if not config.allowed_hosts:
        import logging
        logging.getLogger(__name__).warning(
            "Host header validation is disabled (no --allowed-hosts configured). "
            "This is acceptable for local development but should be configured in "
            "production to prevent DNS rebinding attacks."
        )

    # Start DB-backed config hot-reload (MySQL 轮询模式)
    if not config.disable_reload and config.config_db_url:
        from data_tool_mcp.config.db_reader import watch_config_changes

        async def _reload_from_db() -> None:
            # Reload config from DB, rebuild resources, then close stale sources
            old_sources = rm.get_sources_map()
            reloaded = await load_config(config)
            await _initialize_resources(reloaded, rm)
            for src in old_sources.values():
                try:
                    if hasattr(src, "close"):
                        await src.close()
                except Exception:
                    pass

        _reload_task = asyncio.create_task(
            watch_config_changes(config.config_db_url, _reload_from_db, config.env_passwords)
        )
        logger = __import__("logging").getLogger(__name__)
        logger.info("DB config hot-reload enabled (MySQL 轮询模式)")

    # Run uvicorn with optional TLS
    uvicorn_config_kwargs = {
        "app": app,
        "host": config.address,
        "port": config.port,
        "log_level": config.log_level.lower(),
    }
    if config.cert_file and config.key_file:
        uvicorn_config_kwargs["ssl_certfile"] = config.cert_file
        uvicorn_config_kwargs["ssl_keyfile"] = config.key_file

    uvicorn_config = uvicorn.Config(**uvicorn_config_kwargs)
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


async def _run_stdio(config: "ServerConfig") -> None:
    """Start STDIO server."""
    from data_tool_mcp.config.loader import load_config
    from data_tool_mcp.resources import ResourceManager
    from data_tool_mcp.server.mcp.protocol import MCPProtocol
    from data_tool_mcp.server.mcp.stdio import STDIOTransport

    if config.telemetry_otlp or config.telemetry_gcp:
        from data_tool_mcp.telemetry import setup_otel
        setup_otel(
            otlp_endpoint=config.telemetry_otlp,
            gcp_project=config.telemetry_gcp_project if config.telemetry_gcp else None,
            service_name=config.telemetry_service_name,
        )

    config = await load_config(config)
    rm = ResourceManager()
    await _initialize_resources(config, rm)

    # 初始化配置持久化存储（默认在当前目录创建 SQLite 文件 toolbox_data.db）
    from data_tool_mcp.config.store import init_store
    store = await init_store(config.store_url, config.store_username, config.store_password)
    if store.is_persistent:
        await _load_persisted_resources(config, rm, store)

    protocol = MCPProtocol(rm)
    transport = STDIOTransport(protocol)
    await transport.run()


async def _initialize_resources(config: "ServerConfig", rm: "ResourceManager") -> None:
    """Initialize all sources, tools, toolsets, prompts, and embedding models from config."""
    from data_tool_mcp.sources import decode_source_config
    from data_tool_mcp.tools import decode_tool_config

    # Initialize sources
    sources_map = {}
    source_configs_map: dict[str, dict[str, Any]] = {}
    for name, src_data in config.source_configs.items():
        src_type = src_data.get("type", "")
        try:
            source_config = decode_source_config(src_type, name, src_data)
            source = await source_config.initialize()
            sources_map[name] = source
            source_configs_map[name] = src_data
        except Exception as exc:
            if config.ignore_unknown_tools:
                import logging
                logging.getLogger(__name__).warning(f"Skipping unknown source type {src_type!r}: {exc}")
            else:
                raise

    # Initialize tools
    tools_map = {}
    tool_types_map = {}
    for name, tool_data in config.tool_configs.items():
        tool_type = tool_data.get("type", "")
        try:
            tool_config = decode_tool_config(tool_type, name, tool_data)
            tool = await tool_config.initialize()
            tools_map[name] = tool
            tool_types_map[name] = tool_type
        except Exception as exc:
            if config.ignore_unknown_tools:
                import logging
                logging.getLogger(__name__).warning(f"Skipping unknown tool type {tool_type!r}: {exc}")
            else:
                raise

    # Initialize toolsets
    toolsets_map = {}
    for name, ts_data in config.toolset_configs.items():
        from data_tool_mcp.resources import Toolset
        tool_names = [t["name"] for t in ts_data.get("tools", []) if "name" in t]
        toolsets_map[name] = Toolset(name=name, tools=tool_names)

    # Initialize prompts
    prompts_map = {}
    for name, p_data in config.prompt_configs.items():
        from data_tool_mcp.prompts import decode_prompt_config
        try:
            prompt_config = decode_prompt_config(p_data.get("type", "custom"), name, p_data)
            prompt = await prompt_config.initialize()
            prompts_map[name] = prompt
        except Exception as exc:
            if config.ignore_unknown_tools:
                import logging
                logging.getLogger(__name__).warning(f"Skipping prompt {name!r}: {exc}")
            else:
                raise

    # Initialize promptsets
    promptsets_map = {}
    for name, ps_data in config.promptset_configs.items():
        from data_tool_mcp.prompts.base import Promptset
        prompt_names = [p["name"] for p in ps_data.get("prompts", []) if "name" in p]
        promptsets_map[name] = Promptset(name=name, prompt_names=prompt_names)

    # Initialize embedding models
    embedding_models_map = {}
    for name, em_data in config.embedding_model_configs.items():
        from data_tool_mcp.embeddingmodels import decode_embedding_model_config
        try:
            em_config = decode_embedding_model_config(em_data.get("type", ""), name, em_data)
            em = await em_config.initialize()
            embedding_models_map[name] = em
        except Exception as exc:
            if config.ignore_unknown_tools:
                import logging
                logging.getLogger(__name__).warning(f"Skipping embedding model {name!r}: {exc}")
            else:
                raise

    rm.set_resources(
        sources=sources_map,
        source_configs=source_configs_map,
        tools=tools_map,
        toolsets=toolsets_map,
        prompts=prompts_map,
        promptsets=promptsets_map,
        embedding_models=embedding_models_map,
        tool_types=tool_types_map,
    )


async def _load_persisted_resources(config, rm, store) -> None:
    """从 ConfigStore 加载持久化的数据源和工具，补充到 ResourceManager。"""
    import logging
    logger = logging.getLogger(__name__)

    from data_tool_mcp.sources import decode_source_config
    from data_tool_mcp.tools import decode_tool_config

    # 加载持久化的数据源
    saved_sources = await store.load_sources()
    for src_data in saved_sources:
        name = src_data.get("name", "")
        src_type = src_data.get("type", "")
        if not name or not src_type:
            continue
        if name in rm.get_sources_map():
            continue  # 已存在（来自 YAML 配置），跳过
        try:
            config_data = {k: v for k, v in src_data.items() if k not in ("name", "type")}
            source_config = decode_source_config(src_type, name, config_data)
            source = await source_config.initialize()
            rm.add_source(name, source, config=config_data)
            logger.info("从存储加载数据源: %s (%s)", name, src_type)
        except Exception as exc:
            logger.warning("加载持久化数据源 %r 失败: %s", name, exc)

    # 加载持久化的工具
    saved_tools = await store.load_tools()
    for tool_data in saved_tools:
        name = tool_data.get("name", "")
        tool_type = tool_data.get("type", "")
        if not name or not tool_type:
            continue
        if name in rm.get_tools_map():
            continue  # 已存在，跳过
        try:
            tool_config = decode_tool_config(tool_type, name, tool_data)
            tool = await tool_config.initialize()
            rm.add_tool(name, tool, tool_type)
            logger.info("从存储加载工具: %s (%s)", name, tool_type)
        except Exception as exc:
            logger.warning("加载持久化工具 %r 失败: %s", name, exc)

    # 确保默认 toolset 存在（包含所有已加载的工具）
    rm.ensure_default_toolset()


if __name__ == "__main__":
    main()
