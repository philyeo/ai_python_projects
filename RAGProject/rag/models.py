"""Shared records passed between reading, search, and the page."""

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Cell:
    """One spreadsheet cell.

    ``is_formula`` is true when the workbook stores a formula. The value is the
    cached result when Excel saved one, otherwise None.
    """

    value: object
    is_formula: bool = False


@dataclass
class SheetTable:
    """One detected table, already turned into a DataFrame of display text."""

    sheet: str
    header_row: int
    columns: list[str]
    notes: str
    frame: pd.DataFrame
    excel_rows: list[int]


@dataclass
class WorkbookContent:
    """Every table found in an uploaded workbook."""

    tables: list[SheetTable]
    warnings: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    """Text that can be embedded, plus the words the page shows as a source."""

    kind: str
    sheet: str
    title: str
    text: str
    display: str
    excel_row: int | None = None
    score: float | None = None
