# MCP-Based Data Analytics AI Agent

An AI-powered data analytics application built on the **Model Context Protocol
(MCP)**. Users upload a CSV/Excel dataset and ask natural-language questions;
a LangChain-powered LLM agent answers by selecting and combining tools from
three MCP servers exposed through a single aggregator:

- **Pandas MCP** (STDIO) — exact structured calculations
- **RAG MCP** (STDIO) — semantic retrieval over the uploaded dataset
- **Web Search MCP** (Streamable HTTP, Tavily) — external internet search

---

## 1. Architecture

```
Flask Web Application (upload + chat)
        |
LangChain AI Agent (LLM reasoning + tool selection)
        |
MCP Aggregator  http://127.0.0.1:8000/mcp  (Streamable HTTP)
        |
+----------------+----------------+------------------+
|   Pandas MCP   |     RAG MCP    |  Web Search MCP  |
|     STDIO      |     STDIO      |  Streamable HTTP |
|  custom local  |  local subproc |  Tavily (remote) |
+----------------+----------------+------------------+
```

Tool names are namespaced by server name, so the agent sees:

| Prefix      | Tools                                                                 |
|-------------|-----------------------------------------------------------------------|
| `pandas_*`  | `load_dataset`, `get_dataset_info`, `get_column_summary`, `aggregate_data`, `groupby_data`, `filter_dataset` |
| `rag_*`     | `load_dataset`, `search_dataset`, `get_dataset_info`                  |
| `tavily_*`  | `search`, `extract` (+ `crawl`, `map`, `research` with an API key)    |

---

## 2. Technologies

