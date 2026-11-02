
# ============================================================
# RAG MCP SERVER
# CSV / EXCEL + SENTENCE TRANSFORMERS + FAISS
# TRANSPORT: STDIO
# ============================================================

import os
import json
import pickle
import numpy as np
import pandas as pd
import faiss

from pathlib import Path
from sentence_transformers import SentenceTransformer
from fastmcp import FastMCP


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = PROJECT_DIR / "uploads"
VECTOR_FOLDER = PROJECT_DIR / "vectorstore"

UPLOAD_FOLDER.mkdir(exist_ok=True)
VECTOR_FOLDER.mkdir(exist_ok=True)

INDEX_PATH = VECTOR_FOLDER / "rag_index.faiss"
TEXT_PATH = VECTOR_FOLDER / "rag_texts.pkl"
INFO_PATH = VECTOR_FOLDER / "dataset_info.json"

MODEL_NAME = "all-MiniLM-L6-v2"

mcp = FastMCP("RAG MCP Server")

# Embedding model
embedder = SentenceTransformer(MODEL_NAME)


# ============================================================
# LOAD EXISTING VECTORSTORE
# ============================================================

def load_vectorstore():

    if not INDEX_PATH.exists() or not TEXT_PATH.exists():
        return None, []

    index = faiss.read_index(str(INDEX_PATH))

    with open(TEXT_PATH, "rb") as file:
        texts = pickle.load(file)

    return index, texts


# ============================================================
# TOOL 1: LOAD DATASET
# ============================================================

@mcp.tool()
def load_dataset(file_path: str) -> str:
    """
    Load an uploaded CSV or Excel dataset.
    Convert rows into text, generate embeddings,
    and store the vectors in FAISS.

    file_path: Absolute path to the uploaded file.
    """

    file_path = Path(file_path).resolve()

    # Security: only allow files inside uploads/
    if not file_path.is_relative_to(UPLOAD_FOLDER.resolve()):
        return "Error: File must be inside the uploads folder."

    if not file_path.exists():
        return "Error: Uploaded file does not exist."

    try:

        # Read file
        if file_path.suffix.lower() == ".csv":
            df = pd.read_csv(file_path)

        elif file_path.suffix.lower() == ".xlsx":
            df = pd.read_excel(file_path)

        else:
            return "Error: Only CSV and XLSX are supported."

        if df.empty:
            return "Error: Dataset is empty."

        # Convert each row into text
        texts = []

        for row_number, row in df.iterrows():

            row_text = " | ".join(
                [
                    f"{col}: {row[col]}"
                    for col in df.columns
                    if pd.notna(row[col])
                ]
            )

            texts.append(
                f"Row {row_number + 1}: {row_text}"
            )

        # Generate embeddings
        embeddings = embedder.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True
        )

        embeddings = np.asarray(
            embeddings,
            dtype="float32"
        )

        # Build FAISS index
        dimension = embeddings.shape[1]

        index = faiss.IndexFlatL2(dimension)

        index.add(embeddings)

        # Save index
        faiss.write_index(
            index,
            str(INDEX_PATH)
        )

        # Save text chunks
        with open(TEXT_PATH, "wb") as file:
            pickle.dump(texts, file)

        # Save dataset metadata
        metadata = {
            "filename": file_path.name,
            "rows": len(df),
            "columns": df.columns.tolist(),
            "chunks": len(texts)
        }

        with open(INFO_PATH, "w") as file:
            json.dump(metadata, file, indent=4)

        return json.dumps({
            "status": "success",
            "filename": file_path.name,
            "rows": len(df),
            "columns": df.columns.tolist(),
            "embeddings": len(embeddings),
            "message": "Dataset successfully indexed."
        })

    except Exception as e:

        return f"Error loading dataset: {str(e)}"


# ============================================================
# TOOL 2: SEARCH DATASET
# ============================================================

@mcp.tool()
def search_dataset(query: str, k: int = 10) -> str:
    """
    Search the uploaded dataset using semantic similarity.

    query: Natural language question about the dataset.
    k: Number of relevant rows to retrieve.
    """

    if not query.strip():
        return "Error: Search query cannot be empty."

    index, texts = load_vectorstore()

    if index is None:
        return "Error: No dataset has been uploaded yet."

    try:

        k = max(1, min(int(k), 20, index.ntotal))

        # Convert question into embedding
        query_embedding = embedder.encode(
            [query],
            convert_to_numpy=True
        )

        query_embedding = np.asarray(
            query_embedding,
            dtype="float32"
        )

        # FAISS similarity search
        distances, indices = index.search(
            query_embedding,
            k
        )

        results = []

        for distance, idx in zip(
            distances[0],
            indices[0]
        ):

            if idx < 0:
                continue

            results.append({
                "text": texts[int(idx)],
                "distance": float(distance)
            })

        return json.dumps({
            "query": query,
            "results": results,
            "total_results": len(results)
        }, ensure_ascii=False)

    except Exception as e:

        return f"Search error: {str(e)}"


# ============================================================
# TOOL 3: DATASET INFORMATION
# ============================================================

@mcp.tool()
def get_dataset_info() -> str:
    """
    Return information about the currently indexed dataset,
    including filename, columns, and number of rows.
    """

    if not INFO_PATH.exists():
        return "No dataset has been uploaded."

    with open(INFO_PATH, "r") as file:
        return json.dumps(
            json.load(file),
            indent=4
        )


# ============================================================
# RUN MCP SERVER
# ============================================================

if __name__ == "__main__":

    mcp.run(transport="stdio")
