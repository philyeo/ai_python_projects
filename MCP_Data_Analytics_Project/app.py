"""
Flask application: dataset upload + natural-language chat.

The Flask app manages user interaction, stores uploaded files, keeps the
active dataset state per session, and delegates question answering to the
LangChain AI agent (which is connected to the MCP aggregator).
"""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError

from flask import Flask, jsonify, render_template, request, session
from werkzeug.utils import secure_filename

from agent.ai_agent import AIAgent
from config import prompts, settings

# ---------------------------------------------------------------------------
# Flask configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = settings.get_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

settings.ensure_directories()


def allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in settings.ALLOWED_EXTENSIONS
    )


# ---------------------------------------------------------------------------
# Persistent async event loop for the agent (thread-safe bridge to Flask)
# ---------------------------------------------------------------------------

MCP_LOOP = asyncio.new_event_loop()
LOOP_READY = threading.Event()


def start_event_loop() -> None:
    asyncio.set_event_loop(MCP_LOOP)
    LOOP_READY.set()
    MCP_LOOP.run_forever()


threading.Thread(
    target=start_event_loop,
    name="MCP-Event-Loop",
    daemon=True,
).start()

if not LOOP_READY.wait(timeout=10):
    raise RuntimeError("MCP event loop failed to start.")


AGENT = AIAgent()
AGENT_LOCK = threading.Lock()


def submit(coroutine, timeout: int = 180):
    future = asyncio.run_coroutine_threadsafe(coroutine, MCP_LOOP)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        future.cancel()
        raise TimeoutError(
            f"AI Agent request exceeded {timeout} seconds."
        )


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

def execute_agent(user_message: str, history: list | None = None) -> dict:
    with AGENT_LOCK:
        if not AGENT.is_initialized:
            submit(AGENT.initialize(), timeout=120)

        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})

        response = submit(AGENT.ainvoke(messages), timeout=180)

        final_message = response["messages"][-1]
        answer = final_message.content
        if isinstance(answer, list):
            answer = "\n".join(
                str(item.get("text", item)) if isinstance(item, dict) else str(item)
                for item in answer
            )
        answer = str(answer)

        tool_messages = []
        for message in response["messages"]:
            if getattr(message, "type", "") == "tool":
                tool_messages.append({
                    "name": getattr(message, "name", ""),
                    "content": str(message.content),
                })

        updated_history = messages + [
            {"role": "assistant", "content": answer}
        ]

        return {
            "answer": answer,
            "history": updated_history,
            "tool_messages": tool_messages,
        }


def _load_succeeded(tool_messages: list) -> bool:
    """Return True if a dataset load tool reported success."""
    for tool in tool_messages:
        name = tool.get("name", "").lower()
        if "load_dataset" not in name:
            continue
        content = tool.get("content", "")
        if isinstance(content, str):
            try:
                payload = json.loads(content)
                if isinstance(payload, dict) and payload.get("status") == "success":
                    return True
            except (ValueError, TypeError):
                pass
            if "successfully indexed" in content.lower():
                return True
    return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    try:
        uploaded_file = request.files.get("file")
        if uploaded_file is None or not uploaded_file.filename:
            return jsonify({"error": "Please select a file."}), 400

        if not allowed_file(uploaded_file.filename):
            return jsonify({"error": "Only CSV and XLSX files are supported."}), 400

        filename = secure_filename(uploaded_file.filename)
        if not filename:
            return jsonify({"error": "Invalid filename."}), 400

        file_path = settings.UPLOAD_FOLDER / filename
        uploaded_file.save(file_path)
        absolute_path = str(file_path.resolve())

        prompt = prompts.build_upload_prompt(absolute_path, filename)
        result = execute_agent(prompt)

        if not _load_succeeded(result["tool_messages"]):
            return jsonify({
                "status": "error",
                "error": "Dataset loading could not be confirmed.",
                "agent_response": result["answer"],
                "tool_execution": result["tool_messages"],
            }), 500

        session["dataset_loaded"] = True
        session["dataset_filename"] = filename
        # Preserve the upload conversation so the agent remembers the active
        # dataset (its path and columns) for subsequent questions. Resetting
        # this made the agent forget the dataset was loaded.
        session["chat_history"] = result["history"]

        return jsonify({
            "status": "success",
            "message": "Dataset loaded into Pandas and RAG servers.",
            "filename": filename,
            "file_path": absolute_path,
            "agent_response": result["answer"],
            "tool_execution": result["tool_messages"],
        })

    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/ask", methods=["POST"])
def ask_question():
    try:
        if not session.get("dataset_loaded"):
            return jsonify({"error": "Please upload a dataset first."}), 400

        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify({"error": "Please enter a question."}), 400

        history = session.get("chat_history", [])
        result = execute_agent(query, history)
        session["chat_history"] = result["history"]

        return jsonify({
            "status": "success",
            "question": query,
            "answer": result["answer"],
            "tool_execution": result["tool_messages"],
        })

    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/clear-chat", methods=["POST"])
def clear_chat():
    session["chat_history"] = []
    return jsonify({"status": "success", "message": "Chat history cleared."})


@app.route("/status", methods=["GET"])
def dataset_status():
    return jsonify({
        "dataset_loaded": session.get("dataset_loaded", False),
        "filename": session.get("dataset_filename"),
    })


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(
        host=settings.FLASK_HOST,
        port=settings.FLASK_PORT,
        debug=settings.FLASK_DEBUG,
        use_reloader=False,
    )
