"""Find tables in a workbook without assuming where the header sits.

Pandas treats the first row as the header. Real workbooks often put a title,
a banner, or blank rows above the header, and a later file will not use the
same row as the sample plan. This module reads the cell grid, chooses the
header row, and only then builds a DataFrame.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.worksheet import Worksheet

from rag.errors import AppError
from rag.models import Cell, SheetTable, WorkbookContent

ROW_CAP = 5000
COL_CAP = 200
EXCEL_ERRORS = {
    "#REF!",
    "#NAME?",
    "#VALUE!",
    "#N/A",
    "#DIV/0!",
    "#NULL!",
    "#NUM!",
    "#GETTING_DATA!",
    "#SPILL!",
    "#CALC!",
    "#BLOCKED!",
    "#UNKNOWN!",
    "#ERROR!",
}


def load_workbook(path: Path, header_row: int | None = None) -> WorkbookContent:
    """Read every worksheet and return the tables it contains.

    ``header_row`` is a 1-based Excel row. When it is set, that row is the
    header of the first table on each sheet. Later tables on the same sheet
    are still detected on their own.
    """

    grids = _read_grids(path)
    tables: list[SheetTable] = []
    warnings: list[str] = []
    for sheet_name, grid, sheet_warnings in grids:
        warnings.extend(sheet_warnings)
        if not grid or all(_is_empty_row(row) for row in grid):
            warnings.append(f"{sheet_name} has no cell values.")
            continue
        for raw in _find_tables(sheet_name, grid, header_row):
            tables.append(_to_table(sheet_name, grid, raw))
    if not tables:
        raise AppError(
            "No table was found. If you know the header row, enter it and read the file again."
        )
    return WorkbookContent(tables=tables, warnings=warnings)


def _read_grids(path: Path) -> list[tuple[str, list[list[Cell]], list[str]]]:
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xlsm"}:
            return _read_ooxml(path)
        if suffix == ".xls":
            return _read_xls(path)
    except AppError:
        raise
    except (InvalidFileException, BadZipFile, ValueError, OSError) as exc:
        raise AppError(
            "This workbook could not be opened. If it is damaged or password protected, "
            "save a copy as .xlsx and upload that."
        ) from exc
    except Exception as exc:
        raise AppError(
            "This workbook could not be opened. Save a copy as .xlsx and upload that."
        ) from exc
    raise AppError("Upload an .xlsx, .xlsm, or .xls file.")


def _read_ooxml(path: Path) -> list[tuple[str, list[list[Cell]], list[str]]]:
    import openpyxl

    formulas = openpyxl.load_workbook(path, data_only=False)
    cached = openpyxl.load_workbook(path, data_only=True)
    sheets: list[tuple[str, list[list[Cell]], list[str]]] = []
    try:
        for name in formulas.sheetnames:
            warnings: list[str] = []
            raw_sheet = formulas[name]
            value_sheet = cached[name]
            if not isinstance(raw_sheet, Worksheet) or not isinstance(value_sheet, Worksheet):
                warnings.append(f"{name} is not a worksheet and was skipped.")
                sheets.append((name, [], warnings))
                continue
            if (raw_sheet.max_row or 0) > ROW_CAP or (raw_sheet.max_column or 0) > COL_CAP:
                warnings.append(
                    f"{name} was limited to the first {ROW_CAP} rows and {COL_CAP} columns."
                )
            formula_cells = _cell_map(raw_sheet)
            value_cells = _cell_map(value_sheet)
            sheets.append((name, _grid_from_maps(formula_cells, value_cells), warnings))
    finally:
        formulas.close()
        cached.close()
    return sheets


def _cell_map(sheet: Worksheet) -> dict[tuple[int, int], object]:
    found: dict[tuple[int, int], object] = {}
    max_row = min(sheet.max_row or 1, ROW_CAP)
    max_col = min(sheet.max_column or 1, COL_CAP)
    for row in sheet.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
        for cell in row:
            if cell.value is not None:
                found[(cell.row, cell.column)] = cell.value
    return found


def _grid_from_maps(
    formula_cells: dict[tuple[int, int], object],
    value_cells: dict[tuple[int, int], object],
) -> list[list[Cell]]:
    if not formula_cells and not value_cells:
        return []
    max_row = max(row for row, _ in (*formula_cells, *value_cells))
    max_col = max(col for _, col in (*formula_cells, *value_cells))
    grid: list[list[Cell]] = []
    for row_number in range(1, max_row + 1):
        row: list[Cell] = []
        for col_number in range(1, max_col + 1):
            raw = formula_cells.get((row_number, col_number))
            cached = value_cells.get((row_number, col_number))
            is_formula = isinstance(raw, str) and raw.startswith("=")
            if is_formula:
                value = cached
            else:
                value = cached if cached is not None else raw
            row.append(Cell(value=value, is_formula=is_formula))
        grid.append(row)
    return grid


def _read_xls(path: Path) -> list[tuple[str, list[list[Cell]], list[str]]]:
    """Read legacy .xls workbooks. This path has no separate formula flag."""

    from python_calamine import CalamineWorkbook

    workbook = CalamineWorkbook.from_path(str(path))
    sheets: list[tuple[str, list[list[Cell]], list[str]]] = []
    for name in workbook.sheet_names:
        warnings: list[str] = []
        rows = workbook.get_sheet_by_name(name).to_python(skip_empty_area=False)
        if len(rows) > ROW_CAP:
            warnings.append(f"{name} was limited to the first {ROW_CAP} rows and {COL_CAP} columns.")
            rows = rows[:ROW_CAP]
        width = min(max((len(row) for row in rows), default=0), COL_CAP)
        if any(len(row) > COL_CAP for row in rows):
            warnings.append(f"{name} was limited to the first {COL_CAP} columns.")
        grid: list[list[Cell]] = []
        for source in rows:
            padded = list(source[:width]) + [None] * max(0, width - len(source))
            grid.append([Cell(value=item) for item in padded])
        sheets.append((name, grid, warnings))
    return sheets


class _RawTable:
    def __init__(self, header_index: int, columns: list[tuple[int, str]], record_indexes: list[int], notes_start: int):
        self.header_index = header_index
        self.columns = columns
        self.record_indexes = record_indexes
        self.notes_start = notes_start


def _find_tables(sheet_name: str, grid: list[list[Cell]], header_row: int | None) -> list[_RawTable]:
    found: list[_RawTable] = []
    search = 0
    force = header_row
    while search < len(grid):
        if force is not None:
            header_index = force - 1
            force = None
            if header_index >= len(grid):
                raise AppError(f"{sheet_name} has no row {header_row}.")
            if _is_empty_row(grid[header_index]):
                raise AppError(
                    f"Row {header_row} on {sheet_name} is empty, so it cannot be the header."
                )
        else:
            header_index = _best_header(grid, search)
            if header_index is None:
                break
        columns = _columns_for(grid[header_index])
        record_indexes, next_search = _consume(grid, header_index, columns)
        notes = _notes_text(grid, search, header_index)
        if columns and (record_indexes or notes):
            found.append(_RawTable(header_index, columns, record_indexes, search))
        if next_search <= header_index:
            next_search = header_index + 1
        search = next_search
    return found


def _best_header(grid: list[list[Cell]], start: int) -> int | None:
    best_index = None
    best_score = 0.0
    for index in range(start, len(grid)):
        score = _header_score(grid, index)
        if score > best_score:
            best_score = score
            best_index = index
    if best_score > 0 and best_index is not None:
        return best_index
    # A header with nothing under it still has more labels than a title line.
    if start != 0:
        return None
    label_index = None
    label_count = 0
    for index in range(start, len(grid)):
        count = sum(1 for cell in grid[index] if _is_text_label(cell))
        if count > label_count:
            label_count = count
            label_index = index
    if label_index is not None:
        return label_index
    for index, row in enumerate(grid):
        if not _is_empty_row(row):
            return index
    return None


def _header_score(grid: list[list[Cell]], row_index: int) -> float:
    """Prefer a wide row of short labels that has values in the rows under it.

    One long title scores poorly. A merged header leaves the next row blank,
    so that single blank row is skipped before the rows underneath are counted.
    """

    row = grid[row_index]
    label_cols = [index for index, cell in enumerate(row) if _is_text_label(cell)]
    if not label_cols:
        return 0.0
    lengths = [len(_collapse(str(row[index].value))) for index in label_cols]
    if sum(lengths) / len(lengths) > 50:
        return 0.0
    data_start = row_index + 1
    if (
        data_start < len(grid)
        and _is_empty_row(grid[data_start])
        and data_start + 1 < len(grid)
        and not _is_empty_row(grid[data_start + 1])
    ):
        data_start += 1
    filled_rows = 0
    checked = 0
    ratios: list[float] = []
    for index in range(data_start, len(grid)):
        if _is_empty_row(grid[index]):
            break
        checked += 1
        hits = sum(
            1
            for column in label_cols
            if _format_value(grid[index][column].value) is not None
        )
        needed = 1 if len(label_cols) <= 2 else max(2, len(label_cols) // 5)
        if hits >= needed:
            filled_rows += 1
            ratios.append(hits / len(label_cols))
        if checked >= 8:
            break
    if filled_rows == 0:
        return 0.0
    # Density keeps a sparse title from tying a row whose columns are actually filled in.
    density = sum(ratios) / len(ratios)
    return float((len(label_cols) ** 2) * filled_rows * density)


def _consume(
    grid: list[list[Cell]], header_index: int, columns: list[tuple[int, str]]
) -> tuple[list[int], int]:
    """Collect data rows until two blank rows. One blank row stays inside the table.

    A vertical merge puts the header on one row and leaves the next row empty.
    That single empty row is the partner of the header, not a gap between tables.
    """

    row_index = header_index + 1
    if (
        row_index < len(grid)
        and _is_empty_row(grid[row_index])
        and row_index + 1 < len(grid)
        and not _is_empty_row(grid[row_index + 1])
    ):
        row_index += 1
    records: list[int] = []
    empty_run = 0
    while row_index < len(grid):
        if _is_empty_row(grid[row_index]):
            empty_run += 1
            row_index += 1
            if empty_run >= 2:
                break
            continue
        empty_run = 0
        if _row_has_values(grid[row_index], columns):
            records.append(row_index)
        row_index += 1
    return records, row_index


def _columns_for(row: list[Cell]) -> list[tuple[int, str]]:
    named: list[tuple[int, str]] = []
    for index, cell in enumerate(row):
        name = _header_name(cell, index)
        if name is not None:
            named.append((index, name))
    unique = _dedupe([name for _, name in named])
    return [(index, name) for (index, _), name in zip(named, unique)]


def _header_name(cell: Cell, column_index: int) -> str | None:
    """Name a header cell. A formula or Excel error becomes the column letter.

    The sample plan's column E is a formula pointing at a missing workbook, so
    its cached result is ``#REF!``. Another file can break a different column.
    The letter still gives that column a stable name.
    """

    letter = get_column_letter(column_index + 1)
    if cell.is_formula or _is_error(cell.value):
        return f"Column {letter}"
    if isinstance(cell.value, str) and cell.value.strip().startswith("="):
        return f"Column {letter}"
    return _format_value(cell.value)


def _notes_text(grid: list[list[Cell]], start: int, header_index: int) -> str:
    """Keep banner rows above the header. Rows of only numbers are totals, so they are left out."""

    lines: list[str] = []
    for row_index in range(start, header_index):
        row = grid[row_index]
        if not any(_is_text_label(cell) for cell in row):
            continue
        pieces = []
        for cell in row:
            if cell.is_formula and _is_error(cell.value):
                continue
            text = _format_value(cell.value)
            if text:
                pieces.append(text)
        if pieces:
            lines.append(" | ".join(pieces))
    return "\n".join(lines)


def _to_table(sheet_name: str, grid: list[list[Cell]], raw: _RawTable) -> SheetTable:
    columns = [name for _, name in raw.columns]
    records: list[dict[str, str]] = []
    excel_rows: list[int] = []
    for row_index in raw.record_indexes:
        values: dict[str, str] = {}
        for column_index, name in raw.columns:
            text = _format_value(grid[row_index][column_index].value, header=name)
            values[name] = text or ""
        records.append(values)
        excel_rows.append(row_index + 1)
    frame = pd.DataFrame(records, columns=columns)
    return SheetTable(
        sheet=sheet_name,
        header_row=raw.header_index + 1,
        columns=columns,
        notes=_notes_text(grid, raw.notes_start, raw.header_index),
        frame=frame,
        excel_rows=excel_rows,
    )


def _row_has_values(row: list[Cell], columns: list[tuple[int, str]]) -> bool:
    return any(_format_value(row[index].value, header=name) is not None for index, name in columns)


def _is_empty_row(row: list[Cell]) -> bool:
    return all(_format_value(cell.value) is None for cell in row)


def _is_text_label(cell: Cell) -> bool:
    if cell.is_formula or _is_error(cell.value) or not isinstance(cell.value, str):
        return False
    text = cell.value.strip()
    return bool(text) and not text.startswith("=")


def _is_error(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().upper() in EXCEL_ERRORS


def _format_value(value: object, header: str | None = None) -> str | None:
    """Turn a cell into the text that will be embedded and shown.

    A number under a header that contains ``%`` and that sits between 0 and 1
    is a fraction of completion (1 is 100%). Dates lose a midnight time.
    """

    if value is None or _is_error(value):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        if value.strip().startswith("="):
            return None
        text = _collapse(value)
        return text or None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if header and "%" in header and -1 <= number <= 1:
            percent = number * 100
            rendered = f"{percent:.2f}".rstrip("0").rstrip(".")
            return f"{rendered}%"
        if number.is_integer():
            return str(int(number))
        return f"{number:.4f}".rstrip("0").rstrip(".")
    text = _collapse(str(value))
    return text or None


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        if seen[name] == 1:
            unique.append(name)
        else:
            unique.append(f"{name} ({seen[name]})")
    return unique
