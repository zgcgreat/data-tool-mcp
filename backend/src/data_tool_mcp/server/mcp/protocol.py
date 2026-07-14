"""MCP protocol base — JSON-RPC message handling and method routing.

Maps to Go:
  internal/server/mcp/jsonrpc/ — JSON-RPC types
  internal/server/mcp/v{version}/method.go — method handlers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.errors import (
    AgentError,
    ClientServerError,
    JSONRPCError,
    ToolboxError,
    exception_to_jsonrpc_error,
)


# ---------------------------------------------------------------------------
# JSON-RPC message types
# ---------------------------------------------------------------------------

@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request.

    Maps to Go: jsonrpc.JSONRPCRequest

    A request is a notification when the ``id`` field is **absent** from the
    JSON.  An explicit ``"id": null`` is a valid request id (not a
    notification) per JSON-RPC 2.0 spec.  We track this with ``_is_notification``.
    """
    jsonrpc: str = "2.0"
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    id: str | int | None = None
    _is_notification: bool = False
    # W3C Trace Context — Maps to Go: RequestMetaObject
    meta: RequestMetaObject = field(default_factory=lambda: RequestMetaObject())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JSONRPCRequest:
        meta_data = data.get("params", {}).get("_meta", {})
        # A notification is a request WITHOUT an "id" field (key absent).
        # "id": null is a valid id per JSON-RPC 2.0 and is NOT a notification.
        is_notification = "id" not in data
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            method=data.get("method", ""),
            params=data.get("params", {}),
            id=data.get("id"),
            _is_notification=is_notification,
            meta=RequestMetaObject(
                traceparent=meta_data.get("traceparent", ""),
                tracestate=meta_data.get("tracestate", ""),
                progress_token=meta_data.get("progressToken"),
            ),
        )


@dataclass
class RequestMetaObject:
    """W3C Trace Context and progress token metadata.

    Maps to Go: jsonrpc.RequestMetaObject
    """
    traceparent: str = ""
    tracestate: str = ""
    progress_token: Any = None  # ProgressToken — str | int | None


# Type aliases matching Go
ProgressToken = str | int | None
RequestId = str | int | None


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    result: Any = None
    error: dict[str, Any] | None = None
    id: str | int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


@dataclass
class JSONRPCNotification:
    """JSON-RPC 2.0 notification (no id, no response expected)."""
    jsonrpc: str = "2.0"
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JSONRPCNotification:
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            method=data.get("method", ""),
            params=data.get("params", {}),
        )


# ---------------------------------------------------------------------------
# MCP protocol version configuration
# ---------------------------------------------------------------------------

@dataclass
class MCPVersionConfig:
    """Configuration differences between MCP protocol versions.

    Maps to Go: separate method.go files per version.
    In Python, we unify into one base class with version-specific config.
    """
    version: str  # e.g., "2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"
    supports_sampling: bool = False
    supports_roots: bool = False
    supports_progress: bool = True
    supports_cancel: bool = True


# Protocol versions supported
MCP_VERSIONS = {
    "2024-11-05": MCPVersionConfig(version="2024-11-05"),
    "2025-03-26": MCPVersionConfig(version="2025-03-26", supports_sampling=True),
    "2025-06-18": MCPVersionConfig(version="2025-06-18", supports_sampling=True, supports_roots=True),
    "2025-11-25": MCPVersionConfig(version="2025-11-25", supports_sampling=True, supports_roots=True),
    "DRAFT-2026-v1": MCPVersionConfig(version="DRAFT-2026-v1", supports_sampling=True, supports_roots=True),
}

DEFAULT_MCP_VERSION = "2025-06-18"


# ---------------------------------------------------------------------------
# MCP Protocol handler
# ---------------------------------------------------------------------------

