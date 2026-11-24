import { h, icon, refreshIcons, CONDITIONS, condLabel, fmt, signed, actPill, utterance, masteryBars } from "./common.js";

const PRESETS = [
  { id: "openai", label: "OpenAI", url: "https://api.openai.com/v1", model: "gpt-4.1-mini" },
  { id: "openrouter", label: "OpenRouter", url: "https://openrouter.ai/api/v1", model: "qwen/qwen3-30b-a3b-instruct-2507" },
  { id: "deepseek", label: "DeepSeek", url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { id: "dashscope", label: "Alibaba DashScope (compatible mode)", url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { id: "vllm", label: "Local vLLM (paper setup)", url: "http://localhost:8101/v1", model: "Qwen3.5-35B-A3B", nothink: true },
  { id: "custom", label: "Other OpenAI-compatible", url: "", model: "" },
];
const DEFAULT_CONDS = ["vanilla", "informed", "gla_full"];
const LIVE_CONDS = ["vanilla", "socratic", "informed", "gla_fixed", "gla_reactive", "gla_full", "gla_single_probe", "gla_full_validated"];
const KEY_STORE = "gla-demo-key";

const $ = (id) => document.getElementById(id);
let worker = null;
let ready = false;
let running = false;
let domain = { order: [], skills: {} };
let cards = [];
let lastTraces = [];

function setStatus(parts) {
  const el = $("live-status");
  el.replaceChildren(...[].concat(parts));
  refreshIcons();
}

function spinner(text) {
  return [h("span", { class: "spin", style: "display:inline-flex" }, icon("loader-2")), h("span", {}, text)];
}

function ensureWorker() {
  if (worker) return;
  worker = new Worker(new URL("./worker.js", import.meta.url));
  worker.onmessage = (ev) => {
    const msg = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data;
    handle(msg);
  };
  worker.onerror = (e) => handle({ type: "error", text: e.message || "Worker failed to start" });
  setStatus(spinner("Loading Python runtime (about 10 MB, first time only)"));
  worker.postMessage({ type: "init" });
}

function handle(msg) {
  switch (msg.type) {
    case "status": if (!running) setStatus(spinner(msg.text)); break;
    case "ready":
      ready = true;
      if (!running) setStatus([icon("check-circle-2"), h("span", {}, "Runtime ready. Sessions run in your browser.")]);
      break;
    case "domain": domain = { order: msg.order, skills: msg.skills }; break;
    case "session_start": startCard(msg); break;
    case "turn": addTurn(msg); break;
    case "call": countCall(msg); break;
    case "session_done": finishCard(msg); break;
    case "all_done": done(`Finished ${msg.n} session(s).`); break;
    case "error": done(null, msg.text); break;
  }
}

let calls = 0;
let failedCalls = 0;
let currentIdx = -1;
function countCall(msg) {
  calls += 1;
  if (!msg.ok) failedCalls += 1;
  const card = cards[currentIdx];
  setStatus([...spinner(`Running ${card ? condLabel(card.condition) : ""}`),
    h("span", { class: "pill" }, `${calls} calls`),
    failedCalls ? h("span", { class: "pill no" }, `${failedCalls} retried`) : null]);
}

function metricBox(label, value) {
  return h("div", { class: "metric" }, h("b", {}, value), h("span", {}, label));
}

function startCard(msg) {
  currentIdx = msg.index;
  const card = {
    condition: msg.condition, turns: 0, learned: new Set(), leaks: 0, substantive: 0,
    metrics: h("div", { class: "metrics" }),
    mastery: h("div"), transcript: h("div", { class: "transcript" }),
    badge: h("span", { class: "pill" }, "running"),
  };
  card.el = h("div", { class: "panel session-card" },
    h("div", { class: "session-head" },
      h("h3", {}, condLabel(msg.condition)),
      h("span", { class: "small muted" }, CONDITIONS[msg.condition] ? CONDITIONS[msg.condition].desc : ""),
      h("span", { style: "margin-left:auto" }, card.badge)),
    card.metrics, card.mastery, card.transcript);
  cards[msg.index] = card;
  $("sessions").append(card.el);
  renderMetrics(card);
  card.mastery.replaceChildren(masteryBars(domain.order, domain.skills, msg.state.m, null));
}

function renderMetrics(card, gain) {
  card.metrics.replaceChildren(
    metricBox("turns", card.turns),
    metricBox("skills learned", card.learned.size),
    metricBox("leak rate", card.substantive ? fmt(card.leaks / card.substantive, 2) : "–"),
    metricBox("normalized gain", gain ? signed(gain.norm_gain, 3) : "…"));
}

function addTurn(msg) {
  const card = cards[msg.index];
  if (!card) return;
  card.turns = msg.turn + 1;
  const a = msg.annotation;
  if (["teach", "ask", "both"].includes(a.act)) {
    card.substantive += 1;
    if (a.leaked) card.leaks += 1;
  }
  for (const [sid, v] of Object.entries(msg.state.m)) if (v >= 0.8) card.learned.add(sid);
  card.transcript.append(h("div", { class: "turn" },
    h("div", { class: "meta" }, h("span", {}, `#${msg.turn + 1}`), ...actPill(a, msg.directive)),
    utterance("tutor", msg.tutor), utterance("child", msg.child)));
  card.transcript.scrollTop = card.transcript.scrollHeight;
  card.mastery.replaceChildren(masteryBars(domain.order, domain.skills, msg.state.m, msg.belief));
  renderMetrics(card);
}

function finishCard(msg) {
  const card = cards[msg.index];
  lastTraces[msg.index] = msg.trace;
  card.learned = new Set(msg.trace.learned_skills);
  renderMetrics(card, msg.trace.gain);
  card.badge.className = "pill ok";
  card.badge.textContent = `pre ${fmt(msg.trace.gain.pre, 2)} → post ${fmt(msg.trace.gain.post, 2)}`;
}

function done(text, error) {
  running = false;
  $("run-btn").disabled = false;
  $("mock-btn").disabled = false;
  $("stop-btn").disabled = true;
  const dl = lastTraces.filter(Boolean).length
    ? h("button", { class: "btn", type: "button", onclick: downloadTraces }, icon("download"), "Traces JSON")
    : null;
  if (error) {
    setStatus([h("span", { class: "notice bad", style: "margin:0" }, error), dl]);
  } else {
    setStatus([icon("check-circle-2"), h("span", {}, text), dl]);
  }
}

function downloadTraces() {
  const blob = new Blob([JSON.stringify(lastTraces.filter(Boolean), null, 1)], { type: "application/json" });
  const a = h("a", { href: URL.createObjectURL(blob), download: `gla_live_${Date.now()}.json` });
  document.body.append(a); a.click(); a.remove();
}

function stop() {
  if (worker) worker.terminate();
  worker = null; ready = false;
  for (const c of cards) if (c && c.badge.textContent === "running") { c.badge.className = "pill no"; c.badge.textContent = "stopped"; }
  done("Stopped. The runtime will reload on the next run.");
}

function selectedConditions() {
  return [...document.querySelectorAll("#cond-checks input:checked")].map((x) => x.value);
}

function currentDomain() {
  return document.querySelector("#domain-seg button[aria-pressed=true]").dataset.v;
}

function updateHint() {
  const n = selectedConditions().length;
  const t = Number($("turns").value) || 0;
  const v = selectedConditions().includes("gla_full_validated") ? " (validator adds up to 3 judge calls per turn)" : "";
  $("cost-hint").textContent = n ? `About ${n * t * 3} model calls: tutor, judge and child per turn${v}.` : "Select at least one condition.";
  const prof = $("profile");
  const branched = currentDomain() === "early_math_branched";
  prof.querySelector("option[value=scatter]").disabled = !branched;
  if (!branched && prof.value === "scatter") prof.value = "zero";
}

function readRole(urlId, modelId, keyId, fallback) {
  const url = $(urlId).value.trim();
  const model = $(modelId).value.trim();
  if (!url && !model) return fallback;
  return { base_url: url || fallback.base_url, model: model || fallback.model,
           api_key: $(keyId).value.trim() || fallback.api_key };
}

function run(mock) {
  const conditions = selectedConditions();
  if (!conditions.length) { updateHint(); return; }
  const tutor = { base_url: $("base-url").value.trim(), model: $("model").value.trim(), api_key: $("api-key").value.trim() };
  if (!mock && (!tutor.base_url || !tutor.model)) { $("live-form").reportValidity(); return; }
  if ($("remember-key").checked) sessionStorage.setItem(KEY_STORE, tutor.api_key); else sessionStorage.removeItem(KEY_STORE);
  const config = {
    mock, domain: currentDomain(), profile: $("profile").value, conditions,
    turns: Number($("turns").value), seed: Number($("seed").value),
    roles: mock ? {} : { tutor, judge: readRole("judge-url", "judge-model", "judge-key", tutor),
                         child: readRole("child-url", "child-model", "child-key", tutor) },
    options: { vllm_nothink: $("vllm-nothink").checked, max_tokens: Number($("max-tokens").value) || 800 },
  };
  ensureWorker();
  running = true; calls = 0; failedCalls = 0; cards = []; lastTraces = [];
  $("sessions").replaceChildren();
  $("run-btn").disabled = true; $("mock-btn").disabled = true; $("stop-btn").disabled = false;
  setStatus(spinner(ready ? "Starting" : "Loading Python runtime"));
  worker.postMessage({ type: "run", config });
}

function applyPreset(id) {
  const p = PRESETS.find((x) => x.id === id);
  if (!p) return;
  $("base-url").value = p.url;
  $("model").value = p.model;
  $("vllm-nothink").checked = !!p.nothink;
}

export function initLive() {
  const sel = $("preset");
  for (const p of PRESETS) sel.append(h("option", { value: p.id }, p.label));
  sel.addEventListener("change", () => applyPreset(sel.value));
  applyPreset("openai");
  const saved = sessionStorage.getItem(KEY_STORE);
  if (saved) { $("api-key").value = saved; $("remember-key").checked = true; }

  const box = $("cond-checks");
  for (const c of LIVE_CONDS) {
    box.append(h("label", { title: CONDITIONS[c].desc },
      h("input", { type: "checkbox", value: c, checked: DEFAULT_CONDS.includes(c), onchange: updateHint }),
      condLabel(c)));
  }
  document.querySelectorAll("#domain-seg button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#domain-seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    updateHint();
  }));
  document.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => {
    const t = $("turns"); t.value = Math.max(2, Math.min(40, Number(t.value) + Number(b.dataset.step))); updateHint();
  }));
  document.querySelectorAll("[data-seed]").forEach((b) => b.addEventListener("click", () => {
    const s = $("seed"); s.value = Math.max(1, Math.min(999, Number(s.value) + Number(b.dataset.seed)));
  }));
  $("turns").addEventListener("input", updateHint);
  $("toggle-key").addEventListener("click", () => {
    const k = $("api-key"); k.type = k.type === "password" ? "text" : "password";
  });
  $("live-form").addEventListener("submit", (e) => { e.preventDefault(); run(false); });
  $("mock-btn").addEventListener("click", () => run(true));
  $("stop-btn").addEventListener("click", stop);
  updateHint();
}
