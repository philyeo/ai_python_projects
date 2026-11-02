"""
MCP Aggregator (Streamable HTTP transport).

Connects to:

- the Pandas MCP server over STDIO (local subprocess)
- the RAG MCP server over STDIO (local subprocess)
- the Tavily Web Search MCP server over Streamable HTTP (remote)

and exposes their combined tools through one HTTP endpoint, for example
``http://127.0.0.1:8000/mcp``.

Tool names are namespaced by server name, so the agent sees:
``pandas_*``, ``rag_*`` and ``tavily_*``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable when run directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastmcp.server import create_proxy  # noqa: E402

from config import settings  # noqa: E402
from web_search_mcp.web_search_config import (  # noqa: E402
    get_web_search_server_config,
)

PANDAS_SERVER_PATH = PROJECT_ROOT / "pandas_mcp" / "pandas_server.py"
RAG_SERVER_PATH = PROJECT_ROOT / "rag_mcp" / "rag_server.py"


def build_aggregator_config() -> dict:
    """Build the multi-server MCP configuration for the aggregator."""
    return {
        "mcpServers": {
            "pandas": {
                "command": sys.executable,
                "args": [str(PANDAS_SERVER_PATH)],
                "transport": "stdio",
            },
            "rag": {
                "command": sys.executable,
                "args": [str(RAG_SERVER_PATH)],
                "transport": "stdio",
            },
            "tavily": get_web_search_server_config(),
        }
    }


aggregator = create_proxy(
    build_aggregator_config(),
    name="Data Analytics MCP Aggregator",
)


if __name__ == "__main__":
    settings.ensure_directories()
    aggregator.run(
        transport="http",
        host=settings.AGGREGATOR_HOST,
        port=settings.AGGREGATOR_PORT,
    )
