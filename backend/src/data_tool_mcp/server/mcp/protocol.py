"""MCP protocol base — JSON-RPC message handling and method routing.

Maps to Go:
  internal/server/mcp/jsonrpc/ — JSON-RPC types
  internal/server/mcp/v{version}/method.go — method handlers
"""

from __future__ import annotations

import time
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
        """从字典构造 JSONRPCRequest 实例。"""
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
        """将响应转换为 JSON-RPC 字典。"""
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
        """从字典构造 JSONRPCNotification 实例。"""
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
    "2025-06-18": MCPVersionConfig(
        version="2025-06-18", supports_sampling=True, supports_roots=True
    ),
    "2025-11-25": MCPVersionConfig(
        version="2025-11-25", supports_sampling=True, supports_roots=True
    ),
    "DRAFT-2026-v1": MCPVersionConfig(
        version="DRAFT-2026-v1", supports_sampling=True, supports_roots=True
    ),
}

DEFAULT_MCP_VERSION = "2025-06-18"


# ---------------------------------------------------------------------------
# MCP Protocol handler
# ---------------------------------------------------------------------------


class MCPProtocol:
    """MCP protocol handler — routes JSON-RPC methods to handlers.

    Maps to Go: 5 separate method.go files unified into one class.
    """

    def __init__(
        self,
        resource_manager: Any,
        version: str = DEFAULT_MCP_VERSION,
        toolset_name: str = "",
        access_token: str = "",
        system_id: str = "",
        environment: str = "",
        client_addr: str = "",
    ):
        """初始化实例。"""
        from data_tool_mcp.resources import ResourceManager

        self.rm: ResourceManager = resource_manager
        self.toolset_name = toolset_name
        self.access_token = access_token
        # 请求上下文（用于统计日志埋点）
        self.system_id = system_id
        self.environment = environment
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
        self._attach_trace_context(request.meta)

        handler, handler_name = self._resolve_handler(request.method)
        if handler is None:
            return self._notification_or_error(
                is_notification,
                self._method_not_found_error(request.method, handler_name),
                request.id,
            )

        result, error_dict = await self._safe_invoke_handler(handler, request.params)
        return self._build_response(result, error_dict, request.id, is_notification)

    def _attach_trace_context(self, meta: RequestMetaObject) -> None:
        """提取并传播 W3C Trace Context。"""
        if not meta.traceparent:
            return
        self._propagate_trace_context(meta.traceparent, meta.tracestate)

    def _propagate_trace_context(self, traceparent: str, tracestate: str) -> None:
        """使用 OpenTelemetry 传播 trace context。"""
        try:
            self._do_propagate_trace(traceparent, tracestate)
        except ImportError:
            # OpenTelemetry not available, skip propagation
            pass
        except Exception:
            # Propagation failed, continue without trace context
            pass

    def _do_propagate_trace(self, traceparent: str, tracestate: str) -> None:
        """实际执行 trace context 传播(可能抛 ImportError 或其他异常)。"""
        from opentelemetry import context as otel_context
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        carrier = {
            "traceparent": traceparent,
            "tracestate": tracestate,
        }
        ctx = TraceContextTextMapPropagator().extract(carrier=carrier)
        if ctx is not None:
            otel_context.attach(ctx)

    def _resolve_handler(self, method: str):
        """根据方法名解析 handler,返回 (handler, handler_name)。未找到时 handler 为 None。"""
        handler_name = self._method_map.get(method, "")
        if not handler_name:
            return None, ""
        return getattr(self, handler_name, None), handler_name

    def _method_not_found_error(self, method: str, handler_name: str) -> dict[str, Any]:
        """根据 handler 是否注册,构建对应的 method not found 错误。"""
        if handler_name:
            return {
                "code": JSONRPCError.METHOD_NOT_FOUND,
                "message": f"handler not implemented: {method}",
            }
        return {
            "code": JSONRPCError.METHOD_NOT_FOUND,
            "message": f"method not found: {method}",
        }

    def _notification_or_error(
        self,
        is_notification: bool,
        error_dict: dict[str, Any],
        request_id: RequestId,
    ) -> JSONRPCResponse | None:
        """通知请求返回 None,否则返回带 error 的响应。"""
        if is_notification:
            return None
        return JSONRPCResponse(error=error_dict, id=request_id)

    async def _safe_invoke_handler(self, handler, params: dict[str, Any]):
        """调用 handler,返回 (result, error_dict)。成功时 error_dict 为 None。"""
        try:
            result = await handler(params)
            return result, None
        except ToolboxError as exc:
            return None, exc.to_jsonrpc_error()
        except Exception as exc:
            return None, exception_to_jsonrpc_error(exc)

    def _build_response(
        self,
        result: Any,
        error_dict: dict[str, Any] | None,
        request_id: RequestId,
        is_notification: bool,
    ) -> JSONRPCResponse | None:
        """根据调用结果构建响应,通知请求返回 None。"""
        if is_notification:
            return None
        if error_dict is not None:
            return JSONRPCResponse(error=error_dict, id=request_id)
        return JSONRPCResponse(result=result, id=request_id)

    # -- Method handlers --

    async def handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP initialize request.

        Maps to Go: handleInitialize in each version's method.go.

        MCP spec negotiation: if the client requests a protocol version we
        support, echo it back; otherwise respond with our latest supported
        stable version.
        """
        from data_tool_mcp import __version__

        return {
            "protocolVersion": self._negotiate_version(params),
            "capabilities": self._build_capabilities(),
            "serverInfo": {
                "name": "mcp-toolbox",
                "version": __version__,
            },
        }

    def _negotiate_version(self, params: dict[str, Any]) -> str:
        """协商 MCP 协议版本,客户端版本不支持时回退到最新稳定版。"""
        client_version = params.get("protocolVersion", "")
        if client_version in MCP_VERSIONS:
            return client_version
        return DEFAULT_MCP_VERSION

    def _build_capabilities(self) -> dict[str, Any]:
        """构建 server capabilities,仅当存在 prompts 时才声明 prompts 能力。"""
        capabilities: dict[str, Any] = {"tools": {"listChanged": True}}
        if self._has_prompts():
            capabilities["prompts"] = {"listChanged": True}
        return capabilities

    def _has_prompts(self) -> bool:
        """判断是否注册了 prompts。"""
        return hasattr(self.rm, "get_prompts_map") and bool(self.rm.get_prompts_map())

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
        t0 = time.monotonic()
        success = True
        try:
            tools = self._get_tools_for_list()
            tool_list = [self._build_tool_entry(tool) for tool in tools.values()]
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

    def _get_tools_for_list(self) -> dict[str, Any]:
        """获取 tools/list 用的工具映射,按 toolset 过滤(若设置)。"""
        if not self.toolset_name:
            return self.rm.get_tools_map()
        return {t.name: t for t in self.rm.get_toolset_tools(self.toolset_name)}

    def _build_tool_entry(self, tool) -> dict[str, Any]:
        """构建单个工具的 manifest 条目。"""
        manifest = tool.manifest()
        tool_entry: dict[str, Any] = {
            "name": tool.name,
            "description": manifest.description,
            "inputSchema": self._build_input_schema(manifest),
        }
        self._attach_tool_annotations(tool, tool_entry)
        return tool_entry

    def _build_input_schema(self, manifest) -> dict[str, Any]:
        """构建工具的 inputSchema。"""
        return {
            "type": "object",
            "properties": self._build_param_properties(manifest),
            "required": self._build_required_params(manifest),
        }

    def _build_param_properties(self, manifest) -> dict[str, Any]:
        """构建参数 properties 映射。"""
        return {p.name: {"type": p.type, "description": p.description} for p in manifest.parameters}

    def _build_required_params(self, manifest) -> list[str]:
        """构建必填参数名列表。"""
        return [p.name for p in manifest.parameters if p.required]

    def _attach_tool_annotations(self, tool, tool_entry: dict[str, Any]) -> None:
        """如果有 annotations,附加到 tool_entry(MCP 2025-06-18+)。"""
        annotations = tool.get_annotations()
        if not annotations:
            return
        annot_dict = annotations.to_dict()
        if annot_dict:
            tool_entry["annotations"] = annot_dict

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
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        t0 = time.monotonic()
        success = True
        error_msg = ""

        # 安全校验: toolset 隔离 — 只允许调用当前 toolset 内的工具
        tool, source_name, early_return = await self._prepare_tool_call(tool_name, t0)
        if early_return is not None:
            return early_return

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
        except Exception as exc:
            success = False
            error_msg, response = self._handle_tool_invoke_error(exc)
            return response
        finally:
            await self._log_request(
                method="tools/call",
                tool_name=tool_name,
                source_name=source_name,
                success=success,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error_msg=error_msg,
            )

    async def _prepare_tool_call(self, tool_name: str, t0: float):
        """准备工具调用:toolset 校验 + 工具解析 + auth 校验。
        返回 (tool, source_name, early_return)。
        early_return 非 None 时应直接返回该响应。
        """
        blocked = await self._check_toolset_allowed(tool_name, t0)
        if blocked is not None:
            return None, "", blocked

        tool, source_name = await self._resolve_tool_for_call(tool_name, t0)
        if isinstance(tool, dict):
            return None, source_name, tool
        return tool, source_name, None

    async def _check_toolset_allowed(self, tool_name: str, t0: float):
        """检查 toolset 隔离。被拦截时返回错误响应 dict,否则返回 None。"""
        if not self.toolset_name:
            return None
        if tool_name in self._get_allowed_tool_names():
            return None
        await self._log_request(
            method="tools/call",
            tool_name=tool_name,
            success=False,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error_msg=f"tool not found: {tool_name}",
        )
        return self._tool_not_found_response(tool_name)

    def _get_allowed_tool_names(self) -> set[str]:
        """获取当前 toolset 允许调用的工具名集合。"""
        return {t.name for t in self.rm.get_toolset_tools(self.toolset_name)}

    async def _resolve_tool_for_call(self, tool_name: str, t0: float):
        """解析工具并执行 auth 校验。
        成功返回 (tool, source_name);工具不存在返回 (error_dict, None);
        auth 失败抛出 ClientServerError。
        """
        tool = self.rm.get_tool(tool_name)
        if not tool:
            await self._log_request(
                method="tools/call",
                tool_name=tool_name,
                success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error_msg=f"tool not found: {tool_name}",
            )
            return self._tool_not_found_response(tool_name), None

        # 反查数据源名称（用于统计维度）
        source_name = self._get_tool_source_name(tool)

        # Check if this tool requires client-provided authorization
        # Maps to Go: tool.RequiresClientAuthorization(resourceMgr)
        if self._requires_auth_failure(tool):
            await self._log_request(
                method="tools/call",
                tool_name=tool_name,
                source_name=source_name,
                success=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error_msg="missing access token",
            )
            raise ClientServerError(
                "missing access token in the 'Authorization' header",
                http_status=401,
            )

        return tool, source_name

    def _get_tool_source_name(self, tool) -> str:
        """获取工具的 source_name(用于统计维度)。"""
        return getattr(tool, "source_name", "") or ""

    def _requires_auth_failure(self, tool) -> bool:
        """判断工具是否需要 client authorization 但 access_token 缺失。"""
        return tool.requires_client_authorization(source_provider=self.rm) and not self.access_token

    def _tool_not_found_response(self, tool_name: str) -> dict[str, Any]:
        """构建统一的 'tool not found' 错误响应。"""
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"tool not found: {tool_name}"}],
        }

    def _handle_tool_invoke_error(self, exc: Exception):
        """处理工具调用异常,返回 (error_msg, response_dict)。"""
        if isinstance(exc, ToolboxError):
            return exc.message, self._tool_error_response(exc.message)
        return str(exc), self._tool_error_response(str(exc))

    def _tool_error_response(self, error_msg: str) -> dict[str, Any]:
        """构建工具调用错误响应 dict。"""
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"tool error: {error_msg}"}],
        }

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

        当 system_id / environment 为空时（客户端连 /{sourceName}/sse 而非
        /{systemId}/{environment}/{sourceName}/sse），从 source_name 或 toolset_name
        反查 system_id 和 environment，确保统计维度完整。
        """
        try:
            from data_tool_mcp.config.store import get_store

            store = get_store()
            if not self._is_store_loggable(store):
                return

            resolved_system, resolved_env, resolved_source = self._resolve_log_context(source_name)

            await store.log_mcp_request(
                system_id=resolved_system,
                environment=resolved_env,
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

    def _is_store_loggable(self, store) -> bool:
        """判断 store 是否可用于日志写入。"""
        return store is not None and store.is_persistent

    def _resolve_log_context(self, source_name: str):
        """反查 system_id / environment / source_name,确保统计维度完整。
        返回 (system_id, environment, source_name) 三元组。
        """
        if self.system_id and self.environment:
            return self.system_id, self.environment, source_name
        return self._resolve_missing_context(source_name)

    def _resolve_missing_context(self, source_name: str):
        """当 system_id 或 environment 缺失时,从 source_name 或 toolset_name 反查。"""
        if source_name:
            return self._resolve_from_source(source_name)
        if self.toolset_name:
            return self._resolve_from_toolset(source_name)
        return self.system_id, self.environment, source_name

    def _resolve_from_source(self, source_name: str):
        """从 source_name 反查 system_id 和 environment。"""
        config = self.rm.get_source_config(source_name)
        if not config:
            return self.system_id, self.environment, source_name
        resolved_system = self._fill_missing(self.system_id, config, "systemId")
        resolved_env = self._fill_missing(self.environment, config, "environment")
        return resolved_system, resolved_env, source_name

    def _resolve_from_toolset(self, source_name: str):
        """从 toolset_name 反查统计维度(tools/list 没有 source_name)。"""
        config = self.rm.get_source_config(self.toolset_name)
        if not config:
            # toolset_name 不是 sourceName,可能是 systemId 或 {system_id}-{environment}
            return self.toolset_name, self.environment, source_name
        resolved_system = self._fill_missing(self.system_id, config, "systemId")
        resolved_env = self._fill_missing(self.environment, config, "environment")
        return resolved_system, resolved_env, self.toolset_name

    def _fill_missing(self, current: str, config: dict[str, Any], key: str) -> str:
        """如果 current 为空,从 config[key] 填充并 strip。"""
        if current:
            return current
        return str(config.get(key, "") or "").strip()

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
        return {"prompts": [self._build_prompt_entry(n, p) for n, p in prompts.items()]}

    def _build_prompt_entry(self, name: str, prompt) -> dict[str, Any]:
        """构建单个 prompt 的 manifest 条目。"""
        manifest = prompt.manifest()
        return {
            "name": name,
            "description": manifest.description,
            "arguments": [
                {"name": a.name, "description": a.description, "required": a.required}
                for a in manifest.arguments
            ],
        }

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
