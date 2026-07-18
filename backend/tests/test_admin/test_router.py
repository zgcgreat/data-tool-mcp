from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock

from data_tool_mcp.admin.router import router


@pytest.fixture
def app():
    app = FastAPI()
    rm = MagicMock()
    # 同步方法: 返回空集合/False/None 以模拟"无数据"状态
    rm.get_all_source_configs.return_value = {}
    rm.get_source_config.return_value = None
    rm.has_source.return_value = False
    rm.get_tools_map.return_value = {}
    rm.get_toolsets_map.return_value = {}
    rm.get_prompts_map.return_value = {}
    rm.get_toolset.return_value = None
    # async 方法: 使用 AsyncMock(方案 C 改造后 RM 接口为 async)
    rm.get_source = AsyncMock(return_value=None)
    rm.release_source = AsyncMock(return_value=None)
    rm.add_source = AsyncMock(return_value=None)
    rm.remove_source = AsyncMock(return_value=None)
    rm.invalidate_source = AsyncMock(return_value=None)
    app.state.resource_manager = rm
    app.state.config = MagicMock()
    app.state.config.version = "0.1.0"
    # 默认全部启用: enabled_source_types 为空列表
    app.state.config.enabled_source_types = []
    app.include_router(router)
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_dashboard(client):
    resp = await client.get("/mcp-api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "sourceCount" in data
    assert "toolCount" in data


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/mcp-api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data


@pytest.mark.asyncio
async def test_sources_list_empty(client):
    resp = await client.get("/mcp-api/sources")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_source_types(client):
    resp = await client.get("/mcp-api/source-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "postgres" in data
    assert "fields" in data["postgres"]


@pytest.mark.asyncio
async def test_source_types_with_whitelist(app, client):
    """启用白名单后,/source-types 只返回白名单内的类型。"""
    app.state.config.enabled_source_types = ["postgres", "mysql"]
    resp = await client.get("/mcp-api/source-types")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"postgres", "mysql"}


@pytest.mark.asyncio
async def test_create_source_blocked_by_whitelist(app, client):
    """启用白名单后,创建被禁用类型的数据源应返回 403。"""
    app.state.config.enabled_source_types = ["postgres"]
    resp = await client.post(
        "/mcp-api/sources",
        json={
            "name": "test-mysql",
            "type": "mysql",
            "systemId": "sys001",
            "environment": "dev",
            "host": "localhost",
            "port": 3306,
            "database": "test",
            "user": "root",
            "password": "secret",
        },
    )
    assert resp.status_code == 403
    assert "未启用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_tools_list(client):
    resp = await client.get("/mcp-api/tools")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_config(client):
    resp = await client.get("/mcp-api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "yaml" in data
    assert "prebuiltNames" in data


@pytest.mark.asyncio
async def test_get_source_404(client):
    resp = await client.get("/mcp-api/sources/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_source_204(client):
    resp = await client.delete("/mcp-api/sources/nonexistent")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_query_missing_params(client):
    resp = await client.post("/mcp-api/query", json={})
    assert resp.status_code == 400
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_mcp_test_system_only(app, client):
    """system-only 访问(仅 systemId 无 environment/toolset)应返回该系统工具列表。

    验证 /{systemId}/sse 路径对应的 mcp-test 调用不再返回 404。
    ResourceManager 创建 {systemId} toolset 后,mcp-test 能正确解析并返回工具。
    """
    from data_tool_mcp.resources import Toolset

    # 配置 mock:rm.get_toolset("sys001") 返回非 None,模拟系统级 toolset 已创建
    rm = app.state.resource_manager
    rm.get_toolset.return_value = Toolset(name="sys001", tools=["tool1", "tool2"])
    # MCPProtocol.handle_tools_list 内部调用 get_toolset_tools,返回工具列表
    # 用 MagicMock 模拟工具对象(有 name 和 manifest 方法)
    mock_tool = MagicMock()
    mock_tool.name = "tool1"
    mock_tool.manifest.return_value = MagicMock(description="test tool")
    rm.get_toolset_tools.return_value = [mock_tool]

    resp = await client.post(
        "/mcp-api/mcp-test",
        json={"toolset": "", "systemId": "sys001", "environment": ""},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] == 1
    assert data["tools"][0]["name"] == "tool1"


@pytest.mark.asyncio
async def test_mcp_test_system_only_not_found(app, client):
    """system-only 访问不存在的 systemId 应返回 404(而非误返回全部工具)。"""
    rm = app.state.resource_manager
    # get_toolset 默认返回 None(fixture 配置),无需额外设置

    resp = await client.post(
        "/mcp-api/mcp-test",
        json={"toolset": "", "systemId": "nonexistent", "environment": ""},
    )
    assert resp.status_code == 404
    assert "toolset 'nonexistent' not found" in resp.json()["detail"]
