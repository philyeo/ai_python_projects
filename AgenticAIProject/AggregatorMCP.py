
# ============================================================
# MAIN MCP SERVER AGGREGATOR
# OPENSTREETMAP + OPENWEATHER + RAG
# ============================================================

import os
import sys

from pathlib import Path
from fastmcp.server import create_proxy
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = Path(__file__).resolve().parent
RAG_SERVER_PATH = (
    PROJECT_DIR / "RAG_Server.py"
)

PYTHON_PATH = sys.executable


# ============================================================
# MCP SERVER CONFIGURATION
# ============================================================

MCP_CONFIG = {

    "mcpServers": {

        # ----------------------------------------------------
        # REMOTE OPENSTREETMAP MCP
        # ----------------------------------------------------

        "osm": {

            "url": os.getenv(
                "OPEN_STREET_URL",
            ),

            "transport": "http"
        },

        # ----------------------------------------------------
        # REMOTE OPENWEATHER MCP
        # ----------------------------------------------------

        "weather": {

            "url": os.getenv("OPEN_WEATHER_URL"),

            "transport": "http"
        },

        # ----------------------------------------------------
        # LOCAL RAG MCP
        # ----------------------------------------------------

        "rag": {

            "command": PYTHON_PATH,

            "args": [
                str(RAG_SERVER_PATH)
            ],

            "transport": "stdio"
        }
    }
}


# ============================================================
# CREATE AGGREGATOR
# ============================================================

aggregator = create_proxy(
    MCP_CONFIG,
    name="Main MCP Aggregator"
)


# ============================================================
# RUN AGGREGATOR
# ============================================================

if __name__ == "__main__":

    aggregator.run(
        transport="http",
        host="127.0.0.1",
        port=8000
    )
