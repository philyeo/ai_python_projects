"""Web page for asking a question about an uploaded Excel workbook."""

from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, render_template
from openai import OpenAI
from werkzeug.datastructures import FileStorage

from rag.answer import answer_question
from rag.chunk import build_chunks, inventory_text
from rag.errors import AppError
from rag.ingest import load_workbook
from rag.models import Chunk, WorkbookContent
from rag.store import RowIndex

ROOT = Path(__file__).resolve().parent
UPLOADS = ROOT / "uploads"
MAX_BYTES = 8 * 1024 * 1024
ALLOWED = {".xlsx", ".xlsm", ".xls"}
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES


@dataclass
class LoadedWorkbook:
    filename: str
    stored_path: Path
    content: WorkbookContent
    notes: list[Chunk]
    index: RowIndex | None
    header_row: str


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.loaded: LoadedWorkbook | None = None
        self.question = ""
        self.answer = ""
        self.sources: list[Chunk] = []


STATE = _State()


@app.get("/")
def home():
    return render_page()


@app.post("/upload")
def upload():
    header_row_text = request.form.get("header_row", "").strip()
    try:
        header_row = _parse_header_row(header_row_text)
        incoming = request.files.get("file")
        saved, original_name = _save_upload(incoming)
    except AppError as exc:
        return render_page(error=str(exc), header_row=header_row_text)
    try:
        content = load_workbook(saved, header_row)
        notes, records = build_chunks(content)
        client = _client()
        index = RowIndex.build(client, records) if records else None
    except AppError as exc:
        saved.unlink(missing_ok=True)
        return render_page(error=str(exc), header_row=header_row_text)
    except Exception:
        logger.exception("Upload failed")
        saved.unlink(missing_ok=True)
        return render_page(
            error="The workbook could not be read.",
            header_row=header_row_text,
        )
    with STATE.lock:
        previous = STATE.loaded
        STATE.loaded = LoadedWorkbook(
            filename=original_name,
            stored_path=saved,
            content=content,
            notes=notes,
            index=index,
            header_row=header_row_text,
        )
        STATE.question = ""
        STATE.answer = ""
        STATE.sources = []
    if previous is not None:
        previous.stored_path.unlink(missing_ok=True)
    return render_page()


@app.post("/ask")
def ask():
    question = request.form.get("question", "").strip()
    if not question:
        return render_page(error="Enter a question.", question=question)
    with STATE.lock:
        loaded = STATE.loaded
    if loaded is None:
        return render_page(error="Upload a workbook before asking a question.", question=question)
    try:
        rows = loaded.index.search(question, k=5) if loaded.index is not None else []
        if not rows and not loaded.notes:
            raise AppError("This workbook has nothing to search.")
        reply = answer_question(
            _client(),
            question,
            inventory_text(loaded.content),
            loaded.notes,
            rows,
        )
    except AppError as exc:
        return render_page(error=str(exc), question=question)
    except Exception:
        logger.exception("Question failed")
        return render_page(error="The question could not be answered.", question=question)
    with STATE.lock:
        STATE.question = question
        STATE.answer = reply
        STATE.sources = [*loaded.notes, *rows]
    return render_page()


@app.errorhandler(413)
def too_large(_error):
    return render_page(error="That file is larger than 8 MB."), 413


def render_page(error: str | None = None, header_row: str | None = None, question: str | None = None, status: int = 200):
    with STATE.lock:
        loaded = STATE.loaded
        page_question = STATE.question if question is None else question
        answer = STATE.answer
        sources = list(STATE.sources)
        stored_header = loaded.header_row if loaded is not None else ""
    chosen_header = stored_header if header_row is None else header_row
    tables = []
    warnings: list[str] = []
    filename = ""
    if loaded is not None:
        filename = loaded.filename
        warnings = list(loaded.content.warnings)
        tables = [_table_view(table) for table in loaded.content.tables]
    body = render_template(
        "index.html",
        error=error,
        filename=filename,
        tables=tables,
        warnings=warnings,
        header_row=chosen_header,
        question=page_question,
        answer=answer,
        sources=sources,
        loaded=loaded is not None,
    )
    return body, status


def _table_view(table) -> dict:
    preview = []
    limit = 8
    for excel_row, (_, series) in zip(table.excel_rows, table.frame.iterrows()):
        preview.append(
            {
                "excel_row": excel_row,
                "values": {column: str(series[column]) for column in table.frame.columns},
            }
        )
        if len(preview) >= limit:
            break
    return {
        "sheet": table.sheet,
        "header_row": table.header_row,
        "columns": table.columns,
        "row_count": len(table.frame),
        "notes": table.notes,
        "preview": preview,
        "preview_limited": len(table.frame) > len(preview),
    }


def _parse_header_row(raw: str) -> int | None:
    if not raw:
        return None
    if not raw.isdigit() or int(raw) < 1:
        raise AppError("Header row must be a whole number, or left blank.")
    return int(raw)


def _save_upload(incoming: FileStorage | None) -> tuple[Path, str]:
    if incoming is None or not incoming.filename:
        raise AppError("Choose an Excel file.")
    original = Path(incoming.filename).name
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED:
        raise AppError("Upload an .xlsx, .xlsm, or .xls file.")
    UPLOADS.mkdir(exist_ok=True)
    destination = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    incoming.save(destination)
    return destination, original


def _client() -> OpenAI:
    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise AppError("OPENROUTER_API_KEY is missing from the .env file in this folder.")
    return OpenAI(base_url=OPENROUTER_BASE, api_key=key, timeout=90)


if __name__ == "__main__":
    UPLOADS.mkdir(exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=False)
