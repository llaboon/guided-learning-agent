import { h, icon, refreshIcons, getJSON, condLabel, condName, COND_ORDER, fmt, signed, chatTurn, childOpening, masteryBars } from "./common.js";

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
  const head = h("tr", {}, h("th", {}, "Session"), h("th", {}, "Gain"), h("th", {}, "Mastered"));
  const body = rows.map((r) => {
    const tr = h("tr", { class: r.file ? "click" : "", title: r.file ? "" : "Trace not released" },
      h("td", {}, condName(r.condition), h("span", { class: "small muted", style: "margin-left:6px" }, `${r.profile} · s${r.seed}`)),
      h("td", { class: "num" }, signed(r.norm_gain)), h("td", { class: "num" }, r.n_learned ?? "–"));
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
  for (const t of blocked) add("rect", { x: x(t), y: T, width: Math.max(1, x(t + 1) - x(t)), height: H - T - B, fill: "var(--child-soft)" });
  for (const v of [0, 0.5, 1]) add("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "var(--line-2)" });
  add("line", { x1: L, x2: W - R, y1: y(0.8), y2: y(0.8), stroke: "var(--muted)", "stroke-dasharray": "3 3" });
  for (const v of [0, 0.8, 1]) { const tx = add("text", { x: L - 4, y: y(v) + 4, "text-anchor": "end", "font-size": 10 }); tx.textContent = v; }
  for (let t = 0; t <= n; t += Math.max(1, Math.ceil(n / 8))) { const tx = add("text", { x: x(t), y: H - 6, "text-anchor": "middle", "font-size": 10 }); tx.textContent = t; }
  const legend = [];
  order.forEach((sid, i) => {
    const s = series[sid];
    if (s.every((v) => v === s[0])) return;
    add("polyline", { points: s.map((v, t) => `${x(t)},${y(v)}`).join(" "), fill: "none", stroke: COLORS[i % COLORS.length], "stroke-width": 1.6 });
    legend.push(h("span", {}, h("i", { style: `background:${COLORS[i % COLORS.length]}` }), dom.skills[i].name));
  });
  const cursor = add("line", { x1: x(0), x2: x(0), y1: T, y2: H - B, stroke: "var(--agent)", "stroke-width": 1.5 });
  svg.setCursor = (t) => { cursor.setAttribute("x1", x(t)); cursor.setAttribute("x2", x(t)); };
  const wrap = h("div", {}, svg, h("div", { class: "legend" }, legend.length ? legend : h("span", {}, "No skill moved during this session."),
    blocked.size ? h("span", {}, h("i", { style: "background:var(--child-soft);height:8px;border:1px solid var(--child)" }), "turn blocked by prerequisite gate") : null));
  wrap.svg = svg;
  return wrap;
}

async function showTrace(row) {
  const box = $("ex-detail");
  box.replaceChildren(h("div", { class: "empty" }, "Loading…"));
  const trace = await getJSON(row.file);
  const domId = index.groups.find((g) => g.id === row.group).domain;
  const dom = domains[domId] || (domains[domId] = await getJSON(`data/domains/${domId}.json`));
  const skills = Object.fromEntries(dom.skills.map((s) => [s.id, s]));
  const order = dom.skills.map((s) => s.id);
  const anns = trace.annotations || [];
  const dirs = trace.directives || [];
  const tr = trace.transcript || [];
  const n = Math.floor((tr.length - 1) / 2);
  const { series } = trajectory(trace, order);
  const tl = timelineSvg(trace, dom);
  const chat = h("div", { class: "chat", style: "max-height:520px" });
  const bars = h("div");
  const label = h("span", { class: "turn-label" });
  const slider = h("input", { type: "range", min: 0, max: n, value: n, "aria-label": "Turn" });
  const render = (t) => {
    const items = [childOpening(tr[0] ? tr[0].text : "")];
    for (let k = 0; k < t; k++) items.push(...chatTurn(k + 1, tr[1 + 2 * k].text, tr[2 + 2 * k] ? tr[2 + 2 * k].text : null, anns[k], dirs[k]));
    chat.replaceChildren(...items);
    chat.scrollTop = chat.scrollHeight;
    const m = Object.fromEntries(order.map((s) => [s, series[s][Math.min(t, series[s].length - 1)]]));
    const belief = t === n ? trace.final_belief : null;
    bars.replaceChildren(masteryBars(order, skills, m, belief));
    label.textContent = `turn ${t} / ${n}`;
    if (tl.svg.setCursor) tl.svg.setCursor(t);
  };
  slider.addEventListener("input", () => render(Number(slider.value)));
  const g = trace.gain || {};
  const metric = (v, l) => h("div", { class: "metric" }, h("b", {}, v), h("span", {}, l));
  box.replaceChildren(
    h("div", { class: "session-head", style: "padding:0 0 12px;margin-bottom:12px" },
      condName(row.condition),
      h("span", { class: "small muted" }, `${row.profile} profile · seed ${row.seed}`),
      h("a", { href: row.file, download: "", class: "btn", style: "margin-left:auto" }, icon("download"), "JSON")),
    h("div", { class: "metrics", style: "margin-bottom:14px" },
      metric(signed(g.norm_gain), "normalized gain"),
      metric(`${fmt(g.pre, 2)} → ${fmt(g.post, 2)}`, "pre → post"),
      metric((trace.learned_skills || []).length, "skills mastered"),
      metric(fmt(row.blocked_rate, 2), "blocked turns")),
    h("div", { class: "panel-title" }, icon("activity"), "Child's true mastery over turns"), tl,
    h("div", { class: "scrub" }, icon("history"), slider, label),
    h("div", { class: "cols-2", style: "margin-top:8px" },
      h("div", {}, h("div", { class: "panel-title" }, icon("gauge"), "State at this turn"), bars,
        h("p", { class: "note" }, "Tutor belief is shown at the final turn.")),
      h("div", {}, h("div", { class: "panel-title" }, icon("messages-square"), "Transcript"), chat)));
  render(n);
  refreshIcons();
}
export function initExplore(idx) {
  index = idx;
  $("ex-group").replaceChildren(...idx.groups.filter((g) => g.with_trace).map((g) => opt(g.id, `${g.label} (${g.with_trace})`)));
  $("ex-group").addEventListener("change", fillFilters);
  $("ex-cond").addEventListener("change", fillList);
  $("ex-prof").addEventListener("change", fillList);
  fillFilters();
}
