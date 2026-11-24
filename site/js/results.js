import { h, getJSON, condLabel, condName, COND_ORDER, fmt, signed, pfmt, mean, sd } from "./common.js";

const $ = (id) => document.getElementById(id);
const METRICS = [
  ["norm_gain", "Normalized gain", 3],
  ["n_learned", "Skills learned", 2],
  ["gap_coverage", "Gap coverage", 3],
  ["leakage_rate", "Leakage", 3],
  ["chitchat_rate", "Chitchat", 3],
  ["blocked_rate", "Prereq-blocked", 3],
];

function byCondition(rows) {
  const out = {};
  for (const r of rows) (out[r.condition] = out[r.condition] || []).push(r);
  return COND_ORDER.filter((c) => out[c]).map((c) => [c, out[c]])
    .concat(Object.keys(out).filter((c) => !COND_ORDER.includes(c)).map((c) => [c, out[c]]));
}

function summaryTable(rows) {
  const table = $("summary-table");
  const head = h("tr", {}, h("th", {}, "Condition"), h("th", {}, "n"),
    METRICS.map(([, label]) => h("th", {}, label)));
  const body = byCondition(rows).map(([c, rs]) => h("tr", { class: c === "gla_full" ? "hl" : "" },
    h("td", { title: c }, condName(c)), h("td", { class: "num" }, rs.length),
    METRICS.map(([k, , d]) => {
      const xs = rs.map((r) => r[k]).filter((v) => v !== undefined && v !== null);
      if (!xs.length) return h("td", { class: "num" }, "–");
      const m = mean(xs);
      const scale = k === "n_learned" ? 3 : 1;
      const bar = ["n_learned", "leakage_rate", "chitchat_rate", "blocked_rate", "gap_coverage"].includes(k)
        ? h("span", { class: "cell-bar" }, h("i", { style: `width:${Math.max(0, Math.min(100, (m / scale) * 100))}%;${k === "leakage_rate" || k === "blocked_rate" || k === "chitchat_rate" ? "background:var(--child)" : ""}` }))
        : null;
      return h("td", { class: "num" }, fmt(m, d), h("span", { class: "sd" }, `±${fmt(sd(xs), d)}`), bar);
    })));
  table.replaceChildren(h("thead", {}, head), h("tbody", {}, body));
}

function profileTable(rows) {
  const profiles = [...new Set(rows.map((r) => r.profile))];
  const head = h("tr", {}, h("th", {}, "Condition"), profiles.map((p) => h("th", {}, p)));
  const body = byCondition(rows).map(([c, rs]) => h("tr", { class: c === "gla_full" ? "hl" : "" },
    h("td", {}, condName(c)),
    profiles.map((p) => {
      const xs = rs.filter((r) => r.profile === p).map((r) => r.norm_gain);
      return h("td", { class: "num" }, xs.length ? signed(mean(xs)) : "–");
    })));
  $("profile-table").replaceChildren(h("thead", {}, head), h("tbody", {}, body));
}

/* Paired profile-seed blocks against C4: mean difference, percentile
   bootstrap CI (10k draws, fixed seed) and exact sign-flip p (Monte Carlo
   above 16 blocks). Mirrors experiments/analyze_paired.py. */
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
function pairedStats(diff) {
  const n = diff.length, obs = Math.abs(mean(diff));
  let hits = 0, total = 0;
  if (n <= 16) {
    for (let m = 0; m < (1 << n); m++) {
      let s = 0;
      for (let i = 0; i < n; i++) s += (m >> i) & 1 ? -diff[i] : diff[i];
      hits += Math.abs(s / n) >= obs - 1e-12; total += 1;
    }
  } else {
    const r = rng(19);
    for (let k = 0; k < 20000; k++) {
      let s = 0;
      for (const d of diff) s += r() < 0.5 ? -d : d;
      hits += Math.abs(s / n) >= obs - 1e-12; total += 1;
    }
  }
  const r = rng(1), boots = [];
  for (let k = 0; k < 10000; k++) {
    let s = 0;
    for (let i = 0; i < n; i++) s += diff[Math.floor(r() * n)];
    boots.push(s / n);
  }
  boots.sort((a, b) => a - b);
  return { mean: mean(diff), lo: boots[249], hi: boots[9749], p: hits / total };
}

