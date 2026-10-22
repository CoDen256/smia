// ui/ui.js — vanilla JS, no build step (matches phonexa's plain HTML/JS
// pattern). The shared bearer token (D-S6) is pasted once and kept in
// localStorage; this is an operator tool, not an end-user page.

const TOKEN_KEY = "smia_ui_token";

// One ready-to-send example body per kind, prefilled into the try-it form
// whenever the kind selector changes (not /stt — its request body is
// multipart audio, not JSON, so this form can't represent it).
const EXAMPLE_BODIES = {
  inflections: { word: "hus", lang: "nb" },
  ipa: { text: "hus", lang: "nb" },
  tts: { text: "hus", lang: "nb" },
  translations: { text: "hus", from: "nb", to: "en" },
};

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` };
}

async function refreshAll() {
  const [providers, healthRows] = await Promise.all([
    fetch("/providers", { headers: authHeaders() }).then((r) => r.json()),
    fetch("/health", { headers: authHeaders() }).then((r) => r.json()),
  ]);
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
  const bodyEl = document.getElementById("tryBody");
  if (kind === "stt") {
    bodyEl.value = "";
    bodyEl.placeholder = "/stt takes multipart audio, not JSON — not supported by this form";
    bodyEl.disabled = true;
  } else {
    bodyEl.disabled = false;
    bodyEl.value = JSON.stringify(EXAMPLE_BODIES[kind] || {}, null, 2);
  }
}

async function submitTryIt(event) {
  event.preventDefault();
  const kind = document.getElementById("tryKind").value;
  const provider = document.getElementById("tryProvider").value;
  const forceRefresh = document.getElementById("tryForceRefresh").checked;
  let body;
  try {
    body = JSON.parse(document.getElementById("tryBody").value || "{}");
  } catch (e) {
    document.getElementById("tryResult").textContent = `Invalid JSON body: ${e.message}`;
    return;
  }
  body.provider = provider;
  if (forceRefresh) body.forceRefresh = true;

  const resp = await fetch(`/${kind}`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  // Parse-then-restringify (not resp.text()) for two reasons at once:
  // pretty-printed indentation, and literal Unicode (IPA/Norwegian
  // characters) instead of however the wire bytes happened to be escaped.
  let display;
  try {
    const data = await resp.json();
    display = JSON.stringify(data, null, 2);
  } catch (e) {
    display = await resp.text();
  }
  document.getElementById("tryResult").textContent = `HTTP ${resp.status}\n${display}`;
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
  refreshAll();
});
