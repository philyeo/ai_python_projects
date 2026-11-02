"""
Embedding model wrapper.

Uses Sentence Transformers to encode text chunks into dense vectors. The
model is loaded lazily and cached as a module-level singleton so that it is
only downloaded/loaded once per process.
"""

from __future__ import annotations

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from config import settings

# Suppress huggingface_hub's advisory "unauthenticated requests" log so it
# does not clutter stderr on every model load.
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

_embedder: SentenceTransformer | None = None


def get_embedder() -> SentenceTransformer:
    """Return the shared SentenceTransformer instance (lazy singleton)."""
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedder


def encode(texts: list[str]) -> np.ndarray:
    """Encode a list of texts into a float32 numpy array of embeddings."""
    embedder = get_embedder()
    embeddings = embedder.encode(
        texts,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return np.asarray(embeddings, dtype="float32")
