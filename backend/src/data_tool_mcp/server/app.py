"""FastAPI application factory.

Maps to Go: internal/server/server.go NewServer()
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from data_tool_mcp.config.models import ServerConfig
from data_tool_mcp.resources import ResourceManager
from data_tool_mcp.server.routes import mcp_routes
from data_tool_mcp.server.routes import api_routes
from data_tool_mcp.admin.router import router as admin_router
from data_tool_mcp.server.middleware import (
    HostCheckMiddleware,
    MaxBodySizeMiddleware,
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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifecycle — start/stop SSEManager cleanup routine."""
        await sse_manager.start()
        logger.info("SSEManager cleanup routine started")
        yield
        await sse_manager.stop()
        logger.info("SSEManager cleanup routine stopped")
        # Close all data sources' connections BEFORE closing the config store.
        # 必须在事件循环关闭前关闭 aiomysql 等驱动的底层连接,
        # 否则 GC 触发的 __del__ 会在事件循环已关闭时报 RuntimeError。
        try:
            await resource_manager.close()
            logger.info("ResourceManager sources closed")
        except Exception as exc:
            logger.warning("error closing resource manager sources: %s", exc)
        # Close the config store if present
        from data_tool_mcp.config.store import get_store
        store = get_store()
        if store is not None:
            try:
                await store.close()
            except Exception as exc:
                logger.warning("error closing config store: %s", exc)

    app = FastAPI(
        title="MCP Toolbox",
        version="0.1.0",
        description="MCP Toolbox for Databases",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.resource_manager = resource_manager
    app.state.sse_manager = sse_manager

    # Security middleware — maps to Go: hostCheck + MaxBytesReader
    # Applied before CORS so that invalid hosts are rejected early
    app.add_middleware(HostCheckMiddleware, allowed_hosts=config.allowed_hosts or None)
    app.add_middleware(MaxBodySizeMiddleware, max_size=config.max_body_size)

    # CORS middleware — maps to Go: server.go cors.Handler
    # When allow_origins=["*"], set allow_credentials=False to avoid the
    # invalid combination that browsers reject (and scanners flag).
    if config.allowed_origins:
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

    # 项目标识 header — 所有响应携带 X-Server-Name,便于客户端识别服务来源
    @app.middleware("http")
    async def add_server_name_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Server-Name"] = _SERVER_NAME
        return response

    # Register MCP routes
    mcp_routes.register_routes(app)

    # Register Legacy HTTP API routes (Go: --enable-api flag)
    if config.enable_api:
        app.include_router(api_routes.router)

    # Register Admin UI routes (always enabled)
    app.include_router(admin_router)

    return app
