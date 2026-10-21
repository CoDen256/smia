// ui/ui.js — vanilla JS, no build step (matches phonexa's plain HTML/JS
// pattern). The shared bearer token (D-S6) is pasted once and kept in
// localStorage; this is an operator tool, not an end-user page.

const TOKEN_KEY = "smia_ui_token";

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
        <td>${r.requestsCount}</td><td>${hitRate}%</td>
        <td class="ok">${r.lastSuccessAt || "—"}</td>
        <td>${lastFail}</td>
      </tr>`;
    })
    .join("");
}

function populateTryItSelectors(providers) {
  const kindSel = document.getElementById("tryKind");
  const prevKind = kindSel.value;
  kindSel.innerHTML = Object.keys(providers)
    .map((k) => `<option value="${k}">${k}</option>`)
    .join("");
  if (prevKind) kindSel.value = prevKind;
  updateProviderSelector(providers);
  kindSel.onchange = () => updateProviderSelector(providers);
}

function updateProviderSelector(providers) {
  const kind = document.getElementById("tryKind").value;
  const provSel = document.getElementById("tryProvider");
  provSel.innerHTML = (providers[kind] || []).map((p) => `<option value="${p}">${p}</option>`).join("");
}

async function submitTryIt(event) {
  event.preventDefault();
  const kind = document.getElementById("tryKind").value;
  const provider = document.getElementById("tryProvider").value;
  let body;
  try {
    body = JSON.parse(document.getElementById("tryBody").value || "{}");
  } catch (e) {
    document.getElementById("tryResult").textContent = `Invalid JSON body: ${e.message}`;
    return;
  }
  body.provider = provider;
  body.forceRefresh = true; // manual try-it always bypasses the cache (provider-catalog spec)

  const resp = await fetch(`/${kind}`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await resp.text();
  document.getElementById("tryResult").textContent = `HTTP ${resp.status}\n${text}`;
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
