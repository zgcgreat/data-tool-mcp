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
        self.protocol = protocol

    async def run(self) -> None:
        """Run the STDIO loop: read lines from stdin, process, write to stdout."""
        reader = asyncio.StreamReader()
        protocol_reader = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol_reader, sys.stdin
        )

        while True:
            line = await reader.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                request = JSONRPCRequest.from_dict(data)
                response = await self.protocol.handle_request(request)

                # Only send response if request has an id (not a notification)
                if request.id is not None:
                    output = json.dumps(response.to_dict())
                    sys.stdout.write(output + "\n")
                    sys.stdout.flush()

            except json.JSONDecodeError:
                error_response = JSONRPCResponse(
                    error={"code": -32700, "message": "Parse error"},
                    id=None,
                )
                sys.stdout.write(json.dumps(error_response.to_dict()) + "\n")
                sys.stdout.flush()
            except Exception as exc:
                error_response = JSONRPCResponse(
                    error={"code": -32603, "message": str(exc)},
                    id=None,
                )
                sys.stdout.write(json.dumps(error_response.to_dict()) + "\n")
                sys.stdout.flush()
