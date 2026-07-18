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
        _apply_env_line(line.strip())


def _is_env_assignment(line: str) -> bool:
    """判断是否为有效的环境变量赋值行。"""
    return bool(line) and not line.startswith("#") and "=" in line


def _apply_env_line(line: str) -> None:
    """解析单行环境变量并写入 os.environ（跳过空行和注释）。"""
    if not _is_env_assignment(line):
        return
    key, val = line.split("=", 1)
    os.environ.setdefault(key.strip(), val.strip())


def _resolve_store_password(raw: str) -> str:
    """解析 TOOLBOX_STORE_PASSWORD 配置值。

    支持两种形式:
      1. 明文密码: 直接返回
      2. 加密密文: 检测到有效密文时解密后返回

    这样企业部署时可在 env 中配置加密后的密文，避免明文密码暴露在
    环境变量或 CI/CD 配置中。加密密钥由 TOOLBOX_ENCRYPTION_KEY 提供，
    加解密实现见 utils/crypto.py（企业可替换为 SM4/KMS）。
    """
    if not raw:
        return ""
    from data_tool_mcp.utils.crypto import decrypt, is_encrypted
    if is_encrypted(raw):
        return decrypt(raw)
    return raw


def _build_parser() -> argparse.ArgumentParser:
    """构建 CLI argparse 解析器。"""
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

    # 配置持久化存储
    serve.add_argument("--store-url", default=os.environ.get("TOOLBOX_STORE_URL"),
                       help="配置持久化存储 URL（留空=默认在当前目录创建 SQLite 文件 toolbox_data.db；"
                            "MySQL 推荐 mysql://host:port/db 不含账号密码，配合 --store-username/--store-password）")
    serve.add_argument("--store-username", default=os.environ.get("TOOLBOX_STORE_USERNAME"),
                       help="配置持久化存储 MySQL 用户名（与 --store-url 分离，避免凭据写在 URL 中）")
    serve.add_argument("--store-password", default=os.environ.get("TOOLBOX_STORE_PASSWORD"),
                       help="配置持久化存储 MySQL 密码（与 --store-url 分离）")
    serve.add_argument("--db-pool-size", type=int, default=int(os.environ.get("TOOLBOX_DB_POOL_SIZE", "5")),
                       help="数据库连接池大小（默认 5，多实例部署时按 实例数×pool_size×数据源数 估算 MySQL max_connections）")
    serve.add_argument("--reload-interval", type=float,
                       default=float(os.environ.get("TOOLBOX_RELOAD_INTERVAL", "5")),
                       help="DB 配置热重载轮询间隔（秒，默认 5）。可设环境变量 TOOLBOX_RELOAD_INTERVAL")

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

    # 数据源类型白名单:仅启用的类型会出现在 /mcp-api/source-types 与创建数据源接口
    # 格式: 逗号分隔,例如 postgres,mysql,redis。留空 = 全部启用
    serve.add_argument("--enabled-source-types", default=os.environ.get("TOOLBOX_ENABLED_SOURCE_TYPES"),
                       help="启用的数据源类型白名单(逗号分隔,留空=全部启用)。"
                            "示例: postgres,mysql,redis。可设环境变量 TOOLBOX_ENABLED_SOURCE_TYPES")

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
    """CLI 主入口。"""
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


def _or_default(value, default):
    """返回 value 或 default（用于处理 None/空值参数）。"""
    return value or default


def _join_comma(values):
    """将列表用逗号拼接为字符串，空列表返回空字符串。"""
    return ",".join(values) if values else ""


def _parse_csv_list(raw: str) -> list:
    """逗号分隔字符串 → 去空白的列表。"""
    return [t.strip() for t in raw.split(",") if t.strip()]


def _split_source_types(raw):
    """逗号分隔字符串 → 去空白的列表。"""
    if not raw:
        return []
    return _parse_csv_list(raw)


