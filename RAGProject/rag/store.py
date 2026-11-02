"""Embed row passages with OpenRouter and search them with FAISS."""

from __future__ import annotations

import logging

import faiss
import numpy as np
from openai import OpenAI

from rag.errors import AppError
from rag.models import Chunk

logger = logging.getLogger(__name__)

EMBED_MODEL = "openai/text-embedding-3-small"
# The OpenAI key lives in OpenRouter BYOK. Pinning the provider keeps the call
# on that key instead of another host.
PROVIDER = {"provider": {"order": ["openai"], "allow_fallbacks": False}}
BATCH = 64


class RowIndex:
    """In-memory cosine index over one workbook's row passages."""

    def __init__(self, client: OpenAI, chunks: list[Chunk], matrix: np.ndarray):
        self._client = client
        self.chunks = chunks
        self._index = faiss.IndexFlatIP(matrix.shape[1])
        self._index.add(matrix)

    @classmethod
    def build(cls, client: OpenAI, chunks: list[Chunk]) -> "RowIndex":
        matrix = _embed(client, [chunk.text for chunk in chunks])
        return cls(client, chunks, matrix)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        if not self.chunks:
            return []
        query_vector = _embed(self._client, [query])
        count = min(k, len(self.chunks))
        scores, identifiers = self._index.search(query_vector, count)
        found: list[Chunk] = []
        for score, identifier in zip(scores[0], identifiers[0]):
            position = int(identifier)
            if position < 0:
                continue
            original = self.chunks[position]
            found.append(
                Chunk(
                    kind=original.kind,
                    sheet=original.sheet,
                    title=original.title,
                    text=original.text,
                    display=original.display,
                    excel_row=original.excel_row,
                    score=float(score),
                )
            )
        return found


def _embed(client: OpenAI, texts: list[str]) -> np.ndarray:
    vectors: list[list[float] | None] = [None] * len(texts)
    try:
        for start in range(0, len(texts), BATCH):
            batch = texts[start : start + BATCH]
            response = client.embeddings.create(
                model=EMBED_MODEL,
                input=batch,
                extra_body=PROVIDER,
            )
            for offset, item in enumerate(response.data):
                index = item.index if getattr(item, "index", None) is not None else offset
                vectors[start + index] = item.embedding
    except Exception as exc:
        logger.exception("Embedding request failed")
        raise AppError(openrouter_message(exc)) from exc
    if any(vector is None for vector in vectors):
        raise AppError("OpenRouter returned an incomplete embedding response.")
    matrix = np.asarray(vectors, dtype="float32")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return np.ascontiguousarray(matrix / norms, dtype="float32")


def openrouter_message(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    detail = getattr(exc, "message", None) or str(exc)
    detail = " ".join(detail.split())[:300]
    if status:
        return f"OpenRouter returned an error ({status}). {detail}"
    return f"The request to OpenRouter failed. {detail}"
