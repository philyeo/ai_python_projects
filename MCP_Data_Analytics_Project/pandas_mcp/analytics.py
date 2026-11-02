"""
Pure, reusable Pandas analytics functions.

These functions operate on an in-memory ``pandas.DataFrame`` and return plain
Python objects (dicts / lists) that can be serialized to JSON by the MCP layer.
No FastMCP or transport logic lives here - that is the job of
``pandas_server.py``.

Design principles:

- Never use ``eval`` / ``exec`` on LLM-supplied strings.
- Validate column names, aggregation functions and filter operators.
- Treat missing values explicitly: blanks are treated as missing (NaN), never
  silently as zero. Numeric aggregations therefore exclude missing values,
  matching pandas' default behaviour.
- Raise ``ValueError`` with friendly messages so the agent can relay a useful
  explanation instead of failing silently.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_AGGREGATIONS = {
    "count",
    "sum",
    "mean",
    "min",
    "max",
    "median",
    "std",
    "var",
    "nunique",
}

_OPERATOR_ALIASES = {
    "eq": "==", "==": "==",
    "ne": "!=", "!=": "!=",
    "gt": ">", ">": ">",
    "ge": ">=", ">=": ">=",
    "lt": "<", "<": "<",
    "le": "<=", "<=": "<=",
    "contains": "contains",
    "not_contains": "not_contains",
    "startswith": "startswith",
    "isnull": "isnull",
    "notnull": "notnull",
    "in": "in",
    "not_in": "not_in",
}

DEFAULT_OUTPUT_LIMIT = 50
MAX_OUTPUT_LIMIT = 500


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def jsonable(value: Any) -> Any:
    """Recursively convert a value to a JSON-safe Python object."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, str):
        return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "item"):
        try:
            return jsonable(value.item())
        except (ValueError, TypeError):
            pass
    return str(value)


def _records(df: pd.DataFrame, limit: int = DEFAULT_OUTPUT_LIMIT) -> list[dict]:
    """Convert a DataFrame to a list of JSON-safe record dicts, capped."""
    limit = max(0, min(int(limit), MAX_OUTPUT_LIMIT))
    rows = df.head(limit).to_dict(orient="records")
    return [
        {str(k): jsonable(v) for k, v in record.items()}
        for record in rows
    ]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _clean_column_name(name: Any) -> str:
    """Strip and collapse whitespace in a column name."""
    if name is None:
        return ""
    return re.sub(r"\s+", " ", str(name)).strip()


def _find_header_row(raw: pd.DataFrame) -> int:
    """Find the row most likely to be the header (most non-empty cells)."""
    best_idx, best_score = 0, -1
    for idx, row in raw.iterrows():
        score = sum(
            1 for value in row
            if pd.notna(value) and str(value).strip() != ""
        )
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx


def _fallback_column_name(index: int, header: list[str]) -> str:
    """Name an empty header cell sensibly.

    The supplied ``ProjectPlan.xlsx`` has a broken ``#REF!`` column between
    "Type" and "Module" that holds construct types ("UI Generator",
    "API Service Program"). We recover it as "ConstructType".
    """
    if (
        0 < index < len(header) - 1
        and header[index - 1] == "Type"
        and header[index + 1] == "Module"
    ):
        return "ConstructType"
    return f"Column_{index}"


def _read_excel(path: Path) -> pd.DataFrame:
    """Read an Excel workbook, auto-detecting the header row.

    Business workbooks (like ``ProjectPlan.xlsx``) often have title rows above
    the real header. This helper locates the header row and returns a clean
    DataFrame.
    """
    raw = pd.read_excel(path, header=None, dtype=object)

    header_idx = _find_header_row(raw)
    header: list[str] = []
    for cell in raw.iloc[header_idx]:
        header.append(_clean_column_name(cell) if pd.notna(cell) else "")

    for i in range(len(header)):
        if header[i] == "":
            header[i] = _fallback_column_name(i, header)

    df = raw.iloc[header_idx + 1:].reset_index(drop=True)
    df.columns = header

    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    return df.reset_index(drop=True)


