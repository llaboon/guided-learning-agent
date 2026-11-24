import { h, getJSON, condLabel, COND_ORDER, fmt, signed, pfmt, mean, sd } from "./common.js";

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
    h("td", { title: c }, condLabel(c)), h("td", {}, rs.length),
    METRICS.map(([k, , d]) => {
      const xs = rs.map((r) => r[k]).filter((v) => v !== undefined && v !== null);
      return h("td", {}, xs.length ? `${fmt(mean(xs), d)} ± ${fmt(sd(xs), d)}` : "–");
    })));
  table.replaceChildren(h("thead", {}, head), h("tbody", {}, body));
}

function profileTable(rows) {
  const profiles = [...new Set(rows.map((r) => r.profile))];
  const head = h("tr", {}, h("th", {}, "Condition"), profiles.map((p) => h("th", {}, p)));
  const body = byCondition(rows).map(([c, rs]) => h("tr", { class: c === "gla_full" ? "hl" : "" },
    h("td", {}, condLabel(c)),
    profiles.map((p) => {
      const xs = rs.filter((r) => r.profile === p).map((r) => r.norm_gain);
      return h("td", {}, xs.length ? signed(mean(xs)) : "–");
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
  const head = h("tr", {}, h("th", {}, "C4 GLA minus"), h("th", {}, "Blocks"), h("th", {}, "Mean diff."), h("th", {}, "95% bootstrap CI"), h("th", {}, "Sign-flip p"));
  const body = byCondition(rows).filter(([c]) => c !== "gla_full").map(([c, rs]) => {
    const diff = rs.filter((r) => ref.has(key(r))).map((r) => ref.get(key(r)) - r[metric]);
    if (diff.length < 3) return null;
    const s = pairedStats(diff);
    return h("tr", {}, h("td", {}, condLabel(c)), h("td", {}, diff.length), h("td", {}, signed(s.mean)),
      h("td", {}, `[${fmt(s.lo)}, ${fmt(s.hi)}]`), h("td", {}, pfmt(s.p)));
  }).filter(Boolean);
  t.replaceChildren(h("thead", {}, head), h("tbody", {}, body.length ? body : h("tr", {}, h("td", {}, "No C4 reference in this group."))));
  $("paired-title").textContent = `Paired effects on ${metric === "norm_gain" ? "normalized gain" : "skills learned"} (profile-seed blocks, unadjusted)`;
}

export async function initResults(index) {
  const seg = $("group-seg");
  let metric = "norm_gain";
  let current = null;
  const show = (g) => {
    current = g;
    seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.g === g.id)));
    const rows = index.sessions.filter((s) => s.group === g.id);
    summaryTable(rows);
    profileTable(rows);
    pairedTable(rows, metric);
    const tag = g.status === "new" ? "Added for the resubmission." : "Released with the manuscript.";
    $("summary-note").textContent = `${g.label}. ${rows.length} sessions, 24 tutor turns each, mean ± SD over sessions. ${tag} ` +
      "Gains are state-based pre/post tests on the simulated child; the fixed-state no-learning null has SD ≈ 0.07.";
  };
  for (const g of index.groups) {
    seg.append(h("button", { type: "button", "data-g": g.id, "aria-pressed": "false", title: g.label, onclick: () => show(g) }, g.id.replace(/^resub_/, "").replace(/_/g, " ") + (g.status === "new" ? " *" : "")));
  }
  document.querySelectorAll("#metric-seg button").forEach((b) => b.addEventListener("click", () => {
    metric = b.dataset.m;
    document.querySelectorAll("#metric-seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    if (current) show(current);
  }));
  if (index.groups.length) show(index.groups[0]);
}
