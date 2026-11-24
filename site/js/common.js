export const REPO = "https://github.com/llaboon/guided-learning-agent";

export const CONDITIONS = {
  vanilla:            { short: "C0 Vanilla",       desc: "Plain assistant prompt" },
  socratic:           { short: "C1 Socratic",      desc: "Pedagogical prompt" },
  informed:           { short: "C1+ Informed",     desc: "Prompt with the full skill graph, prerequisites and verification rules" },
  gla_fixed:          { short: "C2 Fixed order",   desc: "Executor + fixed curriculum, ignores evidence" },
  gla_reactive:       { short: "C3 Reactive",      desc: "Learner model, greedy weakest-skill choice" },
  gla_full:           { short: "C4 GLA",           desc: "Learner model + prerequisite planner" },
  gla_single_probe:   { short: "C4 single probe",  desc: "C4 trusting one passed probe" },
  gla_full_validated: { short: "C4 + validator",   desc: "C4 with checked and regenerated executor turns" },
};
export const COND_ORDER = Object.keys(CONDITIONS);
export const condLabel = (c) => (CONDITIONS[c] ? CONDITIONS[c].short : c);

export const PROFILES = {
  zero: "zero", mid: "mid", beggar: "beggar", scatter: "scatter",
};

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function icon(name, cls = "") {
  return h("i", { "data-lucide": name, class: cls });
}

let iconTimer = null;
export function refreshIcons() {
  clearTimeout(iconTimer);
  iconTimer = setTimeout(() => window.lucide && window.lucide.createIcons(), 0);
}

const cache = new Map();
export async function getJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path);
}

export const fmt = (v, d = 3) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toFixed(d);
export const signed = (v, d = 3) =>
  v === null || v === undefined ? "–" : (v >= 0 ? "+" : "") + Number(v).toFixed(d);
export const pfmt = (p) =>
  p === null || p === undefined ? "–" : p < 0.001 ? "<.001" : Number(p).toFixed(3).replace(/^0/, "");

export function mean(xs) { return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN; }
export function sd(xs) {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length - 1));
}

export const COND_COLORS = {
  vanilla: "#8a939c", socratic: "#a08a6a", informed: "#c7771a", gla_fixed: "#3567c4",
  gla_reactive: "#8a55c9", gla_full: "#0d8a7f", gla_single_probe: "#4fae9f", gla_full_validated: "#116d63",
};

export function condName(c) {
  return h("span", { class: "cname" },
    h("span", { class: "cond-mark", style: `background:${COND_COLORS[c] || "#999"}` }), condLabel(c));
}

export function actPill(ann, directive) {
  const out = [];
  if (directive) out.push(h("span", { class: `pill ${directive.activity}`, title: "Planner directive" }, directive.activity));
  if (ann) {
    if (!directive) out.push(h("span", { class: `pill ${ann.act}`, title: "Blind annotation" }, ann.act));
    if (ann.skill) out.push(h("span", { class: "pill skill", title: "Annotated skill" }, ann.skill));
    if (ann.leaked) out.push(h("span", { class: "pill leak" }, "leaked"));
    if (ann.drawn_correct === true) out.push(h("span", { class: "pill ok" }, "correct"));
    if (ann.drawn_correct === false) out.push(h("span", { class: "pill no" }, "wrong"));
  }
  return out;
}

/* One tutor turn plus the child's reply, as chat bubbles. */
export function chatTurn(n, tutorText, childText, ann, directive, fresh = false) {
  const act = directive ? directive.activity : (ann ? ann.act : "");
  const frag = [
    h("div", { class: `msg tutor ${act}${fresh ? " new" : ""}` },
      h("div", { class: "meta" }, h("span", { class: "turn-no" }, `T${n}`), ...actPill(ann, directive)),
      h("div", { class: "bubble" }, tutorText)),
  ];
  if (childText !== undefined && childText !== null) {
    frag.push(h("div", { class: `msg child${fresh ? " new" : ""}` },
      h("div", { class: "meta" }, "child"), h("div", { class: "bubble" }, childText)));
  }
  return frag;
}

export function childOpening(text) {
  return h("div", { class: "msg child" }, h("div", { class: "meta" }, "child"), h("div", { class: "bubble" }, text));
}

/* Paired bars per skill: child's true mastery (amber) and tutor belief (teal), 0.8 line. */
export function masteryBars(order, skills, m, belief, threshold = 0.8) {
  const rows = order.map((sid) => {
    const v = (m && m[sid]) || 0;
    const b = belief ? belief[sid] : null;
    const name = skills[sid] ? skills[sid].name : sid;
    const track = (cls, val) => h("div", { class: "track" },
      h("div", { class: `fill ${cls}`, style: `width:${Math.round(val * 100)}%` }),
      h("span", { class: "thr", style: `left:${threshold * 100}%` }));
    return h("div", { class: `mrow${v >= threshold ? " done" : ""}`, title: `${name}: true ${fmt(v, 2)}` + (b != null ? `, belief ${fmt(b, 2)}` : "") },
      h("span", { class: "nm" }, name),
      h("div", { class: "pbar" }, track("true", v), b != null ? track("belief", b) : null),
      h("span", { class: "v" }, fmt(v, 2)));
  });
  return h("div", {},
    h("div", { class: "mastery-legend", style: "margin-bottom:6px" },
      h("span", {}, h("i", { style: "background:var(--child)" }), "child's true mastery"),
      belief ? h("span", {}, h("i", { style: "background:var(--agent)" }), "tutor belief") : null,
      h("span", {}, h("i", { style: "background:var(--ink-2);width:2px;height:10px;opacity:.5" }), "mastery line 0.8")),
    h("div", { class: "mastery" }, rows));
}

/* Copy buttons for every pre.code inside root. */
export function addCopyButtons(root = document) {
  root.querySelectorAll(".code-wrap").forEach((w) => {
    if (w.querySelector(".copy")) return;
    const pre = w.querySelector("pre");
    const b = h("button", { class: "copy", type: "button", "aria-label": "Copy", "data-tip": "Copy" }, icon("copy"));
    b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(pre.innerText); } catch (e) { /* ignore */ }
      b.replaceChildren(icon("check")); refreshIcons();
      setTimeout(() => { b.replaceChildren(icon("copy")); refreshIcons(); }, 1400);
    });
    w.append(b);
  });
  refreshIcons();
}
