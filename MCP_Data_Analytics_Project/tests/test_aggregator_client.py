"""Verify the running aggregator exposes all namespaced tools over HTTP."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastmcp import Client  # noqa: E402

URL = "http://127.0.0.1:8000/mcp"


async def main():
    async with Client(URL) as client:
        tools = await client.list_tools()
        print("TOOL COUNT:", len(tools))
        for t in tools:
            print(" -", t.name)


if __name__ == "__main__":
    asyncio.run(main())
