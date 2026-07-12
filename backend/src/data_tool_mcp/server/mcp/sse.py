"""SSE transport for MCP protocol.

Maps to Go: internal/server/mcp.go SSE handler
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator

from starlette.responses import StreamingResponse

from data_tool_mcp.server.mcp.protocol import JSONRPCRequest, JSONRPCResponse, MCPProtocol
from data_tool_mcp.server.mcp.session import SSEManager, SSESession


class SSETransport:
    """Server-Sent Events transport for MCP.

    Go: GET /sse → sseHandler()
    Client connects via SSE, sends requests via POST.

    The SSE endpoint sends an initial 'endpoint' event containing the full URL
    where the client should POST its JSON-RPC messages. This URL includes:
    - The host from the original request
    - The session ID for correlation
    - The toolset path segment (if applicable)

    After the initial endpoint event, the SSE stream stays open and delivers
    JSON-RPC responses (as ``message`` events) that are produced by POST
    requests to /message?sessionId=...  Responses are routed through the
    SSESession's event_queue.
    """

    def __init__(
        self,
        protocol: MCPProtocol,
        base_url: str = "",
        toolset_name: str = "",
        sse_manager: SSEManager | None = None,
        session: SSESession | None = None,
    ):
        self.protocol = protocol
        self._base_url = base_url
        self._toolset_name = toolset_name
        self._sse_manager = sse_manager
        # If a session is provided (POST path), reuse it; otherwise create one (GET path).
        if session is not None:
            self.session = session
        else:
            self.session = SSESession()
            self.session.toolset_name = toolset_name
        self._message_endpoint = self._build_endpoint()

    def _build_endpoint(self) -> str:
        """Build the message endpoint URL.

        Maps to Go: fmt.Sprintf("%s://%s/mcp%s?%s", proto, r.Host, toolsetURL, q.Encode())

        The endpoint must be a full URL so the client knows where to POST.
        """
        toolset_path = f"/{self._toolset_name}" if self._toolset_name else ""
        if self._base_url:
            return f"{self._base_url}{toolset_path}/message?sessionId={self.session.id}"
        # Fallback: relative path (client may resolve against its own base)
        return f"{toolset_path}/message?sessionId={self.session.id}"

    async def event_stream(self) -> AsyncGenerator[dict, None]:
        """Generate SSE events for the initial connection.

        Sends the 'endpoint' event so the client knows where to POST.
        Then keeps the connection alive with periodic ping events and
        delivers ``message`` events from the session's event_queue.

        Maps to Go: sseHandler() — sends endpoint, then ranges over
        session.eventChan to flush JSON-RPC responses.
        """
        # First event: tell client the message endpoint
        yield {
            "event": "endpoint",
            "data": self._message_endpoint,
        }

        # Main loop: consume messages from the session queue + send periodic pings
        ping_interval = 30.0
        while True:
            try:
                # Wait for a message from the queue with a timeout for ping
                message = await asyncio.wait_for(
                    self.session.event_queue.get(), timeout=ping_interval
                )
                if message is None:
                    # None is a sentinel signaling the session should close
                    break
                yield {
                    "event": "message",
                    "data": message,
                }
            except asyncio.TimeoutError:
                # No message in ping_interval — send a keepalive ping
                yield {
                    "event": "ping",
                    "data": "",
                }
            except asyncio.CancelledError:
                break

    async def handle_post(self, body: bytes) -> JSONRPCResponse | None:
        """Handle a POST request (client sends JSON-RPC over HTTP).

        Maps to Go: httpHandler — checks for batch requests and rejects them.

        The response is enqueued onto the session's event_queue so the SSE
        stream delivers it as a ``message`` event.  Notifications (no id)
        return None and produce no SSE message (HTTP 202).
        """
        # Check for batch requests (array format)
        try:
            data = json.loads(body)
            if isinstance(data, list):
                return JSONRPCResponse(
                    error={"code": -32600, "message": "not supporting batch requests"},
                    id=None,
                )
        except json.JSONDecodeError as exc:
            return JSONRPCResponse(
                error={"code": -32700, "message": f"parse error: {exc}"},
                id=None,
            )
        request = JSONRPCRequest.from_dict(data)
        response = await self.protocol.handle_request(request)
        if response is None:
            # Notification — no response needed
            return None
        # Enqueue the JSON-RPC response onto the SSE stream
        message_json = json.dumps(response.to_dict())
        try:
            self.session.event_queue.put_nowait(message_json)
        except asyncio.QueueFull:
            # Queue is full — drop oldest and retry
            try:
                self.session.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.session.event_queue.put_nowait(message_json)
        return response

    def create_sse_response(self) -> StreamingResponse:
        """Create a Starlette SSE response for GET /sse.

        Includes the Mcp-Session-Id header for protocol version detection.
        """

        async def format_events():
            try:
                async for event in self.event_stream():
                    event_type = event.get("event", "message")
                    data = event.get("data", "")
                    # SSE spec: each line of data must be prefixed with "data:"
                    # Handle multi-line data by splitting on newlines
                    if isinstance(data, str) and "\n" in data:
                        lines = data.split("\n")
                        data_str = "\n".join(f"data: {line}" for line in lines)
                    else:
                        data_str = f"data: {data}"
                    yield f"event: {event_type}\n{data_str}\n\n"
            except asyncio.CancelledError:
                # Client disconnected — clean up session
                if self._sse_manager is not None:
                    await self._sse_manager.remove(self.session.id)
                raise

        response = StreamingResponse(format_events(), media_type="text/event-stream")
        response.headers["Mcp-Session-Id"] = self.session.id
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        return response
