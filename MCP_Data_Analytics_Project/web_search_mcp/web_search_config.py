"""
Web Search MCP configuration (Tavily).

Tavily exposes a remote MCP server over Streamable HTTP at
``https://mcp.tavily.com/mcp/`` (see https://docs.tavily.com/documentation/mcp).

It provides the following tools:

- ``tavily_search``   - search the web for current, relevant sources
- ``tavily_extract``  - pull clean content from one or more URLs
- ``tavily_crawl``    - read many pages across a site
- ``tavily_map``      - discover a site's structure
- ``tavily_research`` - run multi-source research and return a detailed answer

Authentication: Tavily's remote MCP accepts a Tavily API key in either of two
ways:

1. An ``Authorization: Bearer <api-key>`` header (used here when
   ``TAVILY_API_KEY`` is set), or
2. A ``?tavilyApiKey=<api-key>`` query parameter on the URL.

OAuth is also supported (browser flow) and keyless access is available for
Search and Extract.
"""

from __future__ import annotations

from config import settings


def get_web_search_server_config() -> dict:
    """Return the MCP server config dict for the Tavily web search server."""
    config: dict = {
        "url": settings.TAVILY_MCP_URL,
        "transport": "http",
    }

    if settings.TAVILY_API_KEY:
        config["headers"] = {
            "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
        }

    return config

