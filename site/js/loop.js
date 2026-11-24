/* GLA loop diagram (inline SVG). setLoopStep(activity) highlights the path
   of the current turn during a live session. */
const NS = "http://www.w3.org/2000/svg";
const NODES = {
  domain:   { x: 10,  y: 18,  w: 128, label: "Domain", sub: "skills, prerequisites" },
  planner:  { x: 176, y: 18,  w: 128, label: "Planner", sub: "next directive" },
  executor: { x: 342, y: 18,  w: 128, label: "Executor", sub: "LLM turn + validator" },
  child:    { x: 342, y: 142, w: 128, label: "Simulated child", sub: "true mastery m", cls: "child" },
  filter:   { x: 176, y: 142, w: 128, label: "Evidence filter", sub: "on-skill, not leaked" },
  learner:  { x: 10,  y: 142, w: 128, label: "Learner model", sub: "Beta beliefs" },
};
const H = 52;
const EDGES = [
  ["domain", "planner", "r", ""],
  ["planner", "executor", "r", "directive"],
  ["executor", "child", "d", "tutor turn"],
  ["child", "filter", "l", "answer"],
  ["filter", "learner", "l", "evidence"],
  ["learner", "planner", "u", "belief"],
];
let svg = null;

function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.append(e);
  return e;
}

function anchor(n, side) {
  const b = NODES[n];
  if (side === "r") return [b.x + b.w, b.y + H / 2];
  if (side === "l") return [b.x, b.y + H / 2];
  if (side === "t") return [b.x + b.w / 2, b.y];
  return [b.x + b.w / 2, b.y + H];
}

export function renderLoop(host) {
  svg = el("svg", { viewBox: "0 0 480 222", class: "loop-fig", role: "img",
    "aria-label": "GLA loop: domain and learner model feed the planner, which directs the executor; the child's answer passes the evidence filter into the learner model." });
  const defs = el("defs", {}, svg);
  const m = el("marker", { id: "arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
  el("path", { d: "M0,0 L10,5 L0,10 z", fill: "currentColor" }, m).style.fill = "var(--muted)";
  el("rect", { x: 160, y: 4, width: 156, height: 214, rx: 8, class: "frame" }, svg);
  const fl = el("text", { x: 238, y: 214, "text-anchor": "middle", class: "frame-label" }, svg);
  fl.textContent = "never sees the true state";
  for (const [a, b, dir, label] of EDGES) {
    let p;
    if (dir === "r") { const s = anchor(a, "r"), t = anchor(b, "l"); p = `M${s[0]},${s[1]} L${t[0] - 2},${t[1]}`; }
    else if (dir === "l") { const s = anchor(a, "l"), t = anchor(b, "r"); p = `M${s[0]},${s[1]} L${t[0] + 2},${t[1]}`; }
    else if (dir === "d") { const s = anchor(a, "b"), t = anchor(b, "t"); p = `M${s[0]},${s[1]} L${t[0]},${t[1] - 2}`; }
    else { const s = anchor(a, "t"), t = anchor(b, "b"); p = `M${s[0]},${s[1]} C${s[0]},${s[1] - 40} ${t[0] - 40},${t[1] + 30} ${t[0] - 20},${t[1] + 2}`; }
    el("path", { d: p, class: "edge", "data-edge": `${a}-${b}` }, svg);
    if (label) {
      let lx, ly;
      if (dir === "d") { lx = anchor(a, "b")[0] + 6; ly = 105; }
      else if (dir === "u") { lx = 116; ly = 112; }
      else { lx = (anchor(a, dir === "r" ? "r" : "l")[0] + anchor(b, dir === "r" ? "l" : "r")[0]) / 2; ly = NODES[a].y + H / 2 - 7; }
      const t = el("text", { x: lx, y: ly, "text-anchor": dir === "d" ? "start" : "middle", class: "elabel" }, svg);
      t.textContent = label;
    }
  }
  for (const [id, n] of Object.entries(NODES)) {
    const g = el("g", { class: `node ${n.cls || ""}`, "data-node": id }, svg);
    el("rect", { x: n.x, y: n.y, width: n.w, height: H, rx: 7 }, g);
    const t = el("text", { x: n.x + 12, y: n.y + 22 }, g); t.textContent = n.label;
    const s = el("text", { x: n.x + 12, y: n.y + 39, class: "sub" }, g); s.textContent = n.sub;
  }
  host.replaceChildren(svg);
}

const PATHS = {
  diagnose: ["planner", "executor", "child", "filter", "learner"],
  practice: ["planner", "executor", "child", "filter", "learner"],
  teach: ["planner", "executor", "child"],
  prompt: ["executor", "child"],
};

export function setLoopStep(activity) {
  if (!svg) return;
  const path = activity ? PATHS[activity] || PATHS.prompt : [];
  svg.querySelectorAll(".node").forEach((g) => g.classList.toggle("on", path.includes(g.dataset.node)));
  svg.querySelectorAll(".edge").forEach((e) => {
    const [a, b] = e.dataset.edge.split("-");
    const i = path.indexOf(a);
    e.classList.toggle("flow", i >= 0 && path[i + 1] === b);
  });
}
