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
    tool = rm.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool not found: {tool_name}")

    manifest = tool.manifest()
    annotations = tool.get_annotations()
    result = {
        "name": tool.name,
        "description": manifest.description,
        "source": tool.source_name,
        "annotations": annotations.to_dict() if annotations else {},
        "inputSchema": {
            "type": "object",
            "properties": {
                p.name: {"type": p.type, "description": p.description}
                for p in manifest.parameters
            },
            "required": [p.name for p in manifest.parameters if p.required],
        },
    }
    return result


@router.post("/tool/{tool_name}/invoke")
async def invoke_tool(request: Request, tool_name: str) -> dict[str, Any]:
    """Invoke a tool via the legacy HTTP API.

    Maps to Go: toolInvokeHandler (POST /api/tool/{toolName}/invoke)
    """
    rm = request.app.state.resource_manager
    tool = rm.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool not found: {tool_name}")

    # Extract access token for tools that require client authorization
    access_token = extract_access_token(request)
    
    # Check if tool requires client authorization
    # Maps to Go: tool.RequiresClientAuthorization(s.ResourceMgr)
    if tool.requires_client_authorization(rm):
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="tool requires client authorization but access token is missing from the request header"
            )

    body = await request.json()
    params = body.get("params", {})

    try:
        result = await tool.invoke(
            params, 
            source_provider=rm,
            access_token=access_token
        )
        return {"result": str(result)}
    except ClientServerError as exc:
        # Maps to Go: error classification
        # AgentError → 200, ClientServerError → corresponding HTTP status
        raise HTTPException(status_code=exc.http_status, detail=exc.message)
    except Exception as exc:
        # Unknown errors → 500
        raise HTTPException(status_code=500, detail=str(exc))
