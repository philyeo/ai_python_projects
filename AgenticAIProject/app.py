
# ============================================================
# FLASK MAIN APPLICATION
# FLASK + LANGCHAIN AI AGENT + MCP AGGREGATOR
# RAG + OPENSTREETMAP + OPENWEATHER
# ============================================================

import os
import asyncio
import threading

from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    session
)

from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from langchain.mcp import MCPAdapter
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = Path(__file__).resolve().parent
# Load .env from AgenticAI folder
load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is missing from your .env file."
    )

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

UPLOAD_FOLDER = PROJECT_DIR / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"csv", "xlsx"}

MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL",
)


# ============================================================
# 2. OPENROUTER LLM
# ============================================================

client = ChatOpenAI(
    model=os.getenv(
        "MODEL",
    ),
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0
)


# ============================================================
# 3. SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an intelligent AI agent connected to a Main MCP Aggregator.

The aggregator provides three MCP services:

1. RAG MCP
   - rag_load_dataset
   - rag_search_dataset
   - rag_get_dataset_info

2. OpenStreetMap MCP
   - Location and geographical search tools.

3. OpenWeather MCP
   - Weather information tools.

YOUR RESPONSIBILITIES:

A. DATASET MANAGEMENT

When a user uploads a dataset:
- Use rag_load_dataset to index the uploaded file.
- Do not claim success if indexing fails.

B. DATASET QUESTIONS

- Use rag_search_dataset to retrieve relevant information.
- Use rag_get_dataset_info when metadata is required.
- Answer using retrieved dataset information.
- Do not invent missing values.

C. LOCATION QUESTIONS

- Search the dataset first.
- Identify relevant locations.
- Use OpenStreetMap when geographical information is required.

D. WEATHER QUESTIONS

When the user asks about weather related to a person
or location in the dataset:

1. Search the dataset.
2. Identify the relevant location.
3. Use OpenStreetMap if geocoding is required.
4. Use OpenWeather to retrieve weather information.
5. Combine the results into one answer.

Example:
User: Give me the weather for Liam.

Workflow:
- Search the dataset for Liam.
- Identify Liam's location.
- Resolve the location if necessary.
- Retrieve weather information.
- Present the result clearly.

E. GENERAL RULES

- Select appropriate tools.
- Do not call unnecessary tools.
- Do not repeat tool calls without a reason.
- Clearly distinguish dataset information from external data.
- Never fabricate tool results.
"""


# ============================================================
# 4. PERSISTENT ASYNC EVENT LOOP
# ============================================================

MCP_LOOP = asyncio.new_event_loop()

LOOP_READY = threading.Event()


def start_event_loop():

    asyncio.set_event_loop(MCP_LOOP)

    LOOP_READY.set()

    MCP_LOOP.run_forever()


MCP_THREAD = threading.Thread(
    target=start_event_loop,
    name="MCP-Event-Loop",
    daemon=True
)

MCP_THREAD.start()

if not LOOP_READY.wait(timeout=10):
    raise RuntimeError("MCP event loop failed to start.")


# ============================================================
# 5. GLOBAL MCP AGENT OBJECTS
# ============================================================

MCP_ADAPTER = None
AI_AGENT = None

# Prevent simultaneous agent initialization/invocation
AGENT_LOCK = threading.Lock()


# ============================================================
# 6. INITIALIZE MCP CONNECTION ONCE
# ============================================================

async def initialize_agent():
    global MCP_ADAPTER
    global AI_AGENT

    if AI_AGENT is not None:
        return

    print("\n====================================")
    print("CONNECTING TO MCP AGGREGATOR")
    print("====================================")

    adapter = MCPAdapter(MCP_SERVER_URL)

    await adapter.__aenter__()

    tools = await adapter.list_tools()

    print("\nAVAILABLE MCP TOOLS")

    for tool in tools:
        print("-", tool.name)

    agent = create_agent(
        model=client,
        tools=tools,
        system_prompt=SYSTEM_PROMPT
    )

    MCP_ADAPTER = adapter
    AI_AGENT = agent

    print("\nAI AGENT READY")


# ============================================================
# 7. RUN COROUTINE ON PERSISTENT LOOP
# ============================================================

def submit_coroutine(coroutine, timeout=180):

    future = asyncio.run_coroutine_threadsafe(
        coroutine,
        MCP_LOOP
    )

    try:

        return future.result(timeout=timeout)

    except FutureTimeoutError:

        future.cancel()

        raise TimeoutError(
            f"AI Agent request exceeded {timeout} seconds."
        )


# ============================================================
# 8. EXECUTE AI AGENT
# ============================================================

def execute_agent(user_message, history=None):

    global AI_AGENT

    with AGENT_LOCK:

        # Initialize MCP only once
        if AI_AGENT is None:

            submit_coroutine(
                initialize_agent(),
                timeout=120
            )

        # Preserve previous conversation
        messages = list(history or [])

        messages.append({
            "role": "user",
            "content": user_message
        })

        print("\n====================================")
        print("EXECUTING AI AGENT")
        print("====================================")

        response = submit_coroutine(
            AI_AGENT.ainvoke({
                "messages": messages
            }),
            timeout=180
        )

        final_message = response["messages"][-1]

        answer = final_message.content

        if isinstance(answer, list):

            answer = "\n".join(
                str(item.get("text", item))
                if isinstance(item, dict)
                else str(item)
                for item in answer
            )

        answer = str(answer)

        # Extract tool execution information
        tool_messages = []

        for message in response["messages"]:

            if getattr(message, "type", "") == "tool":

                tool_messages.append({
                    "name": getattr(message, "name", ""),
                    "content": str(message.content)
                })

        updated_history = messages + [{
            "role": "assistant",
            "content": answer
        }]

        return {
            "answer": answer,
            "history": updated_history,
            "tool_messages": tool_messages
        }


# ============================================================
# 9. CHECK DATASET INDEXING RESULT
# ============================================================

def dataset_indexing_succeeded(tool_messages):

    for tool in tool_messages:

        tool_name = tool.get("name", "").lower()

        if "load_dataset" not in tool_name:
            continue

        content = tool.get("content", "")

        # MCP tool results may contain JSON
        if isinstance(content, str):

            try:

                import json

                result = json.loads(content)

                if isinstance(result, dict):
                    if result.get("status") == "success":
                        return True

            except (ValueError, TypeError):
                pass

            if "dataset successfully indexed" in content.lower():
                return True

    return False


# ============================================================
# 10. FILE VALIDATION
# ============================================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# 11. HOME PAGE
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# 12. UPLOAD DATASET
# ============================================================

@app.route("/upload", methods=["POST"])
def upload_file():

    try:

        uploaded_file = request.files.get("file")

        if uploaded_file is None or not uploaded_file.filename:

            return jsonify({
                "error": "Please select a file."
            }), 400

        if not allowed_file(uploaded_file.filename):

            return jsonify({
                "error": "Only CSV and XLSX files are supported."
            }), 400

        filename = secure_filename(
            uploaded_file.filename
        )

        if not filename:

            return jsonify({
                "error": "Invalid filename."
            }), 400

        file_path = UPLOAD_FOLDER / filename

        uploaded_file.save(file_path)

        absolute_path = str(
            file_path.resolve()
        )

        print("\n====================================")
        print("FILE UPLOADED")
        print("====================================")

        print("Filename:", filename)
        print("Path:", absolute_path)

        prompt = f"""
