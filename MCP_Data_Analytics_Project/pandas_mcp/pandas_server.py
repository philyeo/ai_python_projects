"""
Pandas MCP Server (STDIO transport).

Exposes reusable Pandas analytics functions (from ``analytics.py``) as MCP
tools using FastMCP.

Design notes:

- The server keeps the currently active dataset in a module-level cache and
  also records the active dataset path in the shared state file
  (``config.settings``), so the dataset survives subprocess restarts and is
  discoverable by the RAG server too.
- Tools return JSON strings (matching the RAG server's convention) so the
  LangChain agent can parse them uniformly.
- Every tool validates inputs and returns an explicit ``status`` field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the project root is importable when this file is run directly
# (e.g. as a subprocess launched by the aggregator).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastmcp import FastMCP

from config import settings
from pandas_mcp import analytics

mcp = FastMCP("Pandas MCP Server")

# In-memory cache of the active dataset.
_active_df = None
_active_path: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dataframe():
    """Return the active DataFrame, loading it from disk if necessary."""
    global _active_df, _active_path

    path = settings.get_active_dataset()
    if not path:
        raise ValueError("No dataset loaded. Call load_dataset first.")

    if _active_df is not None and _active_path == path:
        return _active_df

    df = analytics.load_dataframe(path)
    _active_df = df
    _active_path = path
    return df


def _ok(payload: dict) -> str:
    return json.dumps(
        {"status": "success", **payload},
        ensure_ascii=False,
        default=str,
    )


def _err(message) -> str:
    return json.dumps(
        {"status": "error", "message": str(message)},
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Tool: load dataset
# ---------------------------------------------------------------------------

@mcp.tool()
def load_dataset(file_path: str) -> str:
    """Load a CSV or XLSX dataset and make it the active dataset.

    file_path: Absolute path to the file (inside the uploads/ or data/ folder).
    """
    try:
        path = Path(file_path).resolve()
        if not settings.is_allowed_dataset_path(path):
            return _err("File must be inside the uploads/ or data/ folder.")

        df = analytics.load_dataframe(path)

        global _active_df, _active_path
        _active_df = df
        _active_path = str(path)
        settings.set_active_dataset(path)

        info = analytics.get_dataset_info(df)
        return _ok({
            "file_path": str(path),
            "filename": path.name,
            **info,
        })

    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool: dataset information
# ---------------------------------------------------------------------------

@mcp.tool()
def get_dataset_info() -> str:
    """Return dimensions, columns and data types of the active dataset."""
    try:
        return _ok(analytics.get_dataset_info(_get_dataframe()))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool: column summary
# ---------------------------------------------------------------------------

@mcp.tool()
def get_column_summary(column: str) -> str:
    """Return descriptive statistics for a column of the active dataset.

    column: Name of the column to summarise.
    """
    try:
        return _ok(analytics.get_column_summary(_get_dataframe(), column))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)



# ---------------------------------------------------------------------------
# Tool: aggregation
# ---------------------------------------------------------------------------

@mcp.tool()
def aggregate_data(column: str, agg_func: str = "count") -> str:
    """Apply a single aggregation to a column (count/sum/mean/min/max/median).

    column: Column to aggregate. Use an empty string with agg_func="count"
        to count all rows.
    agg_func: One of count, sum, mean, min, max, median, std, var, nunique.
    """
    try:
        return _ok(analytics.aggregate_data(_get_dataframe(), column, agg_func))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool: group by
# ---------------------------------------------------------------------------

@mcp.tool()
def groupby_data(
    group_by: str,
    agg_func: str = "mean",
    value_column: str = "",
) -> str:
    """Group the active dataset by one or more columns and aggregate a measure.

    group_by: Column name, or comma-separated column names, to group by.
    agg_func: Aggregation to apply (count, sum, mean, min, max, median, ...).
    value_column: Column to aggregate. Required unless agg_func is "count".
    """
    try:
        return _ok(
            analytics.groupby_data(
                _get_dataframe(),
                group_by,
                agg_func,
                value_column,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool: filter
# ---------------------------------------------------------------------------

@mcp.tool()
def filter_dataset(filters: str, limit: int = 50) -> str:
    """Filter records of the active dataset using validated conditions.

    filters: A JSON array of condition objects, for example
        [{"column": "age", "operator": ">", "value": 50},
         {"column": "survived", "operator": "==", "value": 1}].
        Supported operators: ==, !=, >, >=, <, <=, contains, not_contains,
        startswith, isnull, notnull, in, not_in.
    limit: Maximum number of result rows to return (default 50, max 500).
    """
    try:
        return _ok(analytics.filter_dataset(_get_dataframe(), filters, limit))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