- Python, Flask, Pandas, NumPy, OpenPyXL
- FastMCP (MCP servers + aggregator)
- Model Context Protocol (STDIO + Streamable HTTP transports)
- LangChain (`langchain.mcp.MCPAdapter`, `langchain.agents.create_agent`)
- OpenRouter-compatible OpenAI API (`langchain_openai.ChatOpenAI`)
- FAISS + Sentence Transformers (RAG)
- Tavily Web Search MCP — keyless by default (https://docs.tavily.com/documentation/keyless)

---

## 3. Folder structure

```
MCP_Data_Analytics_Project/
|-- app.py                 # Flask application
|-- requirements.txt
|-- .env / .env.example    # configuration (never commit .env)
|-- .gitignore
|-- README.md
|-- config/
|   |-- settings.py        # paths + environment settings
|   |-- prompts.py         # system prompt + upload prompt
|-- data/                  # titanic.csv, ProjectPlan.xlsx
|-- uploads/               # user uploads (gitignored)
|-- pandas_mcp/
|   |-- analytics.py       # pure, reusable Pandas functions
|   |-- pandas_server.py   # FastMCP STDIO server (tool registration)
|-- rag_mcp/
|   |-- embeddings.py      # Sentence Transformers wrapper
|   |-- vector_store.py    # FAISS persistence
|   |-- rag_server.py      # FastMCP STDIO server
|-- web_search_mcp/
|   |-- web_search_config.py  # Tavily MCP connection config
|-- aggregator/
|   |-- aggregator_server.py  # combines the three servers (HTTP)
|-- agent/
|   |-- mcp_client.py      # MCPAdapter connection
|   |-- ai_agent.py        # LLM + tool-calling workflow
|-- templates/ static/     # Flask UI
|-- logs/                  # runtime logs + active-dataset state
```

---

## 4. Features

**Pandas MCP** — dataset information, descriptive statistics, aggregation,
GroupBy (single or multiple columns), and validated filtering. Column names,
aggregation functions and filter operators are validated; no arbitrary code or
SQL is ever executed.

**RAG MCP** — indexes each row of the uploaded dataset as a text chunk and
performs FAISS-based semantic search.

**Web Search MCP** — Tavily's remote MCP provides `search` and `extract` via
keyless access by default; setting a `TAVILY_API_KEY` adds `crawl`, `map` and
`research`.

**AI agent** — interprets questions, selects the right tools, can call multiple
tools in one answer, and combines results while labelling their source.


## 5. Installation

1. Copy or clone the project.
2. Create and activate a Python virtual environment (Python 3.11+).
3. `pip install -r requirements.txt`
4. `copy .env.example .env` and fill in your credentials:
   - `OPENROUTER_API_KEY` — required for the LLM.
   - `MODEL` — any OpenRouter model id (default `openai/gpt-4o-mini`).
   - `TAVILY_API_KEY` — optional. Leave blank to use keyless access (Search +
     Extract, rate-limited); set a key to unlock all tools and higher limits.
5. Place sample datasets in `data/` (Titanic CSV and `ProjectPlan.xlsx` are
   already included).

---

## 6. Running

Run these in **separate terminals**:

```bash
# 1. Start the MCP aggregator (combines Pandas + RAG + Tavily)
python aggregator/aggregator_server.py

# 2. Start the Flask app
python app.py
```

Then open **http://127.0.0.1:5000**, upload a dataset, and ask questions.

> The aggregator must be running and reachable at `AGGREGATOR_URL` (default
> `http://127.0.0.1:8000/mcp`) before the Flask agent is initialized.

You can also test each MCP server independently:

```bash
# Pandas MCP server (STDIO) — inspect tools with an MCP client/inspector
python pandas_mcp/pandas_server.py

# RAG MCP server (STDIO)
python rag_mcp/rag_server.py
```

---

## 7. Testing

A standalone smoke test for the analytics layer is included:

```bash
python tests/test_analytics.py
```

### Titanic exercises (verified against the included `data/titanic.csv`)

| Question | Expected tool |
|---|---|
| How many passengers are in the dataset? | `pandas_get_dataset_info` / `aggregate_data(count)` |
| What is the average passenger age? | `pandas_get_column_summary(age)` / `aggregate_data(age, mean)` |
| Average fare for each passenger class? | `pandas_groupby_data(pclass, mean, fare)` |
| Survival rate by sex? | `pandas_groupby_data(sex, mean, survived)` |
| Number of survivors and non-survivors? | `pandas_groupby_data(survived, count)` |
| Which class had the highest survival rate? | `pandas_groupby_data(pclass, mean, survived)` |
| Filter passengers older than 50 who survived | `pandas_filter_dataset` |

### SilverBank ProjectPlan exercises (verified against `data/ProjectPlan.xlsx`)

| Question | Expected tool |
|---|---|
| How many tasks are in the project plan? | `pandas_aggregate_data("", count)` |
| Tasks completed / pending / in progress? | `pandas_groupby_data(Status, count)` |
| Tasks assigned to each developer? | `pandas_groupby_data(Assigned To, count)` |
| Which module has the most tasks? | `pandas_groupby_data(Module, count)` |
| Average completion % by module? | `pandas_groupby_data(Module, mean, Completion %)` |
| Which tasks are unassigned? | `pandas_filter_dataset` (`Assigned To isnull`) |
| Financial vs Non-Financial tasks? | `pandas_groupby_data(Financial / Non-Financial, count)` |
| Tasks marked overdue? | `pandas_filter_dataset` |
| Total estimated mandays by module? | `pandas_groupby_data(Module, sum, Target Manday)` |

---

## 8. Data handling notes

- **Header detection** — `ProjectPlan.xlsx` contains title rows above the real
  header. The Pandas and RAG loaders auto-detect the header row. The workbook's
  broken `#REF!` column (which holds construct types such as "UI Generator" and
  "API Service Program") is recovered as `ConstructType`.
- **Blank / missing values** — blanks are treated as missing (NaN), never as
  zero. Numeric aggregations exclude missing values. The agent is instructed to
  report missing values rather than assuming zero.
- **Completion %** — the workbook stores completion as a mix of decimals (e.g.
  `0.05`) and whole numbers (e.g. `1`). The tools return the raw values; the
  agent should state the interpretation.
- **Project filter** — the workbook contains multiple projects. The supplied
  `ProjectPlan.xlsx` has the **SilverBank Non-Banking Extension** data in its
  `DevPlan` sheet (the rows below the second title block). Review the data and
  confirm the intended project rows before analysing a new workbook.

---

## 9. Security

- Keep credentials in `.env`; never commit it.
- Validate uploaded file extensions and size.
- MCP dataset-load tools only accept paths inside `uploads/` or `data/`.
- No arbitrary code/SQL execution from LLM-supplied strings.
- Protect the Flask server and MCP endpoint before any public deployment.
- Anonymise developer names and internal project information before sharing a
  project workbook.

