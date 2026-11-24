import { h, getJSON, refreshIcons, REPO } from "./common.js";
import { initLive } from "./live.js";
import { initResults } from "./results.js";
import { initExplore } from "./explore.js";

const views = ["live", "results", "explore", "repro"];
const inited = new Set();
let index = null;

async function getIndex() {
  if (!index) index = await getJSON("data/index.json");
  return index;
}

async function initView(v) {
  if (inited.has(v)) return;
  inited.add(v);
  if (v === "live") initLive();
  if (v === "results") await initResults(await getIndex());
  if (v === "explore") initExplore(await getIndex());
  if (v === "repro") await initRepro();
  refreshIcons();
}

function show(v) {
  if (!views.includes(v)) v = "live";
  document.querySelectorAll("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === v)));
  document.querySelectorAll("section.view").forEach((s) => s.classList.toggle("active", s.id === `view-${v}`));
  initView(v).catch((e) => console.error(e));
}

async function initRepro() {
  const idx = await getIndex();
  let manifest = {};
  try { manifest = await getJSON("data/manifest.json"); } catch (e) { /* optional */ }
  const head = h("tr", {}, h("th", {}, "Group"), h("th", {}, "Sessions"), h("th", {}, "Traces"), h("th", {}, "Status"));
  const body = idx.groups.map((g) => h("tr", {}, h("td", {}, g.label), h("td", {}, g.n), h("td", {}, g.with_trace),
    h("td", {}, g.status === "new" ? "resubmission run" : "released")));
  document.getElementById("artifact-table").replaceChildren(h("thead", {}, head), h("tbody", {}, body));
  document.getElementById("artifact-note").textContent =
    `${Object.keys(manifest).length} site files with SHA-256 digests in data/manifest.json.`;
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("repo-link").href = REPO;
  document.querySelectorAll(".repo-url").forEach((e) => (e.textContent = REPO + ".git"));
  document.querySelectorAll(".repo-name").forEach((e) => (e.textContent = REPO.split("/").pop()));
  document.querySelectorAll(".repo-file").forEach((e) => (e.href = `${REPO}/blob/main/${e.dataset.path}`));
  document.querySelectorAll("nav.tabs button").forEach((b) => b.addEventListener("click", () => {
    history.replaceState(null, "", `#${b.dataset.view}`);
    show(b.dataset.view);
  }));
  show(location.hash.slice(1) || "live");
  refreshIcons();
});
