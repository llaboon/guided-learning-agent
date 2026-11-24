import { h, getJSON, condLabel, COND_ORDER, fmt, signed, actPill, utterance, masteryBars } from "./common.js";

const $ = (id) => document.getElementById(id);
const COLORS = ["#0f766e", "#2c5fa8", "#b45309", "#7c3aed", "#be185d", "#4d7c0f", "#0e7490",
  "#9a3412", "#475569", "#a16207", "#1d4ed8", "#15803d", "#c2410c", "#6d28d9", "#0369a1",
  "#b91c1c", "#4338ca", "#047857", "#92400e", "#334155", "#86198f"];
let index = null;
let domains = {};

function opt(v, label) { return h("option", { value: v }, label); }

function fillFilters() {
  const g = $("ex-group").value;
  const rows = index.sessions.filter((s) => s.group === g);
  const conds = COND_ORDER.filter((c) => rows.some((r) => r.condition === c));
  const profs = [...new Set(rows.map((r) => r.profile))];
  const keepC = $("ex-cond").value, keepP = $("ex-prof").value;
  $("ex-cond").replaceChildren(opt("", "All conditions"), ...conds.map((c) => opt(c, condLabel(c))));
  $("ex-prof").replaceChildren(opt("", "All profiles"), ...profs.map((p) => opt(p, p)));
  if (conds.includes(keepC)) $("ex-cond").value = keepC;
  if (profs.includes(keepP)) $("ex-prof").value = keepP;
  fillList();
}

function fillList() {
  const g = $("ex-group").value, c = $("ex-cond").value, p = $("ex-prof").value;
  const rows = index.sessions.filter((s) => s.group === g && (!c || s.condition === c) && (!p || s.profile === p));
  const head = h("tr", {}, h("th", {}, "Session"), h("th", {}, "Gain"), h("th", {}, "Learned"));
  const body = rows.map((r) => {
    const tr = h("tr", { class: r.file ? "click" : "", title: r.file ? "" : "Trace not released" },
      h("td", {}, `${condLabel(r.condition)} · ${r.profile} · s${r.seed}`),
      h("td", {}, signed(r.norm_gain)), h("td", {}, r.n_learned ?? "–"));
    if (r.file) tr.addEventListener("click", () => {
      $("ex-list").querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
      tr.classList.add("sel");
      showTrace(r);
    });
    return tr;
  });
  $("ex-list").replaceChildren(h("thead", {}, head), h("tbody", {}, body));
}

/* Rebuild the true-mastery trajectory per skill from state events. */
function trajectory(trace, order) {
  const init = new Set(trace.student_profile.mastered || []);
  const cur = Object.fromEntries(order.map((s) => [s, init.has(s) ? 1 : 0]));
  const n = trace.n_turns || (trace.annotations || []).length;
  const series = Object.fromEntries(order.map((s) => [s, [cur[s]]]));
  const byTurn = {};
  for (const e of trace.state_events || []) if (e.event === "progress") (byTurn[e.turn] = byTurn[e.turn] || []).push(e);
  const blocked = new Set((trace.state_events || []).filter((e) => e.event === "blocked_prereq").map((e) => e.turn));
  for (let t = 0; t < n; t++) {
    for (const e of byTurn[t] || []) cur[e.skill] = e.m;
    for (const s of order) series[s].push(cur[s]);
  }
  return { series, n, blocked };
}

