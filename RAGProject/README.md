# Workbook questions

A small Retrieval-Augmented Generation app. You upload an Excel file, the app finds the table on each sheet, and a question is answered from the closest rows.

The sample file in this folder is `ProjectPlan.xlsx`. The reader does not assume that file's layout. Another workbook can put its header on a different row and use different columns.

## Setup

Use Python 3.13. The virtual environment for this project lives in this folder. The `.venv` in the parent folder belongs to the other labs.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` if you do not already have one, and set `OPENROUTER_API_KEY`. Embeddings and answers both go through OpenRouter at `https://openrouter.ai/api/v1`. The requests ask OpenRouter to use the OpenAI provider, so they use the OpenAI key saved in OpenRouter's BYOK settings. The key stays in `.env` and is never written into the page.

## Run

```powershell
python app.py
```

Open http://127.0.0.1:5000. Choose an `.xlsx`, `.xlsm`, or `.xls` file. Leave **Header row** blank unless the detected header is wrong. Then ask a question.

The index is kept in memory for this process. Uploading another file replaces it. Stopping the app clears it.

## How a workbook is read

1. `.xlsx` and `.xlsm` are read with openpyxl, including the cached result of formula cells. `.xls` is read with python-calamine.
2. Each sheet is scored row by row. A header is a row of short labels with values in the rows under it. A single blank row directly under a header is treated as the other half of a merged header. Two blank rows end the table, and a later header starts another table on that sheet.
3. Text above the header is kept as notes. A row that contains only numbers is left out.
4. An empty header, a formula, or an Excel error such as `#REF!` is named from its column letter (`Column E`).
5. The detected rows are placed in a pandas DataFrame. Each data row becomes one passage: sheet, Excel row, then `header: value` for cells that have a value. Dates are written as dates. A number from 0 to 1 under a header that contains `%` is written as a percent.
6. Passages are embedded with `openai/text-embedding-3-small` and stored in an in-memory FAISS index. A question is embedded the same way. The five closest rows, the notes, and a short inventory of each table are sent to `openai/gpt-4o-mini`.

## Checks

```powershell
python -m unittest discover -s tests
```

Those tests do not call OpenRouter. They cover `ProjectPlan.xlsx`, a header on row 1, a title above a lower header, two tables separated by blank rows, a forced header row, and a broken formula header.

## Limits

- One workbook at a time, in this process.
- Files larger than 8 MB are refused.
- Each sheet is read up to 5,000 rows and 200 columns.
- Two tables side by side in the same rows are read as one table. Tables stacked with two blank rows between them are read separately.
- The model only sees the notes, the inventory, and the five closest rows. A question that needs every row, such as a total that is not already written on the sheet, can be incomplete.
