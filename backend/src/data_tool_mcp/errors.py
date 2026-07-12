"""Error classification system for MCP Toolbox.

Maps to Go: internal/util/util.go ToolboxError / AgentError / ClientServerError
"""

from __future__ import annotations

from typing import Any


class ToolboxError(Exception):
    """Base error for all MCP Toolbox errors.

    Maps to Go: ToolboxError interface.
    """
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.message = message
        self.code = code

    def to_jsonrpc_error(self) -> dict:
        """Convert to a JSON-RPC error object."""
        return {
            "code": self.code,
            "message": self.message,
        }


class AgentError(ToolboxError):
    """Error caused by the AI agent (client-side).

    Maps to Go: AgentError — code 200.
    These are errors where the agent sent invalid or inappropriate input.
    The client should adjust its behavior and retry.
    """
    def __init__(self, message: str):
        super().__init__(message, code=200)


class ClientServerError(ToolboxError):
    """Error with an HTTP status code.

    Maps to Go: ClientServerError — maps HTTP status codes to JSON-RPC.
    Examples:
      401 → UNAUTHORIZED (-401)
      403 → FORBIDDEN (-403)
      429 → rate limited
    """
    def __init__(self, message: str, http_status: int, details: Any = None):
        self.http_status = http_status
        self.details = details
        # Map HTTP status to JSON-RPC error code
        code = _http_to_jsonrpc_code(http_status)
        super().__init__(message, code=code)

    def to_jsonrpc_error(self) -> dict:
        error = super().to_jsonrpc_error()
        if self.details:
            error["data"] = self.details
        return error


def _http_to_jsonrpc_code(http_status: int) -> int:
    """Map HTTP status codes to JSON-RPC error codes."""
    mapping = {
        400: JSONRPCError.INVALID_PARAMS,
        401: JSONRPCError.UNAUTHORIZED,
        403: JSONRPCError.FORBIDDEN,
        404: JSONRPCError.METHOD_NOT_FOUND,
        429: JSONRPCError.INTERNAL_ERROR,
        500: JSONRPCError.INTERNAL_ERROR,
    }
    return mapping.get(http_status, JSONRPCError.INTERNAL_ERROR)


class JSONRPCError:
    """Standard + extended JSON-RPC error codes.

    Maps to Go: internal/server/mcp/jsonrpc/ error codes.
    Standard codes: -32700 to -32603
    Extended codes: -32001 to -32004, -401, -403
    """
    # Standard JSON-RPC 2.0 error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP extended error codes
    HEADER_MISMATCH = -32001
    MISSING_REQUIRED_CLIENT_CAPABILITY = -32003
    UNSUPPORTED_PROTOCOL_VERSION = -32004

    # Auth error codes
    UNAUTHORIZED = -401
    FORBIDDEN = -403


def exception_to_jsonrpc_error(exc: Exception) -> dict:
    """Convert any exception to a JSON-RPC error dict.

    Maps to Go: ProcessGeneralError / ProcessGcpError
    """
    if isinstance(exc, ToolboxError):
        return exc.to_jsonrpc_error()
    # Generic exception
    return {
        "code": JSONRPCError.INTERNAL_ERROR,
        "message": str(exc),
    }
