"""
FAISS vector store management.

Persists a flat-L2 FAISS index, the corresponding text chunks, and dataset
metadata to the configured vector store directory.
"""

from __future__ import annotations

import json
import pickle
from typing import Any

import faiss
import numpy as np

from config import settings

INDEX_PATH = settings.VECTOR_STORE_PATH / "rag_index.faiss"
TEXT_PATH = settings.VECTOR_STORE_PATH / "rag_texts.pkl"
INFO_PATH = settings.VECTOR_STORE_PATH / "dataset_info.json"


def save_index(embeddings: np.ndarray, texts: list[str], metadata: dict) -> None:
    """Build and persist a FAISS index, its texts, and dataset metadata."""
    settings.VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    faiss.write_index(index, str(INDEX_PATH))

    with open(TEXT_PATH, "wb") as file:
        pickle.dump(texts, file)

    with open(INFO_PATH, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4, ensure_ascii=False)


def load_index() -> tuple[Any, list[str]]:
    """Return ``(index, texts)``, or ``(None, [])`` if nothing is indexed."""
    if not INDEX_PATH.exists() or not TEXT_PATH.exists():
        return None, []

    index = faiss.read_index(str(INDEX_PATH))
    with open(TEXT_PATH, "rb") as file:
        texts = pickle.load(file)

    return index, texts


def search(
    index: Any,
    texts: list[str],
    query_embedding: np.ndarray,
    k: int,
) -> list[dict]:
    """Run a FAISS similarity search and return result dictionaries."""
    distances, indices = index.search(query_embedding, k)

    results = []
    for distance, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        results.append({
            "text": texts[int(idx)],
            "distance": float(distance),
        })

    return results


def load_info() -> dict | None:
    """Return the stored dataset metadata, or ``None`` if unavailable."""
    if not INFO_PATH.exists():
        return None
    with open(INFO_PATH, "r", encoding="utf-8") as file:
        return json.load(file)
