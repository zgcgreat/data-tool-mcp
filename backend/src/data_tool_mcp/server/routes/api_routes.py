"""Legacy HTTP API routes.

Maps to Go: internal/server/api.go

Provides:
  GET  /api/toolset           — list all toolsets
  GET  /api/toolset/{name}    — get specific toolset
  GET  /api/tool/{name}       — get tool manifest
  POST /api/tool/{name}/invoke — invoke a tool
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from data_tool_mcp.errors import ClientServerError

router = APIRouter(prefix="/api", tags=["api"])


def extract_access_token(request: Request) -> str:
    """Extract access token from Authorization header.

    Maps to Go: internal/server/api.go accessToken extraction
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return auth_header


@router.get("/toolset")
async def list_toolsets(request: Request) -> dict[str, Any]:
    """List all toolsets.

    Maps to Go: toolsetHandler (GET /api/toolset)
    """
    rm = request.app.state.resource_manager
    toolsets = rm.get_toolsets_map()
    result = []
    for name, toolset in toolsets.items():
        result.append(toolset.manifest() if hasattr(toolset, "manifest") else {"name": name})
    return {"toolsets": result}


@router.get("/toolset/{toolset_name}")
async def get_toolset(request: Request, toolset_name: str) -> dict[str, Any]:
    """Get a specific toolset.

    Maps to Go: toolsetHandler (GET /api/toolset/{toolsetName})
    """
    rm = request.app.state.resource_manager
    toolset = rm.get_toolset(toolset_name)
    if not toolset:
        raise HTTPException(status_code=404, detail=f"toolset not found: {toolset_name}")
    if hasattr(toolset, "manifest"):
        return toolset.manifest()
    return {"name": toolset_name}


@router.get("/tool/{tool_name}")
async def get_tool(request: Request, tool_name: str) -> dict[str, Any]:
    """Get a tool's manifest.

    Maps to Go: toolGetHandler (GET /api/tool/{toolName})
    """
    rm = request.app.state.resource_manager
    tool = await _get_tool_or_404(request, rm, tool_name)
    return _build_tool_manifest(tool)


@router.post("/tool/{tool_name}/invoke")
async def invoke_tool(request: Request, tool_name: str) -> dict[str, Any]:
    """Invoke a tool via the legacy HTTP API.

    Maps to Go: toolInvokeHandler (POST /api/tool/{toolName}/invoke)
    """
    rm = request.app.state.resource_manager
    tool = await _get_tool_or_404(request, rm, tool_name)

    # Extract access token for tools that require client authorization
    access_token = extract_access_token(request)
    # Check if tool requires client authorization
    # Maps to Go: tool.RequiresClientAuthorization(s.ResourceMgr)
    _check_tool_authorization(tool, rm, access_token)

    body = await request.json()
    params = body.get("params", {})
    return await _invoke_tool(tool, params, rm, access_token)


async def _get_tool_or_404(request: Request, rm, tool_name: str):
    """获取工具,不存在则抛 404。

    多实例一致性: rm 未命中时从 store 按需加载(复用 admin/_tools 的辅助函数)。
    """
    tool = rm.get_tool(tool_name)
    if tool:
        return tool
    # rm 未命中:尝试从 store 按需加载
    from data_tool_mcp.config.store import get_store

    store = get_store()
    if store and store.is_persistent:
        from data_tool_mcp.admin._tools import _get_tool_for_action

        tool = await _get_tool_for_action(rm, store, tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool not found: {tool_name}")
    return tool


def _build_tool_manifest(tool) -> dict[str, Any]:
    """构建工具 manifest 响应。"""
    manifest = tool.manifest()
    annotations = tool.get_annotations()
    return {
        "name": tool.name,
        "description": manifest.description,
        "source": tool.source_name,
        "annotations": _annotations_to_dict(annotations),
        "inputSchema": _build_input_schema_dict(manifest),
    }


def _annotations_to_dict(annotations) -> dict[str, Any]:
    """将 annotations 转为 dict,空时返回 {}。"""
    if not annotations:
        return {}
    return annotations.to_dict()


def _build_input_schema_dict(manifest) -> dict[str, Any]:
    """构建 inputSchema。"""
    return {
        "type": "object",
        "properties": _build_param_properties(manifest),
        "required": _build_required_params(manifest),
    }


def _build_param_properties(manifest) -> dict[str, Any]:
    """构建参数 properties 映射。"""
    return {p.name: {"type": p.type, "description": p.description} for p in manifest.parameters}


def _build_required_params(manifest) -> list[str]:
    """构建必填参数名列表。"""
    return [p.name for p in manifest.parameters if p.required]


def _check_tool_authorization(tool, rm, access_token: str) -> None:
    """检查工具是否需要 client authorization,需要但缺失时抛 401。"""
    if not tool.requires_client_authorization(rm):
        return
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="tool requires client authorization but access token is missing from the request header",
        )


async def _invoke_tool(tool, params, rm, access_token: str) -> dict[str, Any]:
    """调用工具并处理异常,返回 {"result": ...}。

    result 保持原始类型(dict/list/str/int 等),由 FastAPI 自动 JSON 序列化。
    避免 str(result) 把结构化数据变成 Python repr(单引号、非合法 JSON)。
    """
    try:
        result = await tool.invoke(params, source_provider=rm, access_token=access_token)
        return {"result": result}
    except ClientServerError as exc:
        # Maps to Go: error classification
        # AgentError → 200, ClientServerError → corresponding HTTP status
        raise HTTPException(status_code=exc.http_status, detail=exc.message)
    except Exception as exc:
        # Unknown errors → 500
        raise HTTPException(status_code=500, detail=str(exc))
