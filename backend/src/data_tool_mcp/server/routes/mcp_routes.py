"""MCP HTTP routes — SSE + Streamable HTTP + toolset routing.

Maps to Go: internal/server/mcp.go route definitions
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from data_tool_mcp.resources import ResourceManager
from data_tool_mcp.server.mcp.protocol import MCPProtocol
from data_tool_mcp.server.mcp.session import SSESession
from data_tool_mcp.server.mcp.sse import SSETransport
from data_tool_mcp.server.mcp.streamable import StreamableHTTPTransport

# 默认 MCP 协议版本（可被 mcp-protocol-version 请求头覆盖）
_DEFAULT_PROTOCOL_VERSION = "2025-06-18"


def _get_base_url(request: Request) -> str:
    """Derive the base URL from the incoming request.

    Maps to Go: fmt.Sprintf("%s://%s", proto, r.Host)
    Respects X-Forwarded-Proto and X-Forwarded-Host for reverse proxy setups.
    """
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    return f"{proto}://{host}"


def _extract_access_token(request: Request) -> str:
    """Extract access token from the Authorization header.

    Maps to Go: accessToken := tools.AccessToken(r.Header.Get("Authorization"))
    Also checks X-Auth-Token as a fallback for gateway-injected tokens.
    """
    auth = request.headers.get("authorization", "")
    if auth:
        return auth
    # Fallback: gateway-injected token (e.g., from Envoy/Istio)
    return request.headers.get("x-auth-token", "")


def _get_client_addr(request: Request) -> str:
    """提取客户端 IP 地址（用于统计日志），优先取 X-Forwarded-For 首段。"""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return _client_host(request)


def _client_host(request: Request) -> str:
    """从 request.client 获取 host,不可用时返回空串。"""
    if not request.client:
        return ""
    return request.client.host or ""


def _verify_source_belongs_to_system(
    rm: ResourceManager,
    source_name: str,
    system_id: str | None = None,
    environment: str | None = None,
) -> str | None:
    """校验数据源归属:URL 中的 systemId/environment 必须与 source 配置一致。

    防止跨系统访问(如 /systemA/dev/sourceB/sse 访问属于 systemB 的 sourceB)。
    返回 None 表示校验通过,返回字符串表示错误消息(应返回 404)。
    """
    cfg = rm.get_source_config(source_name)
    if cfg is None:
        return f"toolset not found: {source_name}"
    # 校验 system_id(若 URL 中提供)
    if system_id:
        cfg_sid = str(cfg.get("systemId") or cfg.get("system_id") or "")
        if cfg_sid != system_id:
            # systemId 不匹配,返回 404 防止泄露 source 存在性
            return f"toolset not found: {source_name}"
    # 校验 environment(若 URL 中提供)
    if environment:
        cfg_env = str(cfg.get("environment") or "")
        if cfg_env != environment:
            return f"toolset not found: {source_name}"
    return None


# ---------------------------------------------------------------------------
# 共享辅助函数 — 消除路由 handler 间的重复代码
# ---------------------------------------------------------------------------


def _check_toolset(rm: ResourceManager, name: str) -> JSONResponse | None:
    """校验 toolset 存在性,不存在返回 404 JSONResponse,存在返回 None。"""
    toolset = rm.get_toolset(name)
    if not toolset:
        return JSONResponse(
            status_code=404,
            content={"error": f"toolset not found: {name}"},
        )
    return None


def _check_source_access(
    rm: ResourceManager,
    source_name: str,
    system_id: str | None = None,
    environment: str | None = None,
) -> JSONResponse | None:
    """组合校验:source 归属 + toolset 存在性。通过返回 None,失败返回 404。"""
    err = _verify_source_belongs_to_system(rm, source_name, system_id, environment)
    if err:
        return JSONResponse(status_code=404, content={"error": err})
    return _check_toolset(rm, source_name)


async def _get_session_or_error(
    sse_manager: Any, request: Request
) -> tuple[SSESession | None, JSONResponse | None]:
    """从 query param 提取 sessionId 并查找 session。

    返回 (session, error_response):
      - session 找到 → (session, None)
      - 缺少 sessionId → (None, 400)
      - session 不存在 → (None, 404)
    """
    session_id = request.query_params.get("sessionId", "")
    if not session_id:
        return None, JSONResponse(
            status_code=400,
            content={"error": "missing sessionId query parameter"},
        )
    session = await sse_manager.get(session_id)
    if session is None:
        return None, JSONResponse(
            status_code=404,
            content={"error": f"session not found: {session_id}"},
        )
    return session, None


def _build_protocol(
    rm: ResourceManager,
    request: Request,
    *,
    toolset_name: str | None = None,
    system_id: str | None = None,
    environment: str | None = None,
    version: str | None = None,
) -> MCPProtocol:
    """构造 MCPProtocol 实例,统一 access_token / client_addr 提取逻辑。"""
    kwargs: dict[str, Any] = {
        "access_token": _extract_access_token(request),
        "client_addr": _get_client_addr(request),
    }
    if toolset_name is not None:
        kwargs["toolset_name"] = toolset_name
    if system_id is not None:
        kwargs["system_id"] = system_id
    if environment is not None:
        kwargs["environment"] = environment
    if version is not None:
        kwargs["version"] = version
    return MCPProtocol(rm, **kwargs)


def _method_not_allowed() -> JSONResponse:
    """返回 405 Method Not Allowed 响应。"""
    return JSONResponse(
        status_code=405,
        content={"error": "Method not allowed. Use POST for JSON-RPC."},
    )


def _accepted() -> JSONResponse:
    """SSE message 端点统一返回 202 Accepted(通知和请求均如此)。"""
    return JSONResponse(content={}, status_code=202)


async def _handle_streamable_request(protocol: MCPProtocol, request: Request) -> JSONResponse:
    """处理 Streamable HTTP 请求,返回 JSONResponse。"""
    transport = StreamableHTTPTransport(protocol)
    body = await request.body()
    response = await transport.handle_request(body)
    if response is None:
        return _accepted()
    return JSONResponse(content=response.to_dict())


async def _handle_sse_message(
    protocol: MCPProtocol, transport: SSETransport, request: Request
) -> JSONResponse:
    """处理 SSE message POST,统一返回 202 Accepted。"""
    body = await request.body()
    await transport.handle_post(body)
    return _accepted()


def register_routes(app: FastAPI) -> None:
    """Register all MCP routes on the FastAPI app.

    Maps to Go routes:
      GET  /sse          → SSE handler
      POST /message      → SSE message endpoint
      POST /             → Streamable HTTP handler
      GET  /             → Method not allowed
      Same pattern under /{toolsetName}/
    """
    sse_manager = app.state.sse_manager

    # -- Root routes (no toolset scope) --

    @app.get("/sse", tags=["MCP-SSE"])
    async def sse_endpoint(request: Request):
        """SSE transport endpoint.

        Go: r.Get("/sse", func(...) { sseHandler(s, w, r) })
        """
        rm: ResourceManager = request.app.state.resource_manager
        base_url = _get_base_url(request)
        protocol = _build_protocol(rm, request)
        transport = SSETransport(protocol, base_url=base_url, sse_manager=sse_manager)
        # Register the session so POST /message can find it
        await sse_manager.add(transport.session)
        return transport.create_sse_response()

    @app.post("/message", tags=["MCP-SSE"])
    async def message_endpoint(request: Request):
        """Message endpoint for SSE transport (client POSTs here).

        Go: r.Post("/message", func(...) { ... })

        Looks up the SSE session by sessionId query param, processes the
        JSON-RPC request, and enqueues the response onto the session's
        event_queue.  Returns HTTP 202 (Accepted) for successful enqueuing,
        including for notifications (no response body).
        """
        rm: ResourceManager = request.app.state.resource_manager
        session, err = await _get_session_or_error(sse_manager, request)
        if err:
            return err
        protocol = _build_protocol(rm, request)
        transport = SSETransport(protocol, session=session)
        return await _handle_sse_message(protocol, transport, request)

    @app.post("/", tags=["MCP-Streamable"])
    async def streamable_endpoint(request: Request):
        """Streamable HTTP transport endpoint.

        Go: r.Post("/", func(...) { httpHandler(s, w, r) })
        """
        rm: ResourceManager = request.app.state.resource_manager
        version = request.headers.get("mcp-protocol-version", _DEFAULT_PROTOCOL_VERSION)
        protocol = _build_protocol(rm, request, version=version)
        return await _handle_streamable_request(protocol, request)

    # -- Toolset-scoped routes (/{toolsetName}/) --

    @app.get("/{toolsetName}/sse", tags=["MCP-SSE"])
    async def toolset_sse_endpoint(toolsetName: str, request: Request):
        """SSE endpoint scoped to a specific toolset.

        Go: r.Route("/{toolsetName}") → nested /sse
        """
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_toolset(rm, toolsetName)
        if err:
            return err
        base_url = _get_base_url(request)
        protocol = _build_protocol(rm, request, toolset_name=toolsetName)
        transport = SSETransport(
            protocol, base_url=base_url, toolset_name=toolsetName, sse_manager=sse_manager
        )
        await sse_manager.add(transport.session)
        return transport.create_sse_response()

    @app.post("/{toolsetName}/message", tags=["MCP-SSE"])
    async def toolset_message_endpoint(toolsetName: str, request: Request):
        """Message endpoint for toolset-scoped SSE transport."""
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_toolset(rm, toolsetName)
        if err:
            return err
        session, err = await _get_session_or_error(sse_manager, request)
        if err:
            return err
        protocol = _build_protocol(rm, request, toolset_name=toolsetName)
        transport = SSETransport(protocol, toolset_name=toolsetName, session=session)
        return await _handle_sse_message(protocol, transport, request)

    @app.post("/{toolsetName}/", tags=["MCP-Streamable"])
    async def toolset_streamable_endpoint(toolsetName: str, request: Request):
        """Streamable HTTP endpoint scoped to a specific toolset.

        Go: r.Route("/{toolsetName}") → nested POST /
        """
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_toolset(rm, toolsetName)
        if err:
            return err
        version = request.headers.get("mcp-protocol-version", _DEFAULT_PROTOCOL_VERSION)
        protocol = _build_protocol(rm, request, toolset_name=toolsetName, version=version)
        return await _handle_streamable_request(protocol, request)

    @app.get("/{toolsetName}/", tags=["MCP-Streamable"])
    async def toolset_get_endpoint(toolsetName: str, request: Request):
        """GET on toolset — method not allowed (like Go version)."""
        return _method_not_allowed()

    # -- System + Environment + Source scoped routes (/{systemId}/{environment}/{sourceName}/) --
    # URL 中同时包含系统编号、环境和数据源名,实际按数据源名过滤工具。
    # 三段式路由必须注册在两段式路由之前,避免被 /{toolsetName}/... 误匹配。

    @app.get("/{systemId}/{environment}/{sourceName}/sse", tags=["MCP-SSE"])
    async def system_env_source_sse_endpoint(
        systemId: str, environment: str, sourceName: str, request: Request
    ):
        """SSE endpoint scoped to a specific source within a system+environment.

        URL: /{systemId}/{environment}/{sourceName}/sse
        过滤逻辑: 使用 sourceName 对应的 toolset。
        """
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_source_access(rm, sourceName, system_id=systemId, environment=environment)
        if err:
            return err
        base_url = _get_base_url(request)
        protocol = _build_protocol(
            rm, request, toolset_name=sourceName, system_id=systemId, environment=environment
        )
        # toolset_name 使用复合路径,确保 message endpoint URL 为 /{systemId}/{environment}/{sourceName}/message
        transport = SSETransport(
            protocol,
            base_url=base_url,
            toolset_name=f"{systemId}/{environment}/{sourceName}",
            sse_manager=sse_manager,
        )
        await sse_manager.add(transport.session)
        return transport.create_sse_response()

    @app.post("/{systemId}/{environment}/{sourceName}/message", tags=["MCP-SSE"])
    async def system_env_source_message_endpoint(
        systemId: str, environment: str, sourceName: str, request: Request
    ):
        """Message endpoint for system+environment+source-scoped SSE transport."""
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_source_access(rm, sourceName, system_id=systemId, environment=environment)
        if err:
            return err
        session, err = await _get_session_or_error(sse_manager, request)
        if err:
            return err
        protocol = _build_protocol(
            rm, request, toolset_name=sourceName, system_id=systemId, environment=environment
        )
        transport = SSETransport(
            protocol, toolset_name=f"{systemId}/{environment}/{sourceName}", session=session
        )
        return await _handle_sse_message(protocol, transport, request)

    @app.post("/{systemId}/{environment}/{sourceName}/", tags=["MCP-Streamable"])
    async def system_env_source_streamable_endpoint(
        systemId: str, environment: str, sourceName: str, request: Request
    ):
        """Streamable HTTP endpoint scoped to a specific source within a system+environment."""
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_source_access(rm, sourceName, system_id=systemId, environment=environment)
        if err:
            return err
        version = request.headers.get("mcp-protocol-version", _DEFAULT_PROTOCOL_VERSION)
        protocol = _build_protocol(
            rm,
            request,
            toolset_name=sourceName,
            system_id=systemId,
            environment=environment,
            version=version,
        )
        return await _handle_streamable_request(protocol, request)

    @app.get("/{systemId}/{environment}/{sourceName}/", tags=["MCP-Streamable"])
    async def system_env_source_get_endpoint(
        systemId: str, environment: str, sourceName: str, request: Request
    ):
        """GET on system+environment+source — method not allowed."""
        return _method_not_allowed()

    # -- System + Source scoped routes (/{systemId}/{sourceName}/) --
    # URL 中同时包含系统编号和数据源名,实际按数据源名过滤工具。

    @app.get("/{systemId}/{sourceName}/sse", tags=["MCP-SSE"])
    async def system_source_sse_endpoint(systemId: str, sourceName: str, request: Request):
        """SSE endpoint scoped to a specific source within a system.

        URL: /{systemId}/{sourceName}/sse
        过滤逻辑: 使用 sourceName 对应的 toolset。
        """
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_source_access(rm, sourceName, system_id=systemId)
        if err:
            return err
        base_url = _get_base_url(request)
        protocol = _build_protocol(rm, request, toolset_name=sourceName, system_id=systemId)
        # toolset_name 使用复合路径,确保 message endpoint URL 为 /{systemId}/{sourceName}/message
        transport = SSETransport(
            protocol,
            base_url=base_url,
            toolset_name=f"{systemId}/{sourceName}",
            sse_manager=sse_manager,
        )
        await sse_manager.add(transport.session)
        return transport.create_sse_response()

    @app.post("/{systemId}/{sourceName}/message", tags=["MCP-SSE"])
    async def system_source_message_endpoint(systemId: str, sourceName: str, request: Request):
        """Message endpoint for system+source-scoped SSE transport."""
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_source_access(rm, sourceName, system_id=systemId)
        if err:
            return err
        session, err = await _get_session_or_error(sse_manager, request)
        if err:
            return err
        protocol = _build_protocol(rm, request, toolset_name=sourceName, system_id=systemId)
        transport = SSETransport(protocol, toolset_name=f"{systemId}/{sourceName}", session=session)
        return await _handle_sse_message(protocol, transport, request)

    @app.post("/{systemId}/{sourceName}/", tags=["MCP-Streamable"])
    async def system_source_streamable_endpoint(systemId: str, sourceName: str, request: Request):
        """Streamable HTTP endpoint scoped to a specific source within a system."""
        rm: ResourceManager = request.app.state.resource_manager
        err = _check_source_access(rm, sourceName, system_id=systemId)
        if err:
            return err
        version = request.headers.get("mcp-protocol-version", _DEFAULT_PROTOCOL_VERSION)
        protocol = _build_protocol(
            rm, request, toolset_name=sourceName, system_id=systemId, version=version
        )
        return await _handle_streamable_request(protocol, request)

    @app.get("/{systemId}/{sourceName}/", tags=["MCP-Streamable"])
    async def system_source_get_endpoint(systemId: str, sourceName: str, request: Request):
        """GET on system+source — method not allowed."""
        return _method_not_allowed()
