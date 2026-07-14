"""MCP HTTP routes — SSE + Streamable HTTP + toolset routing.

Maps to Go: internal/server/mcp.go route definitions
"""

from __future__ import annotations


from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from data_tool_mcp.resources import ResourceManager
from data_tool_mcp.server.mcp.protocol import MCPProtocol
from data_tool_mcp.server.mcp.sse import SSETransport
from data_tool_mcp.server.mcp.streamable import StreamableHTTPTransport


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
    if request.client:
        return request.client.host or ""
    return ""


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

    @app.get("/sse")
    async def sse_endpoint(request: Request):
        """SSE transport endpoint.
        
        Go: r.Get("/sse", func(...) { sseHandler(s, w, r) })
        """
        rm: ResourceManager = request.app.state.resource_manager
        base_url = _get_base_url(request)
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(rm, access_token=access_token, client_addr=_get_client_addr(request))
        transport = SSETransport(protocol, base_url=base_url, sse_manager=sse_manager)
        # Register the session so POST /message can find it
        await sse_manager.add(transport.session)
        return transport.create_sse_response()

    @app.post("/message")
    async def message_endpoint(request: Request):
        """Message endpoint for SSE transport (client POSTs here).

        Go: r.Post("/message", func(...) { ... })

        Looks up the SSE session by sessionId query param, processes the
        JSON-RPC request, and enqueues the response onto the session's
        event_queue.  Returns HTTP 202 (Accepted) for successful enqueuing,
        including for notifications (no response body).
        """
        rm: ResourceManager = request.app.state.resource_manager
        # Look up the session by sessionId query param
        session_id = request.query_params.get("sessionId", "")
        if not session_id:
            return JSONResponse(
                status_code=400,
                content={"error": "missing sessionId query parameter"},
            )
        session = await sse_manager.get(session_id)
        if session is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"session not found: {session_id}"},
            )
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(rm, access_token=access_token, client_addr=_get_client_addr(request))
        transport = SSETransport(protocol, session=session)
        body = await request.body()
        response = await transport.handle_post(body)
        # Notifications return None — no response body, HTTP 202
        if response is None:
            return JSONResponse(content={}, status_code=202)
        # For SSE transport, the response is delivered via the SSE stream;
        # HTTP response is 202 Accepted (no body) per MCP SSE spec.
        return JSONResponse(content={}, status_code=202)

    @app.post("/")
    async def streamable_endpoint(request: Request):
        """Streamable HTTP transport endpoint.

        Go: r.Post("/", func(...) { httpHandler(s, w, r) })
        """
        rm: ResourceManager = request.app.state.resource_manager
        # Detect protocol version from header
        version = request.headers.get("mcp-protocol-version", "2025-06-18")
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(rm, version=version, access_token=access_token, client_addr=_get_client_addr(request))
        transport = StreamableHTTPTransport(protocol)
        body = await request.body()
        response = await transport.handle_request(body)
        # Notifications return None — HTTP 202, no body
        if response is None:
            return JSONResponse(content={}, status_code=202)
        return JSONResponse(content=response.to_dict())

    # -- Toolset-scoped routes (/{toolsetName}/) --

    @app.get("/{toolsetName}/sse")
    async def toolset_sse_endpoint(toolsetName: str, request: Request):
        """SSE endpoint scoped to a specific toolset.

        Go: r.Route("/{toolsetName}") → nested /sse
        """
        rm: ResourceManager = request.app.state.resource_manager
        toolset = rm.get_toolset(toolsetName)
        if not toolset:
            return JSONResponse(
                status_code=404,
                content={"error": f"toolset not found: {toolsetName}"},
            )
        base_url = _get_base_url(request)
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(rm, toolset_name=toolsetName, access_token=access_token, client_addr=_get_client_addr(request))
        transport = SSETransport(
            protocol, base_url=base_url, toolset_name=toolsetName, sse_manager=sse_manager
        )
        await sse_manager.add(transport.session)
        return transport.create_sse_response()

    @app.post("/{toolsetName}/message")
    async def toolset_message_endpoint(toolsetName: str, request: Request):
        """Message endpoint for toolset-scoped SSE transport."""
        rm: ResourceManager = request.app.state.resource_manager
        toolset = rm.get_toolset(toolsetName)
        if not toolset:
            return JSONResponse(
                status_code=404,
                content={"error": f"toolset not found: {toolsetName}"},
            )
        session_id = request.query_params.get("sessionId", "")
        if not session_id:
            return JSONResponse(
                status_code=400,
                content={"error": "missing sessionId query parameter"},
            )
        session = await sse_manager.get(session_id)
        if session is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"session not found: {session_id}"},
            )
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(rm, toolset_name=toolsetName, access_token=access_token, client_addr=_get_client_addr(request))
        transport = SSETransport(protocol, toolset_name=toolsetName, session=session)
        body = await request.body()
        response = await transport.handle_post(body)
        if response is None:
            return JSONResponse(content={}, status_code=202)
        return JSONResponse(content={}, status_code=202)

    @app.post("/{toolsetName}/")
    async def toolset_streamable_endpoint(toolsetName: str, request: Request):
        """Streamable HTTP endpoint scoped to a specific toolset.

        Go: r.Route("/{toolsetName}") → nested POST /
        """
        rm: ResourceManager = request.app.state.resource_manager
        toolset = rm.get_toolset(toolsetName)
        if not toolset:
            return JSONResponse(
                status_code=404,
                content={"error": f"toolset not found: {toolsetName}"},
            )
        version = request.headers.get("mcp-protocol-version", "2025-06-18")
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(rm, version=version, toolset_name=toolsetName, access_token=access_token, client_addr=_get_client_addr(request))
        transport = StreamableHTTPTransport(protocol)
        body = await request.body()
        response = await transport.handle_request(body)
        if response is None:
            return JSONResponse(content={}, status_code=202)
        return JSONResponse(content=response.to_dict())

    @app.get("/{toolsetName}/")
    async def toolset_get_endpoint(toolsetName: str, request: Request):
        """GET on toolset — method not allowed (like Go version)."""
        return JSONResponse(
            status_code=405,
            content={"error": "Method not allowed. Use POST for JSON-RPC."},
        )

    # -- System + Source scoped routes (/{systemId}/{sourceName}/) --
    # URL 中同时包含系统编号和数据源名,实际按数据源名过滤工具。

    @app.get("/{systemId}/{sourceName}/sse")
    async def system_source_sse_endpoint(systemId: str, sourceName: str, request: Request):
        """SSE endpoint scoped to a specific source within a system.

        URL: /{systemId}/{sourceName}/sse
        过滤逻辑: 使用 sourceName 对应的 toolset。
        """
        rm: ResourceManager = request.app.state.resource_manager
        toolset = rm.get_toolset(sourceName)
        if not toolset:
            return JSONResponse(
                status_code=404,
                content={"error": f"toolset not found: {sourceName}"},
            )
        base_url = _get_base_url(request)
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(
            rm, toolset_name=sourceName, access_token=access_token,
            system_id=systemId, client_addr=_get_client_addr(request),
        )
        # toolset_name 使用复合路径,确保 message endpoint URL 为 /{systemId}/{sourceName}/message
        transport = SSETransport(
            protocol,
            base_url=base_url,
            toolset_name=f"{systemId}/{sourceName}",
            sse_manager=sse_manager,
        )
        await sse_manager.add(transport.session)
        return transport.create_sse_response()

    @app.post("/{systemId}/{sourceName}/message")
    async def system_source_message_endpoint(systemId: str, sourceName: str, request: Request):
        """Message endpoint for system+source-scoped SSE transport."""
        rm: ResourceManager = request.app.state.resource_manager
        toolset = rm.get_toolset(sourceName)
        if not toolset:
            return JSONResponse(
                status_code=404,
                content={"error": f"toolset not found: {sourceName}"},
            )
        session_id = request.query_params.get("sessionId", "")
        if not session_id:
            return JSONResponse(
                status_code=400,
                content={"error": "missing sessionId query parameter"},
            )
        session = await sse_manager.get(session_id)
        if session is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"session not found: {session_id}"},
            )
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(
            rm, toolset_name=sourceName, access_token=access_token,
            system_id=systemId, client_addr=_get_client_addr(request),
        )
        transport = SSETransport(
            protocol, toolset_name=f"{systemId}/{sourceName}", session=session
        )
        body = await request.body()
        response = await transport.handle_post(body)
        if response is None:
            return JSONResponse(content={}, status_code=202)
        return JSONResponse(content={}, status_code=202)

    @app.post("/{systemId}/{sourceName}/")
    async def system_source_streamable_endpoint(systemId: str, sourceName: str, request: Request):
        """Streamable HTTP endpoint scoped to a specific source within a system."""
        rm: ResourceManager = request.app.state.resource_manager
        toolset = rm.get_toolset(sourceName)
        if not toolset:
            return JSONResponse(
                status_code=404,
                content={"error": f"toolset not found: {sourceName}"},
            )
        version = request.headers.get("mcp-protocol-version", "2025-06-18")
        access_token = _extract_access_token(request)
        protocol = MCPProtocol(
            rm, version=version, toolset_name=sourceName, access_token=access_token,
            system_id=systemId, client_addr=_get_client_addr(request),
        )
        transport = StreamableHTTPTransport(protocol)
        body = await request.body()
        response = await transport.handle_request(body)
        if response is None:
            return JSONResponse(content={}, status_code=202)
        return JSONResponse(content=response.to_dict())

    @app.get("/{systemId}/{sourceName}/")
    async def system_source_get_endpoint(systemId: str, sourceName: str, request: Request):
        """GET on system+source — method not allowed."""
        return JSONResponse(
            status_code=405,
            content={"error": "Method not allowed. Use POST for JSON-RPC."},
        )