def load_dataframe(file_path: str | Path) -> pd.DataFrame:
    """Load a CSV or XLSX file into a DataFrame.

    Raises ``ValueError`` with a friendly message on failure.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise ValueError(f"File does not exist: {path}")

    extension = path.suffix.lower()
    if extension == ".csv":
        df = pd.read_csv(path)
    elif extension in (".xlsx", ".xls"):
        df = _read_excel(path)
    else:
        raise ValueError("Only CSV and XLSX files are supported.")

    if df.empty:
        raise ValueError("The dataset is empty.")

    df.columns = [_clean_column_name(c) for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _resolve_column(df: pd.DataFrame, column: str) -> str:
    """Return the exact DataFrame column matching ``column`` (case-insensitive)."""
    if not column or not str(column).strip():
        raise ValueError("A column name is required.")
    requested = str(column).strip()
    for candidate in df.columns:
        if str(candidate).strip().lower() == requested.lower():
            return str(candidate)
    raise ValueError(
        f"Column '{requested}' not found. Available columns: {list(df.columns)}"
    )


def _validate_agg(func: str) -> str:
    """Validate and canonicalise an aggregation function name."""
    func = (func or "count").strip().lower()
    if func not in VALID_AGGREGATIONS:
        raise ValueError(
            f"Unsupported aggregation '{func}'. "
            f"Choose from: {sorted(VALID_AGGREGATIONS)}"
        )
    return func


def _canonical_operator(operator: str) -> str:
    operator = (operator or "").strip().lower()
    if operator not in _OPERATOR_ALIASES:
        supported = sorted({v for v in _OPERATOR_ALIASES.values()})
        raise ValueError(
            f"Unsupported operator '{operator}'. Choose from: {supported}"
        )
    return _OPERATOR_ALIASES[operator]


def _coerce_value(series: pd.Series, value: Any) -> Any:
    """Coerce a comparison value to the column's type where sensible."""
    if value is None:
        return None
    if pd.api.types.is_bool_dtype(series):
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return bool(value)
    if pd.api.types.is_numeric_dtype(series):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


# ---------------------------------------------------------------------------
# Tool 1 - dataset information
# ---------------------------------------------------------------------------

def get_dataset_info(df: pd.DataFrame) -> dict:
    """Return dimensions, columns, data types and missing-value counts."""
    return {
        "rows": int(len(df)),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "dtypes": {str(c): str(df[c].dtype) for c in df.columns},
        "missing_values": {
            str(c): int(df[c].isna().sum()) for c in df.columns
        },
    }


# ---------------------------------------------------------------------------
# Tool 2 - column summary
# ---------------------------------------------------------------------------

def get_column_summary(df: pd.DataFrame, column: str) -> dict:
    """Return descriptive statistics for a single column."""
    column = _resolve_column(df, column)
    series = df[column]

    summary: dict[str, Any] = {
        "column": column,
        "dtype": str(series.dtype),
        "count": int(series.count()),
        "missing": int(series.isna().sum()),
        "unique": int(series.nunique(dropna=True)),
    }

    if pd.api.types.is_numeric_dtype(series):
        description = series.describe()
        for key in ("count", "mean", "std", "min", "25%", "50%", "75%", "max"):
            if key in description:
                summary[key] = jsonable(description[key])
    else:
        top = series.value_counts(dropna=False).head(10)
        summary["top_values"] = [
            {"value": jsonable(k), "count": int(v)} for k, v in top.items()
        ]

    return summary


# ---------------------------------------------------------------------------
# Tool 3 - aggregation
# ---------------------------------------------------------------------------

def aggregate_data(df: pd.DataFrame, column: str, agg_func: str) -> dict:
    """Apply a single aggregation (count/sum/mean/min/max/...) to a column.

    Use ``column=""`` together with ``agg_func="count"`` to count all rows.
    """
    agg_func = _validate_agg(agg_func)

    if agg_func == "count" and (not column or not str(column).strip()):
        return {
            "column": None,
            "aggregation": "count",
            "description": "row count",
            "result": int(len(df)),
        }

    column = _resolve_column(df, column)
    series = df[column]

    if agg_func == "count":
        result: Any = int(series.count())
    elif agg_func == "nunique":
        result = int(series.nunique(dropna=True))
    else:
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() == 0:
            raise ValueError(
                f"Column '{column}' has no numeric values to aggregate."
            )
        if agg_func == "sum":
            result = jsonable(numeric.sum())
        elif agg_func == "mean":
            result = jsonable(numeric.mean())
        elif agg_func == "min":
            result = jsonable(numeric.min())
        elif agg_func == "max":
            result = jsonable(numeric.max())
        elif agg_func == "median":
            result = jsonable(numeric.median())
        elif agg_func == "std":
            result = jsonable(numeric.std())
        else:  # var
            result = jsonable(numeric.var())

    return {
        "column": column,
        "aggregation": agg_func,
        "result": result,
    }


