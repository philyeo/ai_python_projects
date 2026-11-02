"""Ask the chat model to answer from the inventory, the notes, and the retrieved rows."""

from __future__ import annotations

import logging

from openai import OpenAI

from rag.errors import AppError
from rag.models import Chunk
from rag.store import PROVIDER, openrouter_message

logger = logging.getLogger(__name__)

CHAT_MODEL = "openai/gpt-4o-mini"

SYSTEM = (
    "You answer questions about one uploaded Excel workbook. "
    "Use only the inventory, the notes, and the retrieved rows. "
    "The inventory describes every detected table. "
    "The retrieved rows are the closest matches, not every row. "
    "A field that does not appear in a row was blank. Do not invent a value for it. "
    "Do not invent names, dates, counts, or statuses. "
    "If the notes or rows give more than one project name, report every name that is written there. "
    "If the workbook does not show the answer, say so. "
    "Write plain sentences. Do not use markdown."
)


def answer_question(
    client: OpenAI,
    question: str,
    inventory: str,
    notes: list[Chunk],
    rows: list[Chunk],
) -> str:
    response = None
    try:
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _user_prompt(question, inventory, notes, rows)},
            ],
            extra_body=PROVIDER,
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("Chat request failed")
        raise AppError(openrouter_message(exc)) from exc
    if not text:
        raise AppError("OpenRouter returned an empty answer.")
    return text


def _user_prompt(question: str, inventory: str, notes: list[Chunk], rows: list[Chunk]) -> str:
    parts = ["Inventory:", inventory or "No table inventory.", ""]
    parts.append("Notes:")
    if notes:
        for note in notes:
            parts.append(note.text)
            parts.append("")
    else:
        parts.append("None.")
        parts.append("")
    parts.append("Retrieved rows:")
    if rows:
        for number, row in enumerate(rows, start=1):
            parts.append(f"{number}. {row.text}")
    else:
        parts.append("None.")
    parts.append("")
    parts.append(f"Question: {question}")
    return "\n".join(parts)
