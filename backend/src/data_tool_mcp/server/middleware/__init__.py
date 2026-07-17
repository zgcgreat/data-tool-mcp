"""Server middleware components.

Maps to Go: internal/server/server.go middleware functions.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class HostCheckMiddleware(BaseHTTPMiddleware):
    """Check the Host header to prevent DNS rebinding attacks.
    
    Maps to Go: hostCheck middleware in server.go.
    """

    def __init__(self, app, allowed_hosts: list[str] | None = None):
        """初始化实例。"""
        super().__init__(app)
        # If None or empty, allow all hosts (development mode)
        self.allowed_hosts = allowed_hosts if allowed_hosts else None

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求,执行中间件逻辑。"""
        if self._is_host_allowed(request):
            return await call_next(request)
        return Response(
            content="Invalid host header",
            status_code=403,
        )

    def _is_host_allowed(self, request: Request) -> bool:
        """判断请求的 Host 是否允许。None 或 "*" 表示放行所有。"""
        if self.allowed_hosts is None:
            return True
        if "*" in self.allowed_hosts:
            return True
        host = request.headers.get("host", "")
        # Remove port if present
        host_name = host.split(":")[0]
        return host_name in self.allowed_hosts


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Limit the size of request bodies.
    
    Maps to Go: MaxBytesReader in server.go.

    Enforces the limit by wrapping the ASGI receive callable to count bytes
    as they are read, which correctly handles both Content-Length requests
    and chunked transfer encoding (where Content-Length is absent).
    """

    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        """初始化实例。"""
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求,执行中间件逻辑。"""
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        if self._content_length_exceeds_limit(request):
            return Response(
                content="Request body too large",
                status_code=413,
            )

        self._wrap_receive_with_limit(request)
        return await self._call_with_body_limit(request, call_next)

    def _content_length_exceeds_limit(self, request: Request) -> bool:
        """检查 Content-Length 是否超过限制(Malformed 时回退到流式检查)。"""
        content_length = request.headers.get("content-length")
        if not content_length:
            return False
        try:
            return int(content_length) > self.max_size
        except ValueError:
            return False

    def _wrap_receive_with_limit(self, request: Request) -> None:
        """包装 receive callable,在读取 body 时强制大小限制。
        捕获 chunked transfer 或 Content-Length 不准确的情况。
        """
        original_receive = request._receive

        received = 0
        limit = self.max_size

        async def limited_receive():
            """限制读取字节数的 receive 包装函数。"""
            nonlocal received
            message = await original_receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                received += len(body)
                if received > limit:
                    # Return a 413 by sending an error response.
                    # We can't easily abort the ASGI flow from here,
                    # but the downstream handler will fail when it
                    # tries to read the truncated body.
                    raise _BodyTooLargeError(received, limit)
            return message

        request._receive = limited_receive

    async def _call_with_body_limit(self, request: Request, call_next) -> Response:
        """调用下游 handler,捕获 body 超限异常并返回 413。"""
        try:
            return await call_next(request)
        except _BodyTooLargeError:
            return Response(
                content="Request body too large",
                status_code=413,
            )


class _BodyTooLargeError(Exception):
    """Internal exception raised when the request body exceeds the limit."""

    def __init__(self, received: int, limit: int):
        """初始化实例。"""
        self.received = received
        self.limit = limit
        super().__init__(f"body size {received} exceeds limit {limit}")