def _build_server_config(args: argparse.Namespace):
    """从 CLI 参数构造 ServerConfig。"""
    from data_tool_mcp.config.models import ServerConfig

    return ServerConfig(
        address=args.address,
        port=args.port,
        stdio=args.stdio,
        log_level=args.log_level,
        logging_format=args.logging_format,
        disable_reload=args.disable_reload,
        enable_api=args.enable_api,
        enable_draft_specs=args.enable_draft_specs,
        cert_file=_or_default(args.tls_cert, ""),
        key_file=_or_default(args.tls_key, ""),
        config_file=_or_default(args.config, ""),
        config_files=_or_default(args.configs, []),
        config_folder=_or_default(args.config_folder, ""),
        prebuilt=_join_comma(args.prebuilt),
        config_db_url=_or_default(args.config_db_url, ""),
        env_passwords=_or_default(args.env_passwords, ""),
        telemetry_otlp=_or_default(args.telemetry_otlp, ""),
        telemetry_gcp=args.telemetry_gcp,
        telemetry_gcp_project=_or_default(args.telemetry_gcp_project, ""),
        telemetry_service_name=args.telemetry_service_name,
        sql_commenter=args.sql_commenter,
        allowed_origins=_or_default(args.allowed_origins, ["*"]),
        # Default to [] -> middleware treats empty list as None and allows all hosts
        # (development mode). Passing ["*"] would enable checking against a literal "*"
        # host and reject everything, so we never default to ["*"].
        allowed_hosts=_or_default(args.allowed_hosts, []),
        ignore_unknown_tools=args.ignore_unknown_tools,
        user_agent_metadata=_or_default(args.user_agent_metadata, []),
        store_url=_or_default(args.store_url, ""),
        store_username=_or_default(args.store_username, ""),
        store_password=_resolve_store_password(_or_default(args.store_password, "")),
        db_pool_size=args.db_pool_size,
        reload_interval=args.reload_interval,
        enabled_source_types=_split_source_types(args.enabled_source_types),
    )


