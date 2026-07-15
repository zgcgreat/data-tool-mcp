#!/usr/bin/env python
"""Quick launcher — starts the MCP Toolbox server with SQLite prebuilt config."""
import os
import sys
from pathlib import Path

# Set default SQLite database path if not already set
if "SQLITE_DATABASE" not in os.environ:
    os.environ["SQLITE_DATABASE"] = str(Path(__file__).parent.parent / "test.db")

# Load .env file if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# Import and run
from data_tool_mcp.cli.main import main

if __name__ == "__main__":
    # sys.argv = ["toolbox", "serve", "--prebuilt", "sqlite", "--port", "15000"]
    sys.argv = ["toolbox", "serve", "--port", "15000"]
    main()
