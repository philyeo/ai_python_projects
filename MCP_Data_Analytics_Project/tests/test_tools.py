"""End-to-end test: invoke the FastMCP tools directly (no transport needed)."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"


def _text(result) -> str:
    """Extract a plain string from a ToolResult."""
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", block)))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(result)


async def main():
    import pandas_mcp.pandas_server as ps
    import rag_mcp.rag_server as rs

    titanic = str((DATA / "titanic.csv").resolve())
    plan = str((DATA / "ProjectPlan.xlsx").resolve())

    print("\n=== RAG load_dataset (titanic) ===")
    r = await rs.mcp.call_tool("load_dataset", {"file_path": titanic})
    print(_text(r)[:500])

    print("\n=== RAG search_dataset ===")
    r = await rs.mcp.call_tool(
        "search_dataset", {"query": "female passenger survived", "k": 3}
    )
    print(_text(r)[:800])

    print("\n=== RAG get_dataset_info ===")
    r = await rs.mcp.call_tool("get_dataset_info", {})
    print(_text(r)[:300])

    print("\n=== Pandas load_dataset (ProjectPlan) ===")
    r = await ps.mcp.call_tool("load_dataset", {"file_path": plan})
    print(_text(r)[:500])

    print("\n=== Pandas groupby_data (Module count) ===")
    r = await ps.mcp.call_tool(
        "groupby_data",
        {"group_by": "Module", "agg_func": "count"},
    )
    print(_text(r))

    print("\n=== Pandas aggregate_data (row count) ===")
    r = await ps.mcp.call_tool(
        "aggregate_data", {"column": "", "agg_func": "count"}
    )
    print(_text(r))

    print("\nALL TOOL CALLS OK")


if __name__ == "__main__":
    asyncio.run(main())
