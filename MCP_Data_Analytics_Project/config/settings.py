"""
Central configuration for the MCP Data Analytics AI Agent project.

Loads environment variables from the project ``.env`` file and exposes the
shared paths and settings used by:

- the Pandas MCP server (STDIO)
- the RAG MCP server (STDIO)
- the Web Search MCP configuration
- the MCP Aggregator (Streamable HTTP)
- the LangChain AI agent
- the Flask application

All paths are absolute, derived from this file's location, so the project
works regardless of the current working directory.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains this ``config`` directory.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load the project .env file (no-op if it does not exist).
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _resolve_path(value: str, default: Path) -> Path:
    """Resolve a possibly-relative path against the project root."""
    path = Path(value.strip()) if value and value.strip() else Path(default)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


UPLOAD_FOLDER = _resolve_path(
    os.getenv("UPLOAD_FOLDER", ""),
    BASE_DIR / "uploads",
)

DATA_FOLDER = _resolve_path(
    os.getenv("DATA_FOLDER", ""),
    BASE_DIR / "data",
)

VECTOR_STORE_PATH = _resolve_path(
    os.getenv("VECTOR_STORE_PATH", ""),
    BASE_DIR / "vector_store",
)

LOGS_FOLDER = BASE_DIR / "logs"

# Shared "active dataset" state file. The Pandas and RAG servers both read
# this to discover which dataset the user is currently working with.
ACTIVE_DATASET_FILE = LOGS_FOLDER / "active_dataset.json"

# ---------------------------------------------------------------------------
# LLM (OpenRouter-compatible OpenAI API)
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1",
)
MODEL = os.getenv("MODEL", "openai/gpt-4o-mini")

# ---------------------------------------------------------------------------
# Web Search MCP (Tavily)
# ---------------------------------------------------------------------------

TAVILY_MCP_URL = os.getenv("TAVILY_MCP_URL", "https://mcp.tavily.com/mcp/")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ---------------------------------------------------------------------------
# MCP Aggregator / Flask
# ---------------------------------------------------------------------------

AGGREGATOR_HOST = os.getenv("AGGREGATOR_HOST", "127.0.0.1")
AGGREGATOR_PORT = int(os.getenv("AGGREGATOR_PORT", "8000"))
AGGREGATOR_URL = os.getenv(
    "AGGREGATOR_URL",
    f"http://{AGGREGATOR_HOST}:{AGGREGATOR_PORT}/mcp",
)

FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)

ALLOWED_EXTENSIONS = {"csv", "xlsx"}


def get_secret_key() -> str:
    """Return the Flask secret key, or a generated value for development."""
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    # Fallback: a stable per-process random key (sessions reset on restart).
    return secrets.token_hex(32)


def ensure_directories() -> None:
    """Create the folders the application relies on."""
    for folder in (UPLOAD_FOLDER, DATA_FOLDER, VECTOR_STORE_PATH, LOGS_FOLDER):
        folder.mkdir(parents=True, exist_ok=True)


def is_allowed_dataset_path(path: str | Path) -> bool:
    """Return True if ``path`` is inside the uploads or data folder."""
    resolved = Path(path).resolve()
    return (
        resolved.is_relative_to(UPLOAD_FOLDER)
        or resolved.is_relative_to(DATA_FOLDER)
    )


def get_active_dataset() -> str | None:
    """Return the absolute path of the currently active dataset, if any."""
    try:
        if ACTIVE_DATASET_FILE.exists():
            data = json.loads(ACTIVE_DATASET_FILE.read_text(encoding="utf-8"))
            path = data.get("active_dataset")
            if path:
                return str(Path(path).resolve())
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return None


def set_active_dataset(path: str | Path) -> None:
    """Persist the active dataset path for the Pandas and RAG servers."""
    LOGS_FOLDER.mkdir(parents=True, exist_ok=True)
    ACTIVE_DATASET_FILE.write_text(
        json.dumps({"active_dataset": str(Path(path).resolve())}, indent=2),
        encoding="utf-8",
    )
