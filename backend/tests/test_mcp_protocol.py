"""Tests for MCP protocol handling."""

import pytest

from data_tool_mcp.server.mcp.protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPProtocol,
    MCP_VERSIONS,
)
from data_tool_mcp.resources import ResourceManager


@pytest.fixture
def resource_manager():
    return ResourceManager()


@pytest.fixture
def protocol(resource_manager):
    return MCPProtocol(resource_manager, version="2025-06-18")


class TestJSONRPCMessages:
    def test_request_from_dict(self):
        data = {"jsonrpc": "2.0", "method": "ping", "id": 1, "params": {}}
        req = JSONRPCRequest.from_dict(data)
        assert req.method == "ping"
        assert req.id == 1

    def test_response_to_dict(self):
        resp = JSONRPCResponse(result={"status": "ok"}, id=1)
        d = resp.to_dict()
        assert d["result"] == {"status": "ok"}
        assert d["id"] == 1
        assert "error" not in d

    def test_error_response_to_dict(self):
        resp = JSONRPCResponse(error={"code": -32601, "message": "not found"}, id=2)
        d = resp.to_dict()
        assert "error" in d
        assert "result" not in d


class TestMCPProtocol:
    @pytest.mark.asyncio
    async def test_initialize(self, protocol):
        req = JSONRPCRequest(method="initialize", id=1, params={})
        resp = await protocol.handle_request(req)
        assert resp.result is not None
        assert resp.result["protocolVersion"] == "2025-06-18"
        assert "tools" in resp.result["capabilities"]

    @pytest.mark.asyncio
    async def test_ping(self, protocol):
        req = JSONRPCRequest(method="ping", id=2, params={})
        resp = await protocol.handle_request(req)
        assert resp.result == {}

    @pytest.mark.asyncio
    async def test_tools_list_empty(self, protocol):
        req = JSONRPCRequest(method="tools/list", id=3, params={})
        resp = await protocol.handle_request(req)
        assert resp.result["tools"] == []

    @pytest.mark.asyncio
    async def test_unknown_method(self, protocol):
        req = JSONRPCRequest(method="nonexistent", id=4, params={})
        resp = await protocol.handle_request(req)
        assert resp.error is not None
        assert resp.error["code"] == -32601

    def test_version_config(self):
        for version_str, config in MCP_VERSIONS.items():
            assert config.version == version_str
