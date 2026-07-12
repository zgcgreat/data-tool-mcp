"""MCP protocol version configuration.

Maps to Go: 5 separate v{version}/method.go files → unified version config.
"""

from data_tool_mcp.server.mcp.protocol import MCP_VERSIONS, DEFAULT_MCP_VERSION

__all__ = ["MCP_VERSIONS", "DEFAULT_MCP_VERSION"]
