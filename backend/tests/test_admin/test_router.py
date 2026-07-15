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
    rm.get_sources_map.return_value = {}
    rm.get_tools_map.return_value = {}
    rm.get_toolsets_map.return_value = {}
    rm.get_prompts_map.return_value = {}
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
    resp = await client.get("/admin/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "sourceCount" in data
    assert "toolCount" in data


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/admin/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data


@pytest.mark.asyncio
async def test_sources_list_empty(client):
    resp = await client.get("/admin/sources")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_source_types(client):
    resp = await client.get("/admin/source-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "postgres" in data
    assert "fields" in data["postgres"]


@pytest.mark.asyncio
async def test_source_types_with_whitelist(app, client):
    """启用白名单后,/source-types 只返回白名单内的类型。"""
    app.state.config.enabled_source_types = ["postgres", "mysql"]
    resp = await client.get("/admin/source-types")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"postgres", "mysql"}


@pytest.mark.asyncio
async def test_create_source_blocked_by_whitelist(app, client):
    """启用白名单后,创建被禁用类型的数据源应返回 403。"""
    app.state.config.enabled_source_types = ["postgres"]
    resp = await client.post("/admin/sources", json={
        "name": "test-mysql",
        "type": "mysql",
        "systemId": "sys001",
        "host": "localhost",
        "port": 3306,
        "database": "test",
        "user": "root",
        "password": "secret",
    })
    assert resp.status_code == 403
    assert "未启用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_tools_list(client):
    resp = await client.get("/admin/tools")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_config(client):
    resp = await client.get("/admin/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "yaml" in data
    assert "prebuiltNames" in data


@pytest.mark.asyncio
async def test_get_source_404(client):
    resp = await client.get("/admin/sources/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_source_204(client):
    resp = await client.delete("/admin/sources/nonexistent")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_query_missing_params(client):
    resp = await client.post("/admin/query", json={})
    assert resp.status_code == 400
    data = resp.json()
    assert "detail" in data
