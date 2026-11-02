"""The page is a plain form. It does not reuse the earlier lab screens."""

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as web  # noqa: E402


class PageTests(unittest.TestCase):
    def setUp(self):
        web.STATE.loaded = None
        web.STATE.question = ""
        web.STATE.answer = ""
        web.STATE.sources = []
        self.client = web.app.test_client()

    def test_home_is_a_workbook_form(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Excel file", page)
        self.assertIn("Header row", page)
        self.assertIn('type="file"', page)
        self.assertNotIn("TrueRAG", page)
        self.assertNotIn("PseudoRAG", page)
        self.assertNotIn("<script", page.lower())
        css = (ROOT / "static" / "site.css").read_text(encoding="utf-8")
        self.assertIn("#f4efe4", css)
        self.assertNotIn("#6c5ce7", css)
        self.assertNotIn("#0f172a", css)
        self.assertNotIn("#0f1117", css)

    def test_ask_before_upload(self):
        page = self.client.post("/ask", data={"question": "How many rows?"}).get_data(as_text=True)
        self.assertIn("Upload a workbook", page)

    def test_upload_without_a_file(self):
        page = self.client.post("/upload", data={"header_row": ""}).get_data(as_text=True)
        self.assertIn("Choose an Excel file", page)

    def test_rejects_a_text_file(self):
        page = self.client.post(
            "/upload",
            data={"file": (io.BytesIO(b"hello"), "notes.txt")},
            content_type="multipart/form-data",
        ).get_data(as_text=True)
        self.assertIn(".xlsx", page)

    def test_damaged_xlsx_stays_on_the_page(self):
        response = self.client.post(
            "/upload",
            data={"file": (io.BytesIO(b"this is not a workbook"), "bad.xlsx")},
            content_type="multipart/form-data",
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Traceback", page)
        self.assertIn("could not be opened", page)


if __name__ == "__main__":
    unittest.main()