function pairedTable(rows, metric) {
  const t = $("paired-table");
  const key = (r) => `${r.profile}|${r.seed}`;
  const ref = new Map(rows.filter((r) => r.condition === "gla_full").map((r) => [key(r), r[metric]]));
  const d = metric === "n_learned" ? 2 : 3;
  const stats = [];
  const head = h("tr", {}, h("th", {}, "C4 GLA minus"), h("th", {}, "Blocks"), h("th", {}, "Mean diff."), h("th", {}, "95% bootstrap CI"), h("th", {}, "Sign-flip p"));
  const body = byCondition(rows).filter(([c]) => c !== "gla_full").map(([c, rs]) => {
    const diff = rs.filter((r) => ref.has(key(r))).map((r) => ref.get(key(r)) - r[metric]);
    if (diff.length < 3) return null;
    const s = pairedStats(diff);
    stats.push({ c, ...s, n: diff.length });
    return h("tr", {}, h("td", {}, condName(c)), h("td", { class: "num" }, diff.length), h("td", { class: "num" }, signed(s.mean, d)),
      h("td", { class: "num" }, `[${fmt(s.lo, d)}, ${fmt(s.hi, d)}]`), h("td", { class: "num" }, pfmt(s.p)));
  }).filter(Boolean);
  t.replaceChildren(h("thead", {}, head), h("tbody", {}, body.length ? body : h("tr", {}, h("td", {}, "No C4 reference in this group."))));
  $("forest").replaceChildren(stats.length ? forest(stats, metric) : h("div"));
}


/* Dot-and-whisker plot of C4 minus each condition with bootstrap CI. */
function forest(stats, metric) {
  const NS = "http://www.w3.org/2000/svg";
  const rowH = 26, L = 128, R = 64, T = 8, B = 26, W = 560;
  const H = T + B + rowH * stats.length;
  let lo = Math.min(0, ...stats.map((s) => s.lo)), hi = Math.max(0, ...stats.map((s) => s.hi));
  const pad = (hi - lo) * 0.08 || 0.1; lo -= pad; hi += pad;
  const x = (v) => L + ((v - lo) / (hi - lo)) * (W - L - R);
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "forest");
  svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Paired effects of C4 with 95% confidence intervals");
  const add = (tag, attrs, parent = svg) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.append(e); return e; };
  const step = niceStep((hi - lo) / 5);
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    add("line", { x1: x(v), x2: x(v), y1: T, y2: H - B, class: "grid" });
    const t = add("text", { x: x(v), y: H - 8, "text-anchor": "middle", class: "tick" }); t.textContent = (+v.toFixed(3)).toString();
  }
  add("line", { x1: x(0), x2: x(0), y1: T - 2, y2: H - B + 2, class: "zero" });
  stats.forEach((s, i) => {
    const y = T + rowH * i + rowH / 2;
    const g = add("g", { class: s.lo > 0 || s.hi < 0 ? "sig" : "ns" });
    const lab = add("text", { x: 0, y: y + 4 }, g); lab.textContent = condLabel(s.c);
    add("line", { x1: x(s.lo), x2: x(s.hi), y1: y, y2: y, class: "ci" }, g);
    add("circle", { cx: x(s.mean), cy: y, r: 4.5, class: "pt" }, g);
    const v = add("text", { x: W - 4, y: y + 4, "text-anchor": "end", class: "val" }, g);
    v.textContent = signed(s.mean, metric === "n_learned" ? 2 : 3);
  });
  return svg;
}
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / p;
  return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p;
}
const CHIP = { resub_main: "Main (8 conditions)", resub_branched: "Branched domain", resub_softgate: "Soft gate", resub_thr09: "Threshold 0.9",
  resub_xjudge: "Gemma judge", resub_xtutor: "Gemma tutor", linear: "Original: linear", branched: "Original: branched",
  alpha_half: "Original: rates x0.5", alpha_double: "Original: rates x2" };
function chipLabel(g) { return CHIP[g.id] || g.id.replace(/^resub_/, "").replace(/_/g, " "); }

export async function initResults(index) {
  const seg = $("group-seg");
  let metric = "n_learned";
  let current = null;
  const show = (g) => {
    current = g;
    seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.g === g.id)));
    $("group-desc").textContent = g.label;
    const rows = index.sessions.filter((s) => s.group === g.id);
    summaryTable(rows);
    profileTable(rows);
    pairedTable(rows, metric);
    const tag = g.status === "new" ? "Added for the resubmission." : "Released with the manuscript.";
    $("summary-note").textContent = `${g.label}. ${rows.length} sessions, 24 tutor turns each, mean ± SD over sessions. ${tag} ` +
      "Gains are state-based pre/post tests on the simulated child; the fixed-state no-learning null has SD ≈ 0.07.";
  };
  for (const g of index.groups) {
    const n = index.sessions.filter((s) => s.group === g.id).length;
    seg.append(h("button", { type: "button", class: "chip", "data-g": g.id, "aria-pressed": "false", title: g.label, onclick: () => show(g) }, chipLabel(g), h("span", { class: "n" }, n)));
  }
  document.querySelectorAll("#metric-seg button").forEach((b) => b.addEventListener("click", () => {
    metric = b.dataset.m;
    document.querySelectorAll("#metric-seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    if (current) show(current);
  }));
  const first = index.groups.find((g) => /main/.test(g.id)) || index.groups[0];
  if (first) show(first);
}