A user has uploaded a new dataset.

You MUST call the rag_load_dataset tool.

Load this exact file:

{absolute_path}

After loading, report:
1. Filename
2. Number of rows
3. Dataset columns
4. Whether indexing succeeded.

Do not claim success if the tool fails.
"""

        result = execute_agent(prompt)

        # Confirm the actual indexing tool result
        success = dataset_indexing_succeeded(
            result["tool_messages"]
        )

        if not success:

            return jsonify({
                "status": "error",
                "error": "RAG indexing could not be confirmed.",
                "agent_response": result["answer"],
                "tool_execution": result["tool_messages"]
            }), 500

        # Update session only after successful indexing
        session["dataset_loaded"] = True
        session["dataset_filename"] = filename
        session["chat_history"] = []

        return jsonify({

            "status": "success",

            "message": "Dataset successfully indexed.",

            "filename": filename,

            "file_path": absolute_path,

            "agent_response": result["answer"],

            "tool_execution": result["tool_messages"]

        })

    except Exception as e:

        print("UPLOAD ERROR:", str(e))

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# 13. ASK AI AGENT
# ============================================================

@app.route("/ask", methods=["POST"])
def ask_question():

    try:

        if not session.get("dataset_loaded"):

            return jsonify({
                "error": "Please upload a dataset first."
            }), 400

        data = request.get_json(silent=True) or {}

        query = data.get(
            "query",
            ""
        ).strip()

        if not query:

            return jsonify({
                "error": "Please enter a question."
            }), 400

        history = session.get(
            "chat_history",
            []
        )

        result = execute_agent(
            query,
            history
        )

        session["chat_history"] = result["history"]

        return jsonify({

            "status": "success",

            "question": query,

            "answer": result["answer"],

            "tool_execution": result["tool_messages"]

        })

    except Exception as e:

        print("AGENT ERROR:", str(e))

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# 14. CLEAR CHAT HISTORY
# ============================================================

@app.route("/clear-chat", methods=["POST"])
def clear_chat():

    session["chat_history"] = []

    return jsonify({
        "status": "success",
        "message": "Chat history cleared."
    })


# ============================================================
# 15. DATASET STATUS
# ============================================================

@app.route("/status", methods=["GET"])
def dataset_status():

    return jsonify({

        "dataset_loaded": session.get(
            "dataset_loaded",
            False
        ),

        "filename": session.get(
            "dataset_filename",
            None
        )

    })


# ============================================================
# 16. RUN FLASK
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=False
    )
