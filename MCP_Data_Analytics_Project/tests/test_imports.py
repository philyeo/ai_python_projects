"""Verification: import all modules, list registered MCP tools, build config."""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    import pandas_mcp.pandas_server as ps
    import rag_mcp.rag_server as rs
    from aggregator import aggregator_server as ag
    from agent.ai_agent import AIAgent
    import app as flask_app  # noqa: F401  (imports cleanly)

    async def _tools(server):
        return await server.list_tools()

    print("=== Pandas server tools ===")
    for t in asyncio.run(_tools(ps.mcp)):
        print(" -", t.name)

    print("\n=== RAG server tools ===")
    for t in asyncio.run(_tools(rs.mcp)):
        print(" -", t.name)

    print("\n=== Aggregator config ===")
    print(json.dumps(ag.build_aggregator_config(), indent=2, default=str))

    print("\n=== Aggregator proxy type ===", type(ag.aggregator).__name__)
    print("=== AIAgent constructed OK ===", AIAgent() is not None)
    print("\nALL IMPORTS OK")


if __name__ == "__main__":
    main()