def _setup_logging(config: "ServerConfig") -> None:
    """根据 config.logging_format 配置根日志器。

    - standard: 默认人类可读格式
    - json: 结构化 JSON 日志(ELK/Loki/Datadog 友好),
      字段包含 timestamp/level/name/message,便于日志聚合平台查询。

    uvicorn 与应用代码共享根日志器配置,确保输出格式一致。
    """
    import logging

    level = getattr(logging, config.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # 清空现有 handlers,避免重复输出
    for handler in list(root.handlers):
        root.removeHandler(handler)

    if config.logging_format == "json":
        try:
            from pythonjsonlogger import jsonlogger
        except ImportError:
            # 优雅降级:未安装 python-json-logger 时回退到 standard 格式
            logging.basicConfig(
                level=level,
                format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            logging.getLogger(__name__).warning(
                "python-json-logger 未安装,回退到 standard 日志格式。"
                "请安装: pip install python-json-logger"
            )
            return

        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
            json_ensure_ascii=False,
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def _cmd_serve(args: argparse.Namespace) -> None:
    """执行 serve 子命令,启动 HTTP/STDIO 服务。"""
    server_config = _build_server_config(args)
    _setup_logging(server_config)
    if args.stdio:
        asyncio.run(_run_stdio(server_config))
    else:
        asyncio.run(_run_http(server_config))


def _telemetry_gcp_project(config: "ServerConfig") -> str | None:
    """启用 GCP 遥测时返回 project id,否则返回 None。"""
    return config.telemetry_gcp_project if config.telemetry_gcp else None


async def _setup_telemetry(config: "ServerConfig") -> None:
    """配置启用时初始化 OpenTelemetry。"""
    if not config.telemetry_otlp and not config.telemetry_gcp:
        return
    from data_tool_mcp.telemetry import setup_otel
    setup_otel(
        otlp_endpoint=config.telemetry_otlp,
        gcp_project=_telemetry_gcp_project(config),
        service_name=config.telemetry_service_name,
    )


async def _prepare_runtime(config: "ServerConfig"):
    """校验加密密钥、设置遥测、加载配置、初始化资源与存储。返回 (config, rm, store)。"""
    from data_tool_mcp.config.loader import load_config
    from data_tool_mcp.config.store import init_store
    from data_tool_mcp.resources import ResourceManager
    from data_tool_mcp.utils.crypto import validate_encryption_key, is_encryption_available

    validate_encryption_key()
    _validate_production_security(config)
    await _setup_telemetry(config)
    config = await load_config(config)
    rm = ResourceManager()
    await _initialize_resources(config, rm)
    store = await init_store(config.store_url, config.store_username, config.store_password)
    return config, rm, store


def _is_production_mode(config: "ServerConfig") -> bool:
    """判断是否为生产模式:监听非本地地址 或 APP_ENV=production。"""
    if os.environ.get("APP_ENV", "").lower() == "production":
        return True
    # 监听 0.0.0.0 或非 loopback 地址视为生产
    if config.address in ("0.0.0.0", "::"):
        return True
    return False


def _validate_production_security(config: "ServerConfig") -> None:
    """生产模式安全校验:加密必须可用,否则拒绝启动。

    防止生产环境误用开发回退密钥或未安装 cryptography 导致明文存储密码。
    """
    if not _is_production_mode(config):
        return
    if not is_encryption_available():
        sys.exit(
            "FATAL: 生产模式(监听 0.0.0.0 或 APP_ENV=production)下加密不可用。\n"
            "请确保:\n"
            "  1. 已安装 cryptography: pip install cryptography\n"
            "  2. 已配置 TOOLBOX_ENCRYPTION_KEY 环境变量(urlsafe-base64 编码的 32 字节)\n"
            "     生成命令: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
            "多实例部署必须使用相同密钥,否则无法解密数据源密码。"
        )


def _warn_sqlite_remote(store, config: "ServerConfig") -> None:
    """SQLite 存储且监听非本地地址时警告多实例部署风险。"""
    if not store.is_sqlite:
        return
    if config.address in ("127.0.0.1", "localhost"):
        return
    import logging
    logging.getLogger(__name__).warning(
        "当前使用 SQLite 存储且监听地址为 %s，多实例部署将导致数据不一致。"
        "请配置 --store-url 指向共享 MySQL。",
        config.address,
    )


def _start_folder_hot_reload(config: "ServerConfig", rm: "ResourceManager") -> None:
    """启用配置目录热重载（若启用且配置了目录）。"""
    if config.disable_reload or not config.config_folder:
        return
    from data_tool_mcp.config.hotreload import start_hot_reload
    asyncio.create_task(start_hot_reload(config.config_folder, config, rm))


def _warn_hosts_disabled(config: "ServerConfig") -> None:
    """未配置 allowed_hosts 时警告 Host 头校验缺失。"""
    if config.allowed_hosts:
        return
    import logging
    logging.getLogger(__name__).warning(
        "Host header validation is disabled (no --allowed-hosts configured). "
        "This is acceptable for local development but should be configured in "
        "production to prevent DNS rebinding attacks."
    )


async def _close_source_quietly(src) -> None:
    """静默关闭 source 连接（忽略异常）。"""
    if not hasattr(src, "close"):
        return
    try:
        await src.close()
    except Exception:
        pass


async def _close_sources(sources_map: dict) -> None:
    """批量关闭旧 source 连接。"""
    for src in sources_map.values():
        await _close_source_quietly(src)


async def _start_db_reload_watcher(config: "ServerConfig", rm: "ResourceManager") -> None:
    """启用 DB 配置热重载（MySQL 轮询模式，若启用且配置了 config_db_url）。"""
    if config.disable_reload or not config.config_db_url:
        return
    from data_tool_mcp.config.db_reader import watch_config_changes
    from data_tool_mcp.config.loader import load_config

    async def _reload_from_db() -> None:
        """DB 热重载回调:重新加载配置并替换资源,关闭旧 source 连接。"""
        old_sources = rm.get_sources_map()
        reloaded = await load_config(config)
        await _initialize_resources(reloaded, rm)
        await _close_sources(old_sources)

    asyncio.create_task(
        watch_config_changes(
            config.config_db_url, _reload_from_db, config.env_passwords,
            poll_interval=config.reload_interval,
        )
    )
    import logging
    logging.getLogger(__name__).info(
        "DB config hot-reload enabled (MySQL 轮询模式, 间隔 %.1fs)", config.reload_interval
    )


async def _serve_uvicorn(app, config: "ServerConfig") -> None:
    """启动 uvicorn HTTP 服务（支持可选 TLS）。"""
    import uvicorn
    kwargs = {
        "app": app,
        "host": config.address,
        "port": config.port,
        "log_level": config.log_level.lower(),
    }
    if config.cert_file and config.key_file:
        kwargs["ssl_certfile"] = config.cert_file
        kwargs["ssl_keyfile"] = config.key_file
    server = uvicorn.Server(uvicorn.Config(**kwargs))
    await server.serve()


async def _run_http(config: "ServerConfig") -> None:
    """Start HTTP server (SSE + Streamable)."""
    from data_tool_mcp.server.app import create_app

    config, rm, store = await _prepare_runtime(config)
    _warn_sqlite_remote(store, config)
    if store.is_persistent:
        await _load_persisted_resources(config, rm, store)
    app = create_app(config, rm)
    _start_folder_hot_reload(config, rm)
    _warn_hosts_disabled(config)
    await _start_db_reload_watcher(config, rm)
    await _serve_uvicorn(app, config)


async def _run_stdio(config: "ServerConfig") -> None:
    """Start STDIO server."""
    from data_tool_mcp.server.mcp.protocol import MCPProtocol
    from data_tool_mcp.server.mcp.stdio import STDIOTransport

    config, rm, store = await _prepare_runtime(config)
    if store.is_persistent:
        await _load_persisted_resources(config, rm, store)
    protocol = MCPProtocol(rm)
    transport = STDIOTransport(protocol)
    await transport.run()


def _log_or_raise(exc: Exception, ignore: bool, message: str) -> None:
    """根据 ignore 标志跳过异常(记日志)或重新抛出。"""
    if ignore:
        import logging
        logging.getLogger(__name__).warning(message)
        return
    raise exc


async def _decode_and_init(name, data, decode_fn, ignore, make_msg, default_type=""):
    """解码并初始化单个资源。失败时根据 ignore 跳过或抛出。返回 (obj, type)。"""
    item_type = data.get("type", default_type)
    try:
        cfg = decode_fn(item_type, name, data)
        obj = await cfg.initialize()
        return obj, item_type
    except Exception as exc:
        _log_or_raise(exc, ignore, make_msg(name, item_type, exc))
        return None, item_type


async def _init_decoded_items(items, decode_fn, ignore, make_msg, default_type=""):
    """批量 decode + initialize，返回 (objs, types)。"""
    objs = {}
    types = {}
    for name, data in items.items():
        obj, item_type = await _decode_and_init(name, data, decode_fn, ignore, make_msg, default_type)
        if obj is None:
            continue
        objs[name] = obj
        types[name] = item_type
    return objs, types


def _extract_names(items: list) -> list:
    """从配置项列表中提取 name 字段。"""
    return [item["name"] for item in items if "name" in item]


def _build_toolsets(toolset_configs):
    """从配置构建 toolset 映射。"""
    from data_tool_mcp.resources import Toolset
    result = {}
    for name, ts_data in toolset_configs.items():
        result[name] = Toolset(name=name, tools=_extract_names(ts_data.get("tools", [])))
    return result


def _build_promptsets(promptset_configs):
    """从配置构建 promptset 映射。"""
    from data_tool_mcp.prompts.base import Promptset
    result = {}
    for name, ps_data in promptset_configs.items():
        result[name] = Promptset(name=name, prompt_names=_extract_names(ps_data.get("prompts", [])))
    return result


async def _initialize_resources(config: "ServerConfig", rm: "ResourceManager") -> None:
    """Initialize all sources, tools, toolsets, prompts, and embedding models from config."""
    from data_tool_mcp.sources import decode_source_config
    from data_tool_mcp.tools import decode_tool_config
    from data_tool_mcp.prompts import decode_prompt_config
    from data_tool_mcp.embeddingmodels import decode_embedding_model_config

    ignore = config.ignore_unknown_tools

    sources_map, _ = await _init_decoded_items(
        config.source_configs, decode_source_config, ignore,
        lambda n, t, e: f"Skipping unknown source type {t!r}: {e}",
    )
    source_configs_map = {name: config.source_configs[name] for name in sources_map}

    tools_map, tool_types_map = await _init_decoded_items(
        config.tool_configs, decode_tool_config, ignore,
        lambda n, t, e: f"Skipping unknown tool type {t!r}: {e}",
    )

    toolsets_map = _build_toolsets(config.toolset_configs)

    prompts_map, _ = await _init_decoded_items(
        config.prompt_configs, decode_prompt_config, ignore,
        lambda n, t, e: f"Skipping prompt {n!r}: {e}",
        default_type="custom",
    )

    promptsets_map = _build_promptsets(config.promptset_configs)

    embedding_models_map, _ = await _init_decoded_items(
        config.embedding_model_configs, decode_embedding_model_config, ignore,
        lambda n, t, e: f"Skipping embedding model {n!r}: {e}",
    )

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


def _has_name_and_type(name, item_type):
    """检查持久化项是否有有效的 name 和 type。"""
    return bool(name and item_type)


def _build_source_config_data(src_data, src_type):
    """从持久化数据构建 source 配置（去除 name，保留 type）。"""
    config_data = dict(src_data)
    config_data.pop("name", None)
    config_data.pop("type", None)
    config_data["type"] = src_type
    return config_data


def _try_add_source_config(rm, name, src_type, src_data, logger):
    """尝试添加持久化 source 配置，失败时记录警告。"""
    try:
        rm.add_source_config(name, _build_source_config_data(src_data, src_type))
        logger.info("从存储加载数据源配置(惰性): %s (%s)", name, src_type)
    except Exception as exc:
        logger.warning("加载持久化数据源 %r 失败: %s", name, exc)


def _load_one_source(rm, src_data, logger):
    """加载单个持久化 source（仅存配置，惰性初始化）。"""
    name = src_data.get("name", "")
    src_type = src_data.get("type", "")
    if not _has_name_and_type(name, src_type):
        return
    if rm.has_source(name):
        return
    _try_add_source_config(rm, name, src_type, src_data, logger)


async def _try_add_tool(rm, name, tool_type, tool_data, decode_fn, logger):
    """尝试解码、初始化并添加持久化工具，失败时记录警告。"""
    try:
        tool_config = decode_fn(tool_type, name, tool_data)
        tool = await tool_config.initialize()
        rm.add_tool(name, tool, tool_type)
        logger.info("从存储加载工具: %s (%s)", name, tool_type)
    except Exception as exc:
        logger.warning("加载持久化工具 %r 失败: %s", name, exc)


async def _load_one_tool(rm, tool_data, decode_fn, logger):
    """加载单个持久化工具（全量初始化）。"""
    name = tool_data.get("name", "")
    tool_type = tool_data.get("type", "")
    if not _has_name_and_type(name, tool_type):
        return
    if name in rm.get_tools_map():
        return
    await _try_add_tool(rm, name, tool_type, tool_data, decode_fn, logger)


async def _load_persisted_resources(config, rm, store) -> None:
    """从 ConfigStore 加载持久化的数据源和工具，补充到 ResourceManager。

    方案 C: 数据源仅加载配置(不 initialize),首次 MCP 调用时惰性初始化。
    工具仍全量加载(无连接池开销)。
    """
    import logging
    logger = logging.getLogger(__name__)

    from data_tool_mcp.tools import decode_tool_config

    for src_data in await store.load_sources():
        _load_one_source(rm, src_data, logger)

    for tool_data in await store.load_tools():
        await _load_one_tool(rm, tool_data, decode_tool_config, logger)

    rm.ensure_default_toolset()


if __name__ == "__main__":
    main()