class MCPProtocol:
    """MCP protocol handler — routes JSON-RPC methods to handlers.

    Maps to Go: 5 separate method.go files unified into one class.
    """

    def __init__(self, resource_manager: Any, version: str = DEFAULT_MCP_VERSION,
                 toolset_name: str = "", access_token: str = "",
                 system_id: str = "", client_addr: str = ""):
        from data_tool_mcp.resources import ResourceManager
        self.rm: ResourceManager = resource_manager
        self.toolset_name = toolset_name
        self.access_token = access_token
        # 请求上下文（用于统计日志埋点）
        self.system_id = system_id
        self.client_addr = client_addr
        self.version_config = MCP_VERSIONS.get(version)
        if not self.version_config:
            # Graceful degradation: fall back to latest stable version
            # instead of raising ValueError.  This matches Go's behavior
            # where unsupported versions trigger a JSON-RPC error response
            # with code -32603 (UNSUPPORTED_PROTOCOL_VERSION), not a crash.
            self.version_config = MCP_VERSIONS[DEFAULT_MCP_VERSION]
            self._version_fallback = True
        else:
            self._version_fallback = False

        # Method routing table — maps Go's per-version method switch
        self._method_map: dict[str, str] = {
            "initialize": "handle_initialize",
            "initialized": "handle_initialized",
            "ping": "handle_ping",
            "tools/list": "handle_tools_list",
            "tools/call": "handle_tools_call",
            "completion/complete": "handle_completion",
            "prompts/list": "handle_prompts_list",
            "prompts/get": "handle_prompts_get",
            "sampling/createMessage": "handle_sampling",
            "roots/list": "handle_roots",
            "logging/setLevel": "handle_logging_set_level",
        }
        # DRAFT-only methods
        if self.version_config.version == "DRAFT-2026-v1":
            self._method_map["server/discover"] = "handle_server_discover"

    async def handle_request(self, request: JSONRPCRequest) -> JSONRPCResponse | None:
        """Route a JSON-RPC request to the appropriate handler.

        Maps to Go: processMcpMessage — checks if message is a notification
        (id == nil) and returns no response.
        """
        # 记录今日 MCP 协议请求计数(Dashboard 指标)
        from data_tool_mcp.server.stats import get_request_counter
        get_request_counter().increment()

        # Check if this is a notification (no id field present in original JSON)
        # Maps to Go: if baseMessage.Id == nil { ... return "", nil, err }
        # Note: "id": null is a valid request id per JSON-RPC 2.0, not a notification.
        is_notification = request._is_notification

        # Extract and propagate trace context from _meta
        # Maps to Go: extractMeta + otel propagation
        ctx = None
        if request.meta.traceparent:
            try:
                from opentelemetry import context as otel_context
                from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
                carrier = {
                    "traceparent": request.meta.traceparent,
                    "tracestate": request.meta.tracestate,
                }
                ctx = TraceContextTextMapPropagator().extract(carrier=carrier)
                if ctx is not None:
                    otel_context.attach(ctx)
            except ImportError:
                # OpenTelemetry not available, skip propagation
                pass
            except Exception:
                # Propagation failed, continue without trace context
                pass

        handler_name = self._method_map.get(request.method)
        if not handler_name:
            if is_notification:
                # Notifications don't get error responses
                return None
            return JSONRPCResponse(
                error={
                    "code": JSONRPCError.METHOD_NOT_FOUND,
                    "message": f"method not found: {request.method}",
                },
                id=request.id,
            )

        handler = getattr(self, handler_name, None)
        if not handler:
            if is_notification:
                return None
            return JSONRPCResponse(
                error={
                    "code": JSONRPCError.METHOD_NOT_FOUND,
                    "message": f"handler not implemented: {request.method}",
                },
                id=request.id,
            )

        try:
            result = await handler(request.params)
            if is_notification:
                # Notifications don't get responses
                return None
            return JSONRPCResponse(result=result, id=request.id)
        except ToolboxError as exc:
            if is_notification:
                return None
            return JSONRPCResponse(
                error=exc.to_jsonrpc_error(),
                id=request.id,
            )
        except Exception as exc:
            if is_notification:
                return None
            return JSONRPCResponse(
                error=exception_to_jsonrpc_error(exc),
                id=request.id,
            )

    # -- Method handlers --

    async def handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP initialize request.

        Maps to Go: handleInitialize in each version's method.go.

        MCP spec negotiation: if the client requests a protocol version we
        support, echo it back; otherwise respond with our latest supported
        stable version.
        """
        # Negotiate protocol version
        # Maps to Go: version negotiation in handleInitialize
        client_version = params.get("protocolVersion", "")
        if client_version and client_version in MCP_VERSIONS:
            negotiated_version = client_version
        else:
            negotiated_version = DEFAULT_MCP_VERSION

        capabilities: dict[str, Any] = {
            "tools": {"listChanged": True},
        }
        # Only advertise prompts capability if prompts exist
        if hasattr(self.rm, "get_prompts_map") and self.rm.get_prompts_map():
            capabilities["prompts"] = {"listChanged": True}

        from data_tool_mcp import __version__
        return {
            "protocolVersion": negotiated_version,
            "capabilities": capabilities,
            "serverInfo": {
                "name": "mcp-toolbox",
                "version": __version__,
            },
        }

    async def handle_initialized(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP initialized notification — no response needed."""
        return {}

    async def handle_ping(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP ping."""
        return {}

    async def handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP tools/list — return tool manifests.

        If toolset_name is set, only return tools in that toolset.
        Maps to Go: handleToolsList (filters by toolset).
        """
        import time
        t0 = time.monotonic()
        success = True
        try:
            if self.toolset_name:
                tools = {
                    t.name: t for t in self.rm.get_toolset_tools(self.toolset_name)
                }
            else:
                tools = self.rm.get_tools_map()

            tool_list = []
            for tool_name, tool in tools.items():
                manifest = tool.manifest()
                tool_entry: dict[str, Any] = {
                    "name": tool.name,
                    "description": manifest.description,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            p.name: {"type": p.type, "description": p.description}
                            for p in manifest.parameters
                        },
                        "required": [p.name for p in manifest.parameters if p.required],
                    },
                }
                # Include annotations if available (MCP 2025-06-18+)
                annotations = tool.get_annotations()
                if annotations:
                    annot_dict = annotations.to_dict()
                    if annot_dict:
                        tool_entry["annotations"] = annot_dict
                tool_list.append(tool_entry)
            return {"tools": tool_list}
        except Exception:
            success = False
            raise
        finally:
            await self._log_request(
                method="tools/list",
                success=success,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

    async def handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP tools/call — execute a tool.

        Maps to Go: handleToolsCall in each version's method.go.
        Extracts access_token from the Authorization header (set by
        mcp_routes) and passes it to tool.invoke(), matching Go's
        AccessToken extraction and RequiresClientAuthorization check.

        安全校验: 当连接绑定了 toolset(系统编号或数据源)时,
        必须确认请求调用的工具属于该 toolset,防止跨系统/跨数据源调用。
        未找到时统一返回 "tool not found",避免泄露工具存在性信息。
        """
        import time
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        t0 = time.monotonic()
        success = True
        error_msg = ""

        # 安全校验: toolset 隔离 — 只允许调用当前 toolset 内的工具
        if self.toolset_name:
            toolset_tools = self.rm.get_toolset_tools(self.toolset_name)
            allowed_names = {t.name for t in toolset_tools}
            if tool_name not in allowed_names:
                await self._log_request(
                    method="tools/call", tool_name=tool_name, success=False,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error_msg=f"tool not found: {tool_name}",
                )
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"tool not found: {tool_name}"}],
                }

        tool = self.rm.get_tool(tool_name)
        if not tool:
            await self._log_request(
                method="tools/call", tool_name=tool_name, success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error_msg=f"tool not found: {tool_name}",
            )
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"tool not found: {tool_name}"}],
            }

        # 反查数据源名称（用于统计维度）
        source_name = getattr(tool, "source_name", "") or ""

        # Check if this tool requires client-provided authorization
        # Maps to Go: tool.RequiresClientAuthorization(resourceMgr)
        if tool.requires_client_authorization(source_provider=self.rm) and not self.access_token:
            await self._log_request(
                method="tools/call", tool_name=tool_name, source_name=source_name,
                success=False, latency_ms=int((time.monotonic() - t0) * 1000),
                error_msg="missing access token",
            )
            raise ClientServerError(
                "missing access token in the 'Authorization' header",
                http_status=401,
            )

        try:
            # ResourceManager implements SourceProvider protocol
            # Maps to Go: tool.Invoke(ctx, resourceMgr, params, accessToken)
            result = await tool.invoke(
                arguments,
                source_provider=self.rm,
                access_token=self.access_token,
            )
            return {
                "content": [{"type": "text", "text": str(result)}],
            }
        except ToolboxError as exc:
            success = False
            error_msg = exc.message
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"tool error: {exc.message}"}],
            }
        except Exception as exc:
            success = False
            error_msg = str(exc)
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"tool error: {exc}"}],
            }
        finally:
            await self._log_request(
                method="tools/call",
                tool_name=tool_name,
                source_name=source_name,
                success=success,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error_msg=error_msg,
            )

    async def _log_request(
        self,
        *,
        method: str,
        tool_name: str = "",
        source_name: str = "",
        success: bool = True,
        latency_ms: int = 0,
        error_msg: str = "",
    ) -> None:
        """异步写入 MCP 请求日志（失败静默，不影响主流程）。

        当 system_id 为空时（客户端连 /{sourceName}/sse 而非 /{systemId}/{sourceName}/sse），
        从 source_name 或 toolset_name 反查 system_id，确保统计维度完整。
        """
        try:
            from data_tool_mcp.config.store import get_store
            store = get_store()
            if store is None or not store.is_persistent:
                return

            resolved_system = self.system_id
            resolved_source = source_name

            # system_id 为空时尝试反查
            if not resolved_system:
                if resolved_source:
                    # 从 source_name 反查 system_id
                    config = self.rm.get_source_config(resolved_source)
                    if config:
                        resolved_system = str(config.get("systemId", ""))
                elif self.toolset_name:
                    # tools/list 没有 source_name: 尝试把 toolset_name 当 sourceName 查
                    config = self.rm.get_source_config(self.toolset_name)
                    if config:
                        resolved_source = self.toolset_name
                        resolved_system = str(config.get("systemId", ""))
                    else:
                        # toolset_name 不是 sourceName,可能是 systemId
                        resolved_system = self.toolset_name

            await store.log_mcp_request(
                system_id=resolved_system,
                source_name=resolved_source,
                tool_name=tool_name,
                method=method,
                success=success,
                latency_ms=latency_ms,
                client_addr=self.client_addr,
                error_msg=error_msg,
            )
        except Exception:
            # 日志写入失败不影响主流程
            pass

    async def handle_completion(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP completion/complete."""
        return {"completion": {"values": [], "total": 0, "hasMore": False}}

    async def handle_prompts_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP prompts/list — return prompt manifests.

        Maps to Go: handlePromptsList
        """
        if not hasattr(self.rm, "get_prompts_map"):
            return {"prompts": []}

        prompts = self.rm.get_prompts_map()
        prompt_list = []
        for prompt_name, prompt in prompts.items():
            manifest = prompt.manifest()
            prompt_list.append({
                "name": prompt_name,
                "description": manifest.description,
                "arguments": [
                    {"name": a.name, "description": a.description, "required": a.required}
                    for a in manifest.arguments
                ],
            })
        return {"prompts": prompt_list}

    async def handle_prompts_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP prompts/get — return a specific prompt.

        Maps to Go: handlePromptsGet
        """
        if not hasattr(self.rm, "get_prompt"):
            raise AgentError("prompts not supported")

        prompt_name = params.get("name", "")
        arguments = params.get("arguments", {})

        prompt = self.rm.get_prompt(prompt_name)
        if not prompt:
            raise AgentError(f"prompt not found: {prompt_name}")

        # Substitute parameters into prompt messages
        result = prompt.substitute_params(arguments)
        return result

    async def handle_sampling(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP sampling/createMessage — request LLM sampling.

        Maps to Go: v20250326+ handleSampling
        This is a client-to-server request; the server requests the client
        to generate an LLM response. For now, return not supported.
        """
        raise AgentError("sampling not supported by this server")

    async def handle_roots(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP roots/list — list server roots.

        Maps to Go: v20250618+ handleRoots
        """
        return {"roots": []}

    async def handle_logging_set_level(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP logging/setLevel — set log level.

        Maps to Go: logging/setLevel method
        """
        import logging
        level = params.get("level", "info").upper()
        logging.getLogger("data_tool_mcp").setLevel(getattr(logging, level, logging.INFO))
        return {}

    async def handle_server_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP server/discover — DRAFT protocol discovery.

        Maps to Go: vdraft handleServerDiscover
        Returns available tools and prompts metadata.
        """
        tools_list_result = await self.handle_tools_list(params)
        prompts_list_result = await self.handle_prompts_list(params)
        return {
            "tools": tools_list_result.get("tools", []),
            "prompts": prompts_list_result.get("prompts", []),
        }
