"""Server middleware components.

Maps to Go: internal/server/server.go middleware functions.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的方法、路径、状态码和耗时。

    跳过健康检查端点与 SSE/长连接端点以减少日志噪声。
    错误响应(>=500)用 ERROR,4xx 用 WARNING,其他用 INFO。
    """

    # 健康检查端点,跳过以减少日志噪声
    _HEALTH_PATHS = frozenset({"/live", "/ready"})

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求,记录请求日志。"""
        if self._should_skip(request.url.path):
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        self._log_request(request, response, duration_ms)
        return response

    def _should_skip(self, path: str) -> bool:
        """判断是否跳过日志记录(健康检查与 SSE/长连接端点)。"""
        if path in self._HEALTH_PATHS:
            return True
        return "sse" in path or "message" in path

    def _log_request(self, request: Request, response: Response, duration_ms: int) -> None:
        """按状态码选择日志级别并输出请求日志。"""
        method = request.method
        path = request.url.path
        status_code = response.status_code
        message = f"{method} {path} -> {status_code} ({duration_ms}ms)"
        logger.log(self._level_for(status_code), message)

    def _level_for(self, status_code: int) -> int:
        """根据状态码返回日志级别。"""
        if status_code >= 500:
            return logging.ERROR
        if status_code >= 400:
            return logging.WARNING
        return logging.INFO


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个请求生成或传递请求 ID。

    读取入站 X-Request-ID header,若缺失则生成 8 位短 UUID。
    将请求 ID 放入 request.state.request_id 供后续使用,
    并在响应 header 中回写 X-Request-ID。
    """

    _HEADER = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求,注入请求 ID 并回写响应 header。"""
        request_id = self._resolve_request_id(request)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[self._HEADER] = request_id
        return response

    def _resolve_request_id(self, request: Request) -> str:
        """从入站 header 读取请求 ID,若缺失则生成新的短 UUID。"""
        incoming = request.headers.get(self._HEADER)
        if incoming:
            return incoming
        return uuid.uuid4().hex[:8]


class _BodyTooLargeError(Exception):
    """Internal exception raised when the request body exceeds the limit."""

    def __init__(self, received: int, limit: int):
        """初始化实例。"""
        self.received = received
        self.limit = limit
        super().__init__(f"body size {received} exceeds limit {limit}")
