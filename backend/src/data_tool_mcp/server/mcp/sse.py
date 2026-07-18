"""SSE transport for MCP protocol.

Maps to Go: internal/server/mcp.go SSE handler
"""

from __future__ import annotations

import asyncio
import json
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
        """初始化实例。"""
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
        async for event in self._stream_messages():
            yield event

    async def _stream_messages(self) -> AsyncGenerator[dict, None]:
        """主循环:从队列消费消息,超时发送 ping。"""
        ping_interval = 30.0
        while True:
            event = await self._next_event(ping_interval)
            if event is None:
                break
            yield event

    async def _next_event(self, ping_interval: float):
        """获取下一个事件。None 表示会话应关闭。"""
        try:
            message = await asyncio.wait_for(self.session.event_queue.get(), timeout=ping_interval)
        except asyncio.TimeoutError:
            # No message in ping_interval — send a keepalive ping
            return {"event": "ping", "data": ""}
        except asyncio.CancelledError:
            return None
        return self._message_to_event(message)

    def _message_to_event(self, message):
        """将队列消息转为事件。哨兵 None 返回 None 表示关闭。"""
        if message is None:
            return None
        return {"event": "message", "data": message}

    async def handle_post(self, body: bytes) -> JSONRPCResponse | None:
        """Handle a POST request (client sends JSON-RPC over HTTP).

        Maps to Go: httpHandler — checks for batch requests and rejects them.

        The response is enqueued onto the session's event_queue so the SSE
        stream delivers it as a ``message`` event.  Notifications (no id)
        return None and produce no SSE message (HTTP 202).
        """
        data, error = self._parse_post_body(body)
        if error is not None:
            return error
        request = JSONRPCRequest.from_dict(data)
        response = await self.protocol.handle_request(request)
        if response is None:
            # Notification — no response needed
            return None
        self._enqueue_response(response)
        return response

    def _parse_post_body(self, body: bytes):
        """解析 POST body。成功返回 (data, None);失败返回 (None, error_response)。"""
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            return None, JSONRPCResponse(
                error={"code": -32700, "message": f"parse error: {exc}"},
                id=None,
            )
        if isinstance(data, list):
            return None, JSONRPCResponse(
                error={"code": -32600, "message": "not supporting batch requests"},
                id=None,
            )
        return data, None

    def _enqueue_response(self, response: JSONRPCResponse) -> None:
        """将响应入队到 SSE 流,队列满时丢弃最旧消息重试。"""
        message_json = json.dumps(response.to_dict())
        try:
            self.session.event_queue.put_nowait(message_json)
        except asyncio.QueueFull:
            self._drop_oldest_and_enqueue(message_json)

    def _drop_oldest_and_enqueue(self, message_json: str) -> None:
        """队列满时丢弃最旧消息后重新入队。"""
        try:
            self.session.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        self.session.event_queue.put_nowait(message_json)

    def create_sse_response(self) -> StreamingResponse:
        """Create a Starlette SSE response for GET /sse.

        Includes the Mcp-Session-Id header for protocol version detection.
        """

        async def format_events():
            """生成 SSE 文本流,客户端断开时清理会话。"""
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
