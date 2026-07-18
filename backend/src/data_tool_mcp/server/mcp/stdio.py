"""STDIO transport for MCP protocol.

Maps to Go: internal/server/mcp.go ServeStdio()
"""

from __future__ import annotations

import asyncio
import json
import sys

from data_tool_mcp.server.mcp.protocol import JSONRPCRequest, JSONRPCResponse, MCPProtocol


class STDIOTransport:
    """STDIO transport for MCP — reads from stdin, writes to stdout.

    Go: ServeStdio() — line-delimited JSON-RPC over stdin/stdout
    """

    def __init__(self, protocol: MCPProtocol):
        """初始化实例。"""
        self.protocol = protocol

    async def run(self) -> None:
        """Run the STDIO loop: read lines from stdin, process, write to stdout."""
        reader = await self._setup_reader()
        await self._loop(reader)

    async def _setup_reader(self) -> asyncio.StreamReader:
        """初始化 stdin reader。"""
        reader = asyncio.StreamReader()
        protocol_reader = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol_reader, sys.stdin)
        return reader

    async def _loop(self, reader: asyncio.StreamReader) -> None:
        """主循环:读取行、处理、写响应。"""
        while True:
            line = await reader.readline()
            if not line:
                break
            await self._handle_line(line)

    async def _handle_line(self, line: bytes) -> None:
        """处理单行输入,空行跳过。"""
        line = line.strip()
        if not line:
            return
        await self._process_line(line)

    async def _process_line(self, line: bytes) -> None:
        """解析并处理 JSON-RPC 行,将响应写入 stdout。"""
        try:
            await self._handle_jsonrpc(line)
        except json.JSONDecodeError:
            self._write_error_response(-32700, "Parse error")
        except Exception as exc:
            self._write_error_response(-32603, str(exc))

    async def _handle_jsonrpc(self, line: bytes) -> None:
        """解析 JSON、处理请求、写入响应。"""
        data = json.loads(line)
        request = JSONRPCRequest.from_dict(data)
        response = await self.protocol.handle_request(request)
        # Only send response if request has an id (not a notification)
        if request.id is not None:
            self._write_response(response.to_dict())

    def _write_response(self, response_dict: dict) -> None:
        """写入 JSON 响应到 stdout。"""
        sys.stdout.write(json.dumps(response_dict) + "\n")
        sys.stdout.flush()

    def _write_error_response(self, code: int, message: str) -> None:
        """写入错误响应到 stdout。"""
        error_response = JSONRPCResponse(
            error={"code": code, "message": message},
            id=None,
        )
        self._write_response(error_response.to_dict())