# ---------------------------------------------------------------------------
# Tool 4 - group by
# ---------------------------------------------------------------------------

def _parse_group_columns(df: pd.DataFrame, group_by: str) -> list[str]:
    if not group_by or not str(group_by).strip():
        raise ValueError("Provide at least one grouping column.")
    raw_columns = [c.strip() for c in str(group_by).split(",") if c.strip()]
    if not raw_columns:
        raise ValueError("Provide at least one grouping column.")
    return [_resolve_column(df, c) for c in raw_columns]


def groupby_data(
    df: pd.DataFrame,
    group_by: str,
    agg_func: str = "mean",
    value_column: str = "",
) -> dict:
    """Group by one or more columns and aggregate a measure.

    ``group_by`` may be a single column or a comma-separated list.
    ``value_column`` is required unless ``agg_func`` is "count".
    """
    group_columns = _parse_group_columns(df, group_by)
    agg_func = _validate_agg(agg_func)

    value_column = (value_column or "").strip()

    if agg_func == "count":
        grouped = df.groupby(group_columns, dropna=False).size().reset_index(
            name="count"
        )
        result_value_column = "count"
    else:
        if not value_column:
            raise ValueError(
                "A value_column is required for non-count aggregations."
            )
        value_col = _resolve_column(df, value_column)
        numeric = pd.to_numeric(df[value_col], errors="coerce")
        grouped = (
            df.assign(**{"__value__": numeric})
            .groupby(group_columns, dropna=False)["__value__"]
            .agg(agg_func)
            .reset_index(name=agg_func)
        )
        result_value_column = agg_func

    return {
        "group_by": group_columns,
        "value_column": result_value_column,
        "aggregation": agg_func,
        "results": _records(grouped, limit=MAX_OUTPUT_LIMIT),
    }


# ---------------------------------------------------------------------------
# Tool 5 - filter
# ---------------------------------------------------------------------------

def _parse_filters(filters: str) -> list[dict]:
    """Parse the ``filters`` JSON string into a list of condition dicts."""
    import json

    if not filters or not str(filters).strip():
        raise ValueError("Provide a filters JSON array.")

    try:
        parsed = json.loads(filters)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "filters must be valid JSON, e.g. "
            '[{"column":"age","operator":">","value":50}]'
        ) from exc

    if not isinstance(parsed, list):
        raise ValueError("filters must be a JSON array of condition objects.")

    conditions = []
    for item in parsed:
        if not isinstance(item, dict) or "column" not in item:
            raise ValueError(
                "Each filter condition must be an object with a 'column' key."
            )
        conditions.append(item)
    return conditions


def _apply_condition(df: pd.DataFrame, condition: dict) -> pd.Series:
    column = _resolve_column(df, condition["column"])
    operator = _canonical_operator(condition.get("operator", "=="))
    raw_value = condition.get("value")
    series = df[column]

    if operator == "isnull":
        return series.isna()
    if operator == "notnull":
        return series.notna()

    if operator in ("in", "not_in"):
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        values = [_coerce_value(series, v) for v in values]
        mask = series.isin(values)
        return ~mask if operator == "not_in" else mask

    if operator in ("contains", "not_contains", "startswith"):
        text = series.astype("string").str
        needle = "" if raw_value is None else str(raw_value)
        if operator == "contains":
            return text.str.contains(needle, case=False, na=False)
        if operator == "not_contains":
            return ~text.str.contains(needle, case=False, na=False)
        return text.str.startswith(needle, na=False)

    value = _coerce_value(series, raw_value)
    if operator == "==":
        return series == value
    if operator == "!=":
        return series != value
    if operator == ">":
        return series > value
    if operator == ">=":
        return series >= value
    if operator == "<":
        return series < value
    if operator == "<=":
        return series <= value

    raise ValueError(f"Unsupported operator '{operator}'.")


def filter_dataset(
    df: pd.DataFrame,
    filters: str,
    limit: int = DEFAULT_OUTPUT_LIMIT,
) -> dict:
    """Filter records using validated conditions.

    ``filters`` is a JSON array of condition objects, for example:
    ``[{"column": "age", "operator": ">", "value": 50},
      {"column": "survived", "operator": "==", "value": 1}]``.
    """
    conditions = _parse_filters(filters)

    mask = pd.Series(True, index=df.index)
    for condition in conditions:
        mask &= _apply_condition(df, condition)

    result = df[mask]
    return {
        "matched_rows": int(len(result)),
        "total_rows": int(len(df)),
        "filters_applied": len(conditions),
        "results": _records(result, limit=limit),
    }


