"""FastAPI application factory.

Maps to Go: internal/server/server.go NewServer()
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from data_tool_mcp.config.models import ServerConfig
from data_tool_mcp.resources import ResourceManager
from data_tool_mcp.server.routes import mcp_routes
from data_tool_mcp.server.routes import api_routes
from data_tool_mcp.admin.router import router as admin_router
from data_tool_mcp.server.middleware import (
    HostCheckMiddleware,
    MaxBodySizeMiddleware,
    RequestIdMiddleware,
    RequestLoggingMiddleware,
)
from data_tool_mcp.server.mcp.session import SSEManager

logger = logging.getLogger(__name__)

# 项目标识 — 所有 HTTP 响应都会携带此 header,便于客户端识别服务来源
_SERVER_NAME = "data-tool-mcp"


def create_app(config: ServerConfig, resource_manager: ResourceManager) -> FastAPI:
    """Create and configure the FastAPI application."""
    # Initialize SSE session manager
    # Maps to Go: sseManager := newSseManager(ctx)
    sse_manager = SSEManager()
    app = FastAPI(
        title="MCP Toolbox",
        version="0.1.0",
        description="MCP Toolbox for Databases",
        lifespan=_build_lifespan(sse_manager, resource_manager),
    )
    _init_app_state(app, config, resource_manager, sse_manager)
    _add_middleware(app, config)
    _add_server_name_middleware(app)
    _register_routers(app, config)
    _register_exception_handlers(app)
    return app


def _build_lifespan(sse_manager: SSEManager, resource_manager: ResourceManager):
    """构建应用 lifespan 上下文管理器。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifecycle — start/stop SSEManager cleanup routine."""
        await sse_manager.start()
        logger.info("SSEManager cleanup routine started")
        yield
        await sse_manager.stop()
        logger.info("SSEManager cleanup routine stopped")
        await _close_resources(resource_manager)

    return lifespan


async def _close_resources(resource_manager: ResourceManager) -> None:
    """关闭 resource manager 和 config store。
    必须在事件循环关闭前关闭 aiomysql 等驱动的底层连接,
    否则 GC 触发的 __del__ 会在事件循环已关闭时报 RuntimeError。
    """
    try:
        await resource_manager.close()
        logger.info("ResourceManager sources closed")
    except Exception as exc:
        logger.warning("error closing resource manager sources: %s", exc)
    await _close_config_store()


async def _close_config_store() -> None:
    """关闭 config store(若存在)。"""
    from data_tool_mcp.config.store import get_store

    store = get_store()
    if store is None:
        return
    try:
        await store.close()
    except Exception as exc:
        logger.warning("error closing config store: %s", exc)


def _init_app_state(
    app: FastAPI, config: ServerConfig, resource_manager: ResourceManager, sse_manager: SSEManager
) -> None:
    """初始化 app.state。"""
    app.state.config = config
    app.state.resource_manager = resource_manager
    app.state.sse_manager = sse_manager


def _add_middleware(app: FastAPI, config: ServerConfig) -> None:
    """添加中间件(请求 ID + 日志 + 安全 + CORS)。"""
    # Starlette 中间件是洋葱模型:先添加的在最外层(inbound 最先执行,outbound 最后执行)。
    # RequestIdMiddleware 必须在最外层,确保所有后续中间件和异常处理器都能访问 request.state.request_id。
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    # Security middleware — maps to Go: hostCheck + MaxBytesReader
    # Applied before CORS so that invalid hosts are rejected early
    app.add_middleware(HostCheckMiddleware, allowed_hosts=config.allowed_hosts or None)
    app.add_middleware(MaxBodySizeMiddleware, max_size=config.max_body_size)
    if config.allowed_origins:
        _add_cors_middleware(app, config)


def _add_cors_middleware(app: FastAPI, config: ServerConfig) -> None:
    """添加 CORS 中间件。"""
    # When allow_origins=["*"], set allow_credentials=False to avoid the
    # invalid combination that browsers reject (and scanners flag).
    is_wildcard = config.allowed_origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=not is_wildcard,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "X-CSRF-Token",
            "Mcp-Session-Id",
            "MCP-Protocol-Version",
        ],
        expose_headers=["Mcp-Session-Id"],
        max_age=300,
    )


def _add_server_name_middleware(app: FastAPI) -> None:
    """添加 X-Server-Name 响应 header 中间件。"""

    # 项目标识 header — 所有响应携带 X-Server-Name,便于客户端识别服务来源
    @app.middleware("http")
    async def add_server_name_header(request: Request, call_next):
        """为所有响应添加 X-Server-Name header。"""
        response = await call_next(request)
        response.headers["X-Server-Name"] = _SERVER_NAME
        return response


def _register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器,捕获所有未处理异常。"""

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """捕获未处理异常,返回 500 并记录 ERROR 日志(含异常堆栈)。"""
        # FastAPI 内置 HTTPException 与 RequestValidationError 的处理器优先级更高,
        # 通常不会进入此 handler;此处显式排除以防万一。
        if isinstance(exc, (HTTPException, RequestValidationError)):
            raise exc
        request_id = getattr(request.state, "request_id", "")
        logger.exception(
            "unhandled exception | request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "内部服务器错误",
                "request_id": request_id,
            },
        )


def _register_routers(app: FastAPI, config: ServerConfig) -> None:
    """注册路由。"""

    # Health check — 兼容旧端点,等价于 /live (轻量级探针,不查依赖)
    @app.get("/health")
    async def health() -> dict:
        """健康检查端点(向后兼容),返回服务存活状态。"""
        return {"status": "ok"}

    # Liveness — 进程存活探针。K8s/Docker 用于判断是否需要重启容器。
    # 永远返回 200(只要事件循环还在跑),不查任何依赖。
    @app.get("/live")
    async def live() -> dict:
        """Liveness probe — 进程存活即返回 ok。"""
        return {"status": "ok"}

    # Readiness — 就绪探针。K8s 用于判断是否可以把流量打到本实例。
    # 检查 ResourceManager 与 ConfigStore 是否已初始化。
    @app.get("/ready")
    async def ready(request: Request) -> dict:
        """Readiness probe — 检查依赖是否就绪。"""
        rm: ResourceManager | None = getattr(request.app.state, "resource_manager", None)
        if rm is None:
            return {"status": "not_ready", "reason": "resource_manager unavailable"}

        from data_tool_mcp.config.store import get_store

        store = get_store()
        if store is None:
            return {"status": "not_ready", "reason": "config_store not initialized"}

        return {
            "status": "ok",
            "sources": len(rm.get_all_source_configs()),
        }

    # Register MCP routes
    mcp_routes.register_routes(app)
    # Register Legacy HTTP API routes (Go: --enable-api flag)
    if config.enable_api:
        app.include_router(api_routes.router)
    # Register Admin UI routes (always enabled)
    app.include_router(admin_router)
