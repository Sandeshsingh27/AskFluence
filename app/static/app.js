const els = {
  authHint: document.getElementById("authHint"),
  apiKey: document.getElementById("apiKey"),
  spaceKey: document.getElementById("spaceKey"),
  timeoutSec: document.getElementById("timeoutSec"),
  question: document.getElementById("question"),
  askBtn: document.getElementById("askBtn"),
  clearBtn: document.getElementById("clearBtn"),
  status: document.getElementById("status"),
  answer: document.getElementById("answer"),
  citations: document.getElementById("citations"),
  elapsed: document.getElementById("elapsed"),
  citationTemplate: document.getElementById("citationTemplate"),
};

let authRequired = false;

function setStatus(message, tone = "") {
  els.status.textContent = message;
  els.status.className = "status";
  if (tone) {
    els.status.classList.add(tone);
  }
}

function setBusy(isBusy) {
  els.askBtn.disabled = isBusy;
  els.askBtn.textContent = isBusy ? "Asking..." : "Ask";
}

function clearCitations() {
  els.citations.innerHTML = "";
}

function renderCitations(citations) {
  clearCitations();
  if (!citations || citations.length === 0) {
    const li = document.createElement("li");
    li.className = "citation-item";
    li.textContent = "No citations were returned.";
    els.citations.appendChild(li);
    return;
  }

  for (const c of citations) {
    const node = els.citationTemplate.content.cloneNode(true);
    const link = node.querySelector(".citation-link");
    const meta = node.querySelector(".citation-meta");
    link.textContent = c.title || c.url || "Untitled source";
    link.href = c.url || "#";
    const score = Number.isFinite(c.score) ? ` | score ${c.score.toFixed(3)}` : "";
    meta.textContent = `${c.page_id || "unknown page"}${score}`;
    els.citations.appendChild(node);
  }
}

function askPayload() {
  const question = els.question.value.trim();
  const spaceRaw = els.spaceKey.value.trim();
  const spaces = spaceRaw ? [spaceRaw] : [];
  return {
    question,
    filters: { spaces },
  };
}

async function loadUiConfig() {
  try {
    const res = await fetch("/ui-config");
    if (!res.ok) {
      throw new Error("Config unavailable");
    }
    const data = await res.json();
    authRequired = Boolean(data.auth_required);
    els.apiKey.disabled = !authRequired;
    els.authHint.className = "auth-hint";

    if (authRequired) {
      els.apiKey.placeholder = "Required when AUTH_REQUIRED=true";
      els.authHint.textContent = "Server auth is enabled. Enter API key to send requests.";
      els.authHint.classList.add("warn");
    } else {
      els.apiKey.value = "";
      els.apiKey.placeholder = "Not required in this environment";
      els.authHint.textContent = "Auth is disabled for this environment. API key field is disabled.";
    }
  } catch {
    els.authHint.textContent = "Could not load server config.";
    els.authHint.classList.add("warn");
  }
}

async function runAsk() {
  const apiKey = els.apiKey.value.trim();
  const payload = askPayload();

  if (authRequired && !apiKey) {
    setStatus("Enter API key first.", "warn");
    return;
  }
  if (!payload.question) {
    setStatus("Enter a question first.", "warn");
    return;
  }

  const timeoutSeconds = Number(els.timeoutSec.value || 90);
  const timeoutMs = Math.max(10, Math.min(timeoutSeconds, 180)) * 1000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  setBusy(true);
  setStatus("Sending request...");
  const start = performance.now();

  try {
    const headers = {
      "Content-Type": "application/json",
    };
    if (authRequired) {
      headers.Authorization = `Bearer ${apiKey}`;
    }

    const response = await fetch("/ask", {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      const detail = err?.detail || `HTTP ${response.status}`;
      throw new Error(detail);
    }

    const data = await response.json();
    els.answer.classList.remove("empty");
    els.answer.textContent = data.answer || "No answer returned.";
    renderCitations(data.citations || []);

    const elapsed = (performance.now() - start) / 1000;
    els.elapsed.textContent = `${elapsed.toFixed(1)}s`;
    setStatus("Done.");
  } catch (err) {
    els.answer.classList.remove("empty");
    els.answer.textContent = "Request failed.";
    clearCitations();
    if (err.name === "AbortError") {
      setStatus("Request timed out. Try a shorter query or retry later.", "warn");
    } else {
      setStatus(String(err.message || err), "error");
    }
  } finally {
    clearTimeout(timer);
    setBusy(false);
  }
}

function clearView() {
  els.question.value = "";
  els.answer.classList.add("empty");
  els.answer.textContent = "Your answer will appear here.";
  els.elapsed.textContent = "";
  clearCitations();
  setStatus("Cleared.");
}

els.askBtn.addEventListener("click", runAsk);
els.clearBtn.addEventListener("click", clearView);
els.question.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    runAsk();
  }
});

loadUiConfig();
setStatus("Ready.");
