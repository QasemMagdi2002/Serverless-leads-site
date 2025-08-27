/* Runtime config loader: reads API URL from ./config.json (no rebuild needed) */
let API_BASE_URL = null;

const $ = (sel) => document.querySelector(sel);
const byId = (id) => document.getElementById(id);

async function loadConfig() {
  try {
    const res = await fetch("./config.json", { cache: "no-store" });
    if (!res.ok) return;
    const cfg = await res.json();
    if (typeof cfg.API_BASE_URL === "string" && cfg.API_BASE_URL.trim()) {
      API_BASE_URL = cfg.API_BASE_URL.trim().replace(/\/$/, "");
    }
  } catch (_) {
    // ignore; stays null
  }
}

function parseUTM() {
  const p = new URLSearchParams(location.search);
  const obj = {};
  ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"].forEach((k) => {
    if (p.get(k)) obj[k] = p.get(k);
  });
  return obj;
}

function validate(form) {
  const errors = {};
  const name = form.name.value.trim();
  const email = form.email.value.trim();
  const message = form.message.value.trim();
  const consent = form.consent.checked;

  if (name.length < 2) errors.name = "Please enter your full name.";
  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  if (!emailOk) errors.email = "Please enter a valid email.";
  if (message.length < 10) errors.message = "Please provide a few more details.";
  if (!consent) errors.consent = "You must consent to be contacted.";

  return { ok: Object.keys(errors).length === 0, errors, data: { name, email, message } };
}

function showErrors(errors) {
  ["name", "email", "message", "consent"].forEach((k) => {
    const node = document.querySelector(`.error[data-for="${k}"]`);
    if (node) node.textContent = errors[k] || "";
  });
}

function setLoading(loading) {
  const btn = byId("submit-btn");
  if (loading) btn.classList.add("loading");
  else btn.classList.remove("loading");
  btn.disabled = loading;
}

function showAlert(type, visible, customText) {
  const id = type === "success" ? "success" : "failure";
  const node = byId(id);
  if (customText) node.textContent = customText;
  node.hidden = !visible;
  byId(id === "success" ? "failure" : "success").hidden = true;
}

function buildPayload(form) {
  const { data } = validate(form);
  const utm = parseUTM();
  return {
    ...data,
    utm,
    userAgent: navigator.userAgent,
    referer: document.referrer || null,
    ts: new Date().toISOString(),
  };
}

async function postJSON(url, body, timeoutMs = 10000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      mode: "cors",
      signal: ctrl.signal,
    });
    clearTimeout(t);
    const isJson = res.headers.get("content-type")?.includes("application/json");
    const payload = isJson ? await res.json() : await res.text();
    if (!res.ok) {
      const errMsg = typeof payload === "object" && payload?.message ? payload.message : res.statusText;
      throw new Error(errMsg || "Request failed");
    }
    return payload;
  } catch (err) {
    clearTimeout(t);
    throw err;
  }
}

function initYear() {
  byId("year").textContent = new Date().getFullYear();
}

window.addEventListener("DOMContentLoaded", async () => {
  initYear();
  await loadConfig();

  const form = byId("lead-form");
  const resetBtn = byId("reset-btn");
  const submitBtn = byId("submit-btn");

  // If API isn’t configured yet, disable form with a friendly message
  if (!API_BASE_URL) {
    submitBtn.disabled = true;
    showAlert("error", true, "⚙️ Form not configured yet. Please try again later.");
    return;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showAlert("success", false);
    showAlert("error", false);

    const v = validate(form);
    showErrors(v.errors);
    if (!v.ok) return;

    setLoading(true);
    try {
      const payload = buildPayload(form);
      const resp = await postJSON(`${API_BASE_URL}/lead`, payload);
      console.info("Lead submitted:", resp);
      showAlert("success", true);
      form.reset();
    } catch (err) {
      console.error("Submit failed:", err);
      showAlert("error", true, "❌ Something went wrong. Please try again in a moment.");
    } finally {
      setLoading(false);
    }
  });

  resetBtn.addEventListener("click", () => {
    showErrors({});
    showAlert("success", false);
    showAlert("error", false);
  });
});
