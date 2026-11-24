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

export function actPill(ann, directive) {
  const out = [];
  if (directive) out.push(h("span", { class: `pill ${directive.activity}` }, directive.activity));
  if (ann) {
    out.push(h("span", { class: `pill ${ann.act}`, title: "Blind judge annotation" }, ann.act));
    if (ann.skill) out.push(h("span", { class: "pill" }, ann.skill));
    if (ann.leaked) out.push(h("span", { class: "pill leak" }, "leaked"));
    if (ann.drawn_correct === true) out.push(h("span", { class: "pill ok" }, "correct"));
    if (ann.drawn_correct === false) out.push(h("span", { class: "pill no" }, "wrong"));
  }
  return out;
}

export function utterance(who, text) {
  return h("div", { class: `utt ${who}` },
    h("span", { class: "who" }, who === "tutor" ? "Tutor" : "Child"),
    h("span", { class: "txt" }, text));
}

/* Mastery bars: true state m (fill), tutor belief (orange tick), 0.8 line. */
export function masteryBars(order, skills, m, belief, threshold = 0.8) {
  return h("div", { class: "mastery" }, order.map((sid) => {
    const v = (m && m[sid]) || 0;
    const b = belief ? belief[sid] : null;
    const bar = h("div", { class: "bar", title: `true ${fmt(v, 2)}` + (b != null ? `, belief ${fmt(b, 2)}` : "") },
      h("i", { style: `width:${Math.round(v * 100)}%` }),
      b != null ? h("i", { class: "belief", style: `width:${Math.round(b * 100)}%` }) : null,
      h("span", { class: "thr", style: `left:${threshold * 100}%` }));
    return h("div", { class: "mrow" },
      h("span", { class: "nm", title: skills[sid] ? skills[sid].name : sid }, skills[sid] ? skills[sid].name : sid),
      bar, h("span", { class: "v" }, fmt(v, 2)));
  }));
}
