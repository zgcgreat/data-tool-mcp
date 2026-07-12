"""Server middleware components.

Maps to Go: internal/server/server.go middleware functions.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class HostCheckMiddleware(BaseHTTPMiddleware):
    """Check the Host header to prevent DNS rebinding attacks.
    
    Maps to Go: hostCheck middleware in server.go.
    """

    def __init__(self, app, allowed_hosts: list[str] | None = None):
        super().__init__(app)
        # If None or empty, allow all hosts (development mode)
        self.allowed_hosts = allowed_hosts if allowed_hosts else None

    async def dispatch(self, request: Request, call_next) -> Response:
        # If no allowed_hosts configured, allow all (development mode)
        if self.allowed_hosts is None:
            return await call_next(request)
        
        host = request.headers.get("host", "")
        # Remove port if present
        host_name = host.split(":")[0]

        # "*" is a wildcard meaning "allow all hosts" (e.g. when --allowed-hosts "*" is passed)
        if "*" in self.allowed_hosts:
            return await call_next(request)

        if host_name not in self.allowed_hosts:
            return Response(
                content="Invalid host header",
                status_code=403,
            )
        
        return await call_next(request)


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Limit the size of request bodies.
    
    Maps to Go: MaxBytesReader in server.go.

    Enforces the limit by wrapping the ASGI receive callable to count bytes
    as they are read, which correctly handles both Content-Length requests
    and chunked transfer encoding (where Content-Length is absent).
    """

    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            # Fast path: check Content-Length header for early rejection
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_size:
                        return Response(
                            content="Request body too large",
                            status_code=413,
                        )
                except ValueError:
                    pass  # Malformed Content-Length, fall through to stream check

            # Wrap the receive callable to enforce the limit on the actual
            # body stream. This catches chunked transfers and clients that
            # lie about Content-Length.
            original_receive = request._receive

            received = 0
            limit = self.max_size

            async def limited_receive():
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

            try:
                return await call_next(request)
            except _BodyTooLargeError:
                return Response(
                    content="Request body too large",
                    status_code=413,
                )
        return await call_next(request)


class _BodyTooLargeError(Exception):
    """Internal exception raised when the request body exceeds the limit."""

    def __init__(self, received: int, limit: int):
        self.received = received
        self.limit = limit
        super().__init__(f"body size {received} exceeds limit {limit}")


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Global API key authentication middleware.

    When ``api_key`` is configured, all requests (except health checks and
    OPTIONS preflight) must include a valid API key in one of:
      - ``X-API-Key`` header
      - ``Authorization: Bearer <key>`` header

    When ``api_key`` is empty (default), authentication is disabled — this
    matches the "enterprise intranet" trust model, but should be combined
    with network isolation / reverse proxy in production.

    Maps to Go: API key validation in server.go request handlers.
    """

    # Paths that are always accessible without auth (health checks)
    _PUBLIC_PATHS = frozenset({"/admin/health"})

    def __init__(self, app, api_key: str = ""):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:
        # No API key configured → auth disabled (intranet trust model)
        if not self.api_key:
            return await call_next(request)

        # OPTIONS preflight always passes
        if request.method == "OPTIONS":
            return await call_next(request)

        # Health check endpoints are always public
        if request.url.path in self._PUBLIC_PATHS:
            return await call_next(request)

        # Extract the provided key from X-API-Key or Authorization: Bearer
        provided = request.headers.get("x-api-key", "")
        if not provided:
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                provided = auth[7:]

        # Constant-time comparison to prevent timing attacks
        if not provided or not hmac.compare_digest(provided, self.api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key. Provide it via 'X-API-Key' header or 'Authorization: Bearer <key>'."},
            )

        return await call_next(request)
