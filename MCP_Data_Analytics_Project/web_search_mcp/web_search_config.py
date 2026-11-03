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

Authentication
--------------

The default approach is **keyless access** (no account or API key required).
See https://docs.tavily.com/documentation/keyless.

- Keyless (default): send the ``X-Tavily-Access-Mode: keyless`` header. Only
  ``tavily_search`` and ``tavily_extract`` can be called, and requests are
  rate-limited.

- API key (optional upgrade): when ``TAVILY_API_KEY`` is set, an
  ``Authorization: Bearer <api-key>`` header is used instead. This unlocks all
  five tools and higher rate limits.
"""

from __future__ import annotations

from config import settings


def get_web_search_server_config() -> dict:
    """Return the MCP server config dict for the Tavily web search server.

    Keyless access is the default: when ``TAVILY_API_KEY`` is not set, the
    ``X-Tavily-Access-Mode: keyless`` header is sent so the remote server does
    not prompt for a sign-in. If an API key is configured, an
    ``Authorization: Bearer <api-key>`` header is used instead.
    """
    config: dict = {
        "url": settings.TAVILY_MCP_URL,
        "transport": "http",
    }

    if settings.TAVILY_API_KEY:
        config["headers"] = {
            "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
        }
    else:
        config["headers"] = {
            "X-Tavily-Access-Mode": "keyless",
        }

    return config

