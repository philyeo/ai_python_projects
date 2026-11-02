// Frontend logic for the MCP Data Analytics AI Agent.

const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");
const uploadStatus = document.getElementById("upload-status");
const datasetInfo = document.getElementById("dataset-info");
const datasetName = document.getElementById("dataset-name");
const datasetDetails = document.getElementById("dataset-details");

const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const chatLog = document.getElementById("chat-log");
const clearBtn = document.getElementById("clear-btn");
const toolTrace = document.getElementById("tool-trace");
const toolTraceContent = document.getElementById("tool-trace-content");

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = "message " + role;
  div.textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function showToolTrace(toolExecution) {
  if (!toolExecution || toolExecution.length === 0) {
    toolTrace.classList.add("hidden");
    return;
  }
  toolTrace.classList.remove("hidden");
  toolTraceContent.textContent = JSON.stringify(toolExecution, null, 2);
}

async function refreshStatus() {
  try {
    const res = await fetch("/status");
    const data = await res.json();
    if (data.dataset_loaded) {
      datasetInfo.classList.remove("hidden");
      datasetName.textContent = data.filename;
    }
  } catch (e) {
    // ignore
  }
}

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) {
    setStatus(uploadStatus, "Please select a file.", "error");
    return;
  }

  uploadBtn.disabled = true;
  setStatus(uploadStatus, "Uploading and loading dataset…");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      setStatus(uploadStatus, data.error || "Upload failed.", "error");
      return;
    }

    setStatus(uploadStatus, "Dataset loaded successfully.", "success");
    datasetInfo.classList.remove("hidden");
    datasetName.textContent = data.filename;

    const details = data.agent_response || data.message || "";
    datasetDetails.textContent = details;

    chatLog.innerHTML = "";
    addMessage("Dataset loaded. Ask me a question about it!", "assistant");
  } catch (err) {
    setStatus(uploadStatus, "Upload failed: " + err.message, "error");
  } finally {
    uploadBtn.disabled = false;
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = chatInput.value.trim();
  if (!query) return;

  addMessage(query, "user");
  chatInput.value = "";
  sendBtn.disabled = true;

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();

    if (!res.ok) {
      addMessage(data.error || "Request failed.", "error");
      showToolTrace(data.tool_execution);
      return;
    }

    addMessage(data.answer || "(no answer)", "assistant");
    showToolTrace(data.tool_execution);
  } catch (err) {
    addMessage("Request failed: " + err.message, "error");
  } finally {
    sendBtn.disabled = false;
  }
});

clearBtn.addEventListener("click", async () => {
  try {
    await fetch("/clear-chat", { method: "POST" });
    chatLog.innerHTML = "";
    toolTrace.classList.add("hidden");
  } catch (err) {
    // ignore
  }
});

refreshStatus();
