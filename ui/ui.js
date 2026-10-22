// ui/ui.js — vanilla JS, no build step (matches phonexa's plain HTML/JS
// pattern). The shared bearer token (D-S6) is pasted once and kept in
// localStorage; this is an operator tool, not an end-user page.

const TOKEN_KEY = "smia_ui_token";

// One ready-to-send example body per kind, prefilled into the try-it form
// whenever the kind selector changes. /stt gets its own audio-upload/
// recording UI instead (see tryBodyAudio in index.html) — its request body
// is multipart audio, not JSON.
const EXAMPLE_BODIES = {
  inflections: { word: "hus", lang: "nb" },
  ipa: { text: "hus", lang: "nb" },
  tts: { text: "hus", lang: "nb" },
  translations: { text: "hus", from: "nb", to: "en" },
};

// The in-browser MediaRecorder result, when the operator records instead
// of uploading a file — takes priority over the file input on submit.
let recordedAudioBlob = null;
let mediaRecorder = null;

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` };
}

async function refreshAll() {
  const [providersResp, healthResp] = await Promise.all([
    fetch("/providers", { headers: authHeaders() }),
    fetch("/health", { headers: authHeaders() }),
  ]);
  const providers = await providersResp.json();
  const healthRows = await healthResp.json();

  // A bad/expired token (or any other non-2xx) returns {"error": "..."},
  // not the {kind: [provider, ...]} shape renderCatalog/health expect —
  // rendering that unchecked throws (names.join on a string) and takes
  // down the rest of refreshAll with it, including the try-it form's
  // provider list. Surface it plainly instead.
  if (!providersResp.ok || !healthResp.ok) {
    document.getElementById("catalog").innerHTML =
      `<tr><td colspan="2" class="bad">${providers.error || healthRows.error || "request failed"} — check the bearer token above</td></tr>`;
    document.getElementById("health").innerHTML = "";
    return;
  }

  renderCatalog(providers);
  renderHealth(healthRows);
  populateTryItSelectors(providers);
}

function renderCatalog(providers) {
  const el = document.getElementById("catalog");
  el.innerHTML = Object.entries(providers)
    .map(([kind, names]) => `<tr><td>${kind}</td><td>${names.join(", ") || "<span class=muted>none configured</span>"}</td></tr>`)
    .join("");
}

function renderHealth(rows) {
  const el = document.getElementById("health");
  if (!rows.length) {
    el.innerHTML = `<tr><td colspan="6" class="muted">No requests yet</td></tr>`;
    return;
  }
  el.innerHTML = rows
    .map((r) => {
      const total = r.requestsCount || 1;
      const hitRate = ((r.hitCount / total) * 100).toFixed(0);
      const lastFail = r.lastFailureAt
        ? `<span class="bad" title="${r.lastFailureMessage || ""}">${r.lastFailureAt}</span>`
        : `<span class="muted">—</span>`;
      return `<tr>
        <td>${r.kind}</td><td>${r.provider}</td>
        <td>${r.requestsCount}</td><td>${hitRate}% (${r.hitCount}/${r.requestsCount})</td>
        <td class="ok">${r.lastSuccessAt || "—"}</td>
        <td>${lastFail}</td>
      </tr>`;
    })
    .join("");
}

// Rebuilds the kind/provider <option> lists from the current catalog
// without losing whatever the operator already had selected — refreshAll()
// runs after every try-it submission, and resetting the selectors each
// time made every submission feel like it forgot what you'd just picked.
function populateTryItSelectors(providers) {
  const kindSel = document.getElementById("tryKind");
  const prevKind = kindSel.value;
  const firstLoad = !kindSel.dataset.initialized;
  kindSel.dataset.initialized = "1";

  const kinds = Object.keys(providers);
  kindSel.innerHTML = kinds.map((k) => `<option value="${k}">${k}</option>`).join("");
  if (kinds.includes(prevKind)) kindSel.value = prevKind;

  updateProviderSelector(providers);
  kindSel.onchange = () => {
    updateProviderSelector(providers);
    prefillBody(kindSel.value);
  };

  if (firstLoad) prefillBody(kindSel.value);
}

function updateProviderSelector(providers) {
  const kind = document.getElementById("tryKind").value;
  const provSel = document.getElementById("tryProvider");
  const prevProvider = provSel.value;
  const available = providers[kind] || [];
  provSel.innerHTML = available.map((p) => `<option value="${p}">${p}</option>`).join("");
  if (available.includes(prevProvider)) provSel.value = prevProvider;
}

function prefillBody(kind) {
  const isAudio = kind === "stt";
  document.getElementById("tryBodyJson").style.display = isAudio ? "none" : "block";
  document.getElementById("tryBodyAudio").style.display = isAudio ? "block" : "none";
  if (!isAudio) {
    document.getElementById("tryBody").value = JSON.stringify(EXAMPLE_BODIES[kind] || {}, null, 2);
  }
}

// ── /stt: file upload or in-browser microphone recording ────────────────

async function toggleRecording() {
  const btn = document.getElementById("tryRecordBtn");
  const status = document.getElementById("tryRecordStatus");

  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    status.textContent = `Microphone access failed: ${e.message}`;
    return;
  }

  const chunks = [];
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    recordedAudioBlob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
    document.getElementById("tryAudioFile").value = ""; // recording takes priority
    const preview = document.getElementById("tryAudioPreview");
    preview.src = URL.createObjectURL(recordedAudioBlob);
    preview.style.display = "block";
    btn.textContent = "● Record from microphone";
    btn.classList.remove("recording");
    status.textContent = "Recorded — ready to send";
  };

  mediaRecorder.start();
  btn.textContent = "■ Stop recording";
  btn.classList.add("recording");
  status.textContent = "Recording…";
}

document.getElementById("tryAudioFile")?.addEventListener("change", (e) => {
  recordedAudioBlob = null; // an explicit file pick overrides any earlier recording
  const file = e.target.files[0];
  if (!file) return;
  const preview = document.getElementById("tryAudioPreview");
  preview.src = URL.createObjectURL(file);
  preview.style.display = "block";
  document.getElementById("tryRecordStatus").textContent = "";
});

// ── /tts: fetch and play each candidate's audio inline ───────────────────

async function renderAudioPlayers(data) {
  const container = document.getElementById("tryAudioPlayers");
  container.innerHTML = "";
  const candidates = (data.candidates || []).filter((c) => c.sha256);
  for (const candidate of candidates) {
    const resp = await fetch(`/tts/${candidate.sha256}`, { headers: authHeaders() });
    if (!resp.ok) continue;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const label = ["source", "voice", "variety"]
      .filter((k) => candidate[k])
      .map((k) => `${k}: ${candidate[k]}`)
      .join(" · ") || candidate.sha256.slice(0, 12);
    const wrapper = document.createElement("div");
    wrapper.className = "audio-candidate";
    wrapper.innerHTML = `<div class="audio-label">${label}</div>`;
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = url;
    wrapper.appendChild(audio);
    container.appendChild(wrapper);
  }
}

async function submitTryIt(event) {
  event.preventDefault();
  const kind = document.getElementById("tryKind").value;
  const provider = document.getElementById("tryProvider").value;
  const forceRefresh = document.getElementById("tryForceRefresh").checked;
  const resultEl = document.getElementById("tryResult");
  document.getElementById("tryAudioPlayers").innerHTML = "";

  let resp;
  if (kind === "stt") {
    const audioBlob = recordedAudioBlob || document.getElementById("tryAudioFile").files[0];
    if (!audioBlob) {
      resultEl.textContent = "Pick an audio file or record one first.";
      return;
    }
    const form = new FormData();
    form.append("audio", audioBlob, audioBlob.name || "recording.webm");
    form.append("provider", provider);
    const lang = document.getElementById("tryAudioLang").value.trim();
    if (lang) form.append("lang", lang);
    // No Content-Type header: the browser sets the multipart boundary.
    resp = await fetch("/stt", { method: "POST", headers: authHeaders(), body: form });
  } else {
    let body;
    try {
      body = JSON.parse(document.getElementById("tryBody").value || "{}");
    } catch (e) {
      resultEl.textContent = `Invalid JSON body: ${e.message}`;
      return;
    }
    body.provider = provider;
    if (forceRefresh) body.forceRefresh = true;
    resp = await fetch(`/${kind}`, {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  // Parse-then-restringify (not resp.text()) for two reasons at once:
  // pretty-printed indentation, and literal Unicode (IPA/Norwegian
  // characters) instead of however the wire bytes happened to be escaped.
  let data = null;
  let display;
  try {
    data = await resp.json();
    display = JSON.stringify(data, null, 2);
  } catch (e) {
    display = await resp.text();
  }
  resultEl.textContent = `HTTP ${resp.status}\n${display}`;

  if (kind === "tts" && data) await renderAudioPlayers(data);
  refreshAll();
}

document.addEventListener("DOMContentLoaded", () => {
  const tokenInput = document.getElementById("tokenInput");
  tokenInput.value = getToken();
  tokenInput.addEventListener("change", () => {
    localStorage.setItem(TOKEN_KEY, tokenInput.value.trim());
    refreshAll();
  });
  document.getElementById("tryForm").addEventListener("submit", submitTryIt);
  document.getElementById("refreshBtn").addEventListener("click", refreshAll);
  document.getElementById("tryRecordBtn").addEventListener("click", toggleRecording);
  refreshAll();
});
