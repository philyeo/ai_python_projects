"""Header detection has to work on the sample plan and on sheets with a different layout."""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.chunk import build_chunks  # noqa: E402
from rag.ingest import load_workbook  # noqa: E402


PLAN = ROOT / "ProjectPlan.xlsx"


class ProjectPlanTests(unittest.TestCase):
    def test_detects_the_task_table_under_the_banner(self):
        content = load_workbook(PLAN)
        self.assertEqual(len(content.tables), 1, content.warnings)
        table = content.tables[0]
        self.assertEqual(table.sheet, "DevPlan")
        self.assertEqual(table.header_row, 14, table.columns)
        self.assertEqual(list(table.excel_rows), list(range(16, 38)))
        self.assertEqual(len(table.frame), 22)
        self.assertIn("WBS Task", table.columns)
        self.assertIn("Column E", table.columns)
        self.assertNotIn("#REF!", table.columns)
        self.assertFalse(any(name.startswith("=") for name in table.columns))
        self.assertIn("SilverBank Non-Banking Extension", table.notes)
        self.assertNotIn("#REF!", table.notes)

        notes, records = build_chunks(content)
        self.assertEqual(len(notes), 1)
        by_row = {chunk.excel_row: chunk for chunk in records}
        self.assertIn("100%", by_row[16].text)
        self.assertIn("2025-07-04", by_row[16].text)
        self.assertIn("Completed", by_row[16].text)
        self.assertIn("Transaction Code (UI)", by_row[20].text)
        self.assertIn("Marwin", by_row[20].text)
        self.assertIn("5%", by_row[20].text)
        self.assertNotIn("File or Program:", by_row[20].text)


class ShiftedSheetTests(unittest.TestCase):
    def _save(self, builder) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        handle.close()
        path = Path(handle.name)
        book = Workbook()
        builder(book.active)
        book.save(path)
        book.close()
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_plain_table_uses_row_1(self):
        def fill(sheet):
            sheet["A1"] = "Fruit"
            sheet["B1"] = "Qty"
            sheet["A2"] = "Apple"
            sheet["B2"] = 3

        table = load_workbook(self._save(fill)).tables[0]
        self.assertEqual(table.header_row, 1)
        self.assertEqual(table.columns, ["Fruit", "Qty"])
        self.assertEqual(table.excel_rows, [2])
        self.assertEqual(table.notes, "")
        self.assertEqual(table.frame.iloc[0]["Fruit"], "Apple")

    def test_title_row_is_notes_and_header_is_lower(self):
        def fill(sheet):
            sheet["B2"] = "Staff list for the lab"
            sheet["A4"] = "Person"
            sheet["B4"] = "Desk"
            sheet["A5"] = "Mina"
            sheet["B5"] = "4"

        table = load_workbook(self._save(fill)).tables[0]
        self.assertEqual(table.header_row, 4)
        self.assertEqual(table.columns, ["Person", "Desk"])
        self.assertIn("Staff list for the lab", table.notes)
        self.assertEqual(table.excel_rows, [5])

    def test_two_blank_rows_start_a_second_table(self):
        def fill(sheet):
            sheet["A1"] = "Name"
            sheet["B1"] = "Age"
            sheet["A2"] = "Ada"
            sheet["B2"] = 36
            sheet["A5"] = "City"
            sheet["B5"] = "Country"
            sheet["A6"] = "Paris"
            sheet["B6"] = "France"

        tables = load_workbook(self._save(fill)).tables
        self.assertEqual([table.header_row for table in tables], [1, 5])
        self.assertEqual(tables[0].excel_rows, [2])
        self.assertEqual(tables[1].frame.iloc[0]["City"], "Paris")

    def test_forced_header_row_overrides_detection(self):
        def fill(sheet):
            sheet["A1"] = "Ignore me title"
            sheet["A2"] = "Name"
            sheet["B2"] = "City"
            sheet["A3"] = "Ada"
            sheet["B3"] = "Oslo"

        path = self._save(fill)
        detected = load_workbook(path).tables[0]
        self.assertEqual(detected.header_row, 2)
        forced = load_workbook(path, header_row=1).tables[0]
        self.assertEqual(forced.header_row, 1)
        self.assertEqual(forced.columns[0], "Ignore me title")

    def test_formula_header_uses_the_column_letter(self):
        def fill(sheet):
            sheet["A1"] = "Name"
            sheet["B1"] = "='[1]1.Config'!L2"
            sheet["A2"] = "Ada"
            sheet["B2"] = "North"

        table = load_workbook(self._save(fill)).tables[0]
        self.assertEqual(table.columns, ["Name", "Column B"])
        self.assertEqual(table.frame.iloc[0]["Column B"], "North")

    def test_percent_and_date_formatting(self):
        def fill(sheet):
            sheet["A1"] = "Item"
            sheet["B1"] = "Completion %"
            sheet["C1"] = "When"
            sheet["A2"] = "Tax UI"
            sheet["B2"] = 0.05
            sheet["C2"] = datetime(2025, 7, 11)

        text = build_chunks(load_workbook(self._save(fill)))[1][0].text
        self.assertIn("Completion %: 5%", text)
        self.assertIn("When: 2025-07-11", text)

    def test_numeric_banner_rows_are_not_records(self):
        def fill(sheet):
            sheet["A1"] = "Queue"
            sheet["C1"] = "Morning batch"
            sheet["A2"] = 4
            sheet["B2"] = 9
            sheet["A4"] = "Ticket"
            sheet["B4"] = "Owner"
            sheet["A5"] = "T-1"
            sheet["B5"] = "Jo"

        table = load_workbook(self._save(fill)).tables[0]
        self.assertEqual(table.header_row, 4)
        self.assertEqual(table.excel_rows, [5])
        self.assertIn("Morning batch", table.notes)
        self.assertNotIn("4", table.notes)


if __name__ == "__main__":
    unittest.main()
