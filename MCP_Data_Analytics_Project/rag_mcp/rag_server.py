"""
RAG MCP Server (STDIO transport).

CSV / Excel + Sentence Transformers + FAISS semantic retrieval.

Adapted from the existing AgenticAIProject ``RAG_Server.py`` and split into
``embeddings.py`` (embedding model) and ``vector_store.py`` (FAISS
persistence). It reuses ``pandas_mcp.analytics.load_dataframe`` so CSV and
Excel files are read consistently (including header auto-detection for
business workbooks such as ``ProjectPlan.xlsx``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the project root is importable when this file is run directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from fastmcp import FastMCP

from config import settings
from pandas_mcp import analytics
from rag_mcp import embeddings, vector_store

mcp = FastMCP("RAG MCP Server")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# Tool: load and index dataset
# ---------------------------------------------------------------------------

@mcp.tool()
def load_dataset(file_path: str) -> str:
    """Load an uploaded CSV or Excel dataset and index it for retrieval.

    file_path: Absolute path to the file (inside the uploads/ or data/ folder).
    """
    try:
        path = Path(file_path).resolve()
        if not settings.is_allowed_dataset_path(path):
            return _err("File must be inside the uploads/ or data/ folder.")
        if not path.exists():
            return _err("Uploaded file does not exist.")

        df = analytics.load_dataframe(path)
        if df.empty:
            return _err("Dataset is empty.")

        texts = []
        for row_number, row in df.iterrows():
            row_text = " | ".join(
                f"{col}: {row[col]}"
                for col in df.columns
                if pd.notna(row[col])
            )
            texts.append(f"Row {row_number + 1}: {row_text}")

        embedding_vectors = embeddings.encode(texts)
        metadata = {
            "filename": path.name,
            "rows": len(df),
            "columns": df.columns.tolist(),
            "chunks": len(texts),
        }
        vector_store.save_index(embedding_vectors, texts, metadata)

        settings.set_active_dataset(path)

        return _ok({
            "filename": path.name,
            "rows": len(df),
            "columns": df.columns.tolist(),
            "embeddings": len(embedding_vectors),
            "message": "Dataset successfully indexed.",
        })

    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool: semantic search
# ---------------------------------------------------------------------------

@mcp.tool()
def search_dataset(query: str, k: int = 10) -> str:
    """Search the indexed dataset using semantic similarity.

    query: Natural-language question about the dataset.
    k: Number of relevant rows to retrieve (maximum 20).
    """
    if not query.strip():
        return _err("Search query cannot be empty.")

    try:
        index, texts = vector_store.load_index()
        if index is None:
            return _err("No dataset has been indexed yet.")

        k = max(1, min(int(k), 20, index.ntotal))
        query_embedding = embeddings.encode([query])
        results = vector_store.search(index, texts, query_embedding, k)

        return _ok({
            "query": query,
            "results": results,
            "total_results": len(results),
        })

    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool: dataset information
# ---------------------------------------------------------------------------

@mcp.tool()
def get_dataset_info() -> str:
    """Return information about the currently indexed dataset."""
    info = vector_store.load_info()
    if info is None:
        return _err("No dataset has been indexed.")
    return _ok(info)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
