"""Turn each DataFrame row into one passage for retrieval."""

from rag.models import Chunk, SheetTable, WorkbookContent

MAX_RECORD_CHARS = 6000
MAX_NOTE_CHARS = 4000


def build_chunks(content: WorkbookContent) -> tuple[list[Chunk], list[Chunk]]:
    """Return note passages and row passages.

    Notes stay out of the vector index and are always given to the model.
    Row passages are what the index searches.
    """

    notes: list[Chunk] = []
    records: list[Chunk] = []
    for table in content.tables:
        note = _note_chunk(table)
        if note is not None:
            notes.append(note)
        records.extend(_record_chunks(table))
    return notes, records


def inventory_text(content: WorkbookContent) -> str:
    """Describe every detected table. This is the whole sheet, not the search hits."""

    lines: list[str] = []
    for table in content.tables:
        columns = ", ".join(table.columns) if table.columns else "(no columns)"
        lines.append(
            f"Sheet {table.sheet}, header on row {table.header_row}: "
            f"{len(table.frame)} data rows. Columns: {columns}."
        )
    return "\n".join(lines)


def _note_chunk(table: SheetTable) -> Chunk | None:
    body = table.notes.strip()
    if not body:
        return None
    if len(body) > MAX_NOTE_CHARS:
        body = body[: MAX_NOTE_CHARS - 1].rstrip() + "…"
    text = (
        f"Sheet: {table.sheet}\n"
        f"This text sits above the table whose header is on row {table.header_row}.\n"
        f"{body}"
    )
    return Chunk(
        kind="note",
        sheet=table.sheet,
        title=f"{table.sheet}, text above the header on row {table.header_row}",
        text=text,
        display=body,
    )


def _record_chunks(table: SheetTable) -> list[Chunk]:
    chunks: list[Chunk] = []
    for position, (_, series) in enumerate(table.frame.iterrows()):
        pairs = [(str(column), str(series[column]).strip()) for column in table.frame.columns]
        pairs = [(column, value) for column, value in pairs if value]
        if not pairs:
            continue
        excel_row = table.excel_rows[position]
        body = " | ".join(f"{column}: {value}" for column, value in pairs)
        text = f"Sheet: {table.sheet} | Row: {excel_row} | {body}"
        if len(text) > MAX_RECORD_CHARS:
            text = text[: MAX_RECORD_CHARS - 1].rstrip() + "…"
        chunks.append(
            Chunk(
                kind="record",
                sheet=table.sheet,
                excel_row=excel_row,
                title=f"{table.sheet}, row {excel_row}",
                text=text,
                display="; ".join(f"{column}: {value}" for column, value in pairs),
            )
        )
    return chunks
