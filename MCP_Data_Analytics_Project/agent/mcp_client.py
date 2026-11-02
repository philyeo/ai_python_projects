"""
MCP client helpers: connect the LangChain agent to the MCP aggregator.

Uses LangChain's ``MCPAdapter`` to open a connection to the aggregator's
Streamable HTTP endpoint and list the combined MCP tools.
"""

from __future__ import annotations

import warnings

# ``langchain.mcp`` is still marked beta; silence the advisory warning so it
# does not clutter the application logs.
warnings.filterwarnings("ignore", message=".*langchain\\.mcp.*")

from langchain.mcp import MCPAdapter  # noqa: E402


async def connect(aggregator_url: str):
    """Open a connection to the aggregator and return ``(adapter, tools)``.

    The caller is responsible for closing the adapter via
    ``await adapter.__aexit__(None, None, None)``.
    """
    adapter = MCPAdapter(aggregator_url)
    await adapter.__aenter__()
    tools = await adapter.list_tools()
    return adapter, tools

