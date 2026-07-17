"""Streamable HTTP transport for MCP protocol.

Maps to Go: internal/server/mcp.go httpHandler() with Streamable HTTP
"""

from __future__ import annotations

import json
from typing import AsyncGenerator

from data_tool_mcp.server.mcp.protocol import JSONRPCRequest, JSONRPCResponse, MCPProtocol


class StreamableHTTPTransport:
    """Streamable HTTP transport for MCP.

    Go: POST / with Content-Type application/json
    Single request → single response (or streaming for progress).
    """

    def __init__(self, protocol: MCPProtocol):
        """初始化实例。"""
        self.protocol = protocol

    async def handle_request(self, body: bytes) -> JSONRPCResponse | None:
        """Handle a Streamable HTTP request."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            return JSONRPCResponse(
                error={"code": -32700, "message": f"parse error: {exc}"},
                id=None,
            )
        request = JSONRPCRequest.from_dict(data)
        return await self.protocol.handle_request(request)

    async def handle_streaming(self, body: bytes) -> AsyncGenerator[bytes, None]:
        """Handle a streaming request (for progress notifications)."""
        response = await self.handle_request(body)
        yield json.dumps(response.to_dict()).encode()