function timelineSvg(trace, dom) {
  const order = dom.skills.map((s) => s.id);
  const { series, n, blocked } = trajectory(trace, order);
  const W = 640, H = 180, L = 30, R = 8, T = 8, B = 20;
  const x = (t) => L + (t / Math.max(n, 1)) * (W - L - R);
  const y = (v) => T + (1 - v) * (H - T - B);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "timeline");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "True mastery per skill over tutor turns");
  const add = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); svg.append(e); return e; };
  for (const t of blocked) add("rect", { x: x(t), y: T, width: Math.max(1, x(t + 1) - x(t)), height: H - T - B, fill: "#fdf1e3" });
  for (const v of [0, 0.5, 1]) add("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#e5e7ea" });
  add("line", { x1: L, x2: W - R, y1: y(0.8), y2: y(0.8), stroke: "#7b858f", "stroke-dasharray": "3 3" });
  for (const v of [0, 0.8, 1]) { const tx = add("text", { x: L - 4, y: y(v) + 4, "text-anchor": "end", "font-size": 10, fill: "#5d6670" }); tx.textContent = v; }
  for (let t = 0; t <= n; t += Math.max(1, Math.ceil(n / 8))) { const tx = add("text", { x: x(t), y: H - 6, "text-anchor": "middle", "font-size": 10, fill: "#5d6670" }); tx.textContent = t; }
  const legend = [];
  order.forEach((sid, i) => {
    const s = series[sid];
    if (s.every((v) => v === s[0])) return;
    add("polyline", { points: s.map((v, t) => `${x(t)},${y(v)}`).join(" "), fill: "none", stroke: COLORS[i % COLORS.length], "stroke-width": 1.6 });
    legend.push(h("span", {}, h("i", { style: `background:${COLORS[i % COLORS.length]}` }), dom.skills[i].name));
  });
  return h("div", {}, svg, h("div", { class: "legend" }, legend.length ? legend : h("span", {}, "No skill moved during this session."),
    blocked.size ? h("span", {}, h("i", { style: "background:#f3d9b8;height:8px" }), "turn blocked by prerequisite gate") : null));
}

async function showTrace(row) {
  const box = $("ex-detail");
  box.replaceChildren(h("div", { class: "empty" }, "Loading…"));
  const [trace, index2] = await Promise.all([getJSON(row.file), Promise.resolve(index)]);
  const domId = index2.groups.find((g) => g.id === row.group).domain;
  const dom = domains[domId] || (domains[domId] = await getJSON(`data/domains/${domId}.json`));
  const skills = Object.fromEntries(dom.skills.map((s) => [s.id, s]));
  const order = dom.skills.map((s) => s.id);
  const anns = trace.annotations || [];
  const dirs = trace.directives || [];
  const turns = [];
  let ti = 0;
  const tr = trace.transcript || [];
  turns.push(h("div", { class: "turn" }, utterance("child", tr[0] ? tr[0].text : "")));
  for (let i = 1; i < tr.length; i += 2) {
    turns.push(h("div", { class: "turn" },
      h("div", { class: "meta" }, h("span", {}, `#${ti + 1}`), ...actPill(anns[ti], dirs[ti])),
      utterance("tutor", tr[i].text), tr[i + 1] ? utterance("child", tr[i + 1].text) : null));
    ti += 1;
  }
  const g = trace.gain || {};
  box.replaceChildren(
    h("div", { class: "session-head" }, h("h3", {}, `${condLabel(row.condition)} · ${row.profile} · seed ${row.seed}`),
      h("a", { href: row.file, download: "", class: "btn", style: "margin-left:auto" }, "Download JSON")),
    h("div", { class: "metrics" },
      h("div", { class: "metric" }, h("b", {}, signed(g.norm_gain)), h("span", {}, "normalized gain")),
      h("div", { class: "metric" }, h("b", {}, `${fmt(g.pre, 2)} → ${fmt(g.post, 2)}`), h("span", {}, "pre → post")),
      h("div", { class: "metric" }, h("b", {}, (trace.learned_skills || []).length), h("span", {}, "skills learned")),
      h("div", { class: "metric" }, h("b", {}, fmt(row.blocked_rate, 2)), h("span", {}, "blocked rate"))),
    h("h3", {}, "True mastery over turns"), timelineSvg(trace, dom),
    h("div", { class: "cols-2", style: "margin-top:10px" },
      h("div", {}, h("h3", {}, "Final true state and tutor belief"),
        masteryBars(order, skills, trace.final_state ? trace.final_state.m : {}, trace.final_belief)),
      h("div", {}, h("h3", {}, "Transcript"), h("div", { class: "transcript" }, turns))));
}

export function initExplore(idx) {
  index = idx;
  $("ex-group").replaceChildren(...idx.groups.filter((g) => g.with_trace).map((g) => opt(g.id, `${g.label} (${g.with_trace})`)));
  $("ex-group").addEventListener("change", fillFilters);
  $("ex-cond").addEventListener("change", fillList);
  $("ex-prof").addEventListener("change", fillList);
  fillFilters();
}
