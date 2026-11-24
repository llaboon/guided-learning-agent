import { h, icon, getJSON, refreshIcons, addCopyButtons, REPO } from "./common.js";
import { renderLoop } from "./loop.js";
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
  if (v === "repro") { await initRepro(); addCopyButtons(); }
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
  const body = idx.groups.map((g) => h("tr", {}, h("td", {}, g.label), h("td", { class: "num" }, g.n), h("td", { class: "num" }, g.with_trace),
    h("td", {}, h("span", { class: `pill ${g.status === "new" ? "practice" : ""}` }, g.status === "new" ? "resubmission" : "original"))));
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
  document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => {
    const v = b.dataset.goto;
    history.replaceState(null, "", `#${v}`);
    show(v);
    document.querySelector("main").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  const themeBtn = document.getElementById("theme-btn");
  const syncTheme = () => {
    const dark = document.documentElement.dataset.theme === "dark";
    themeBtn.replaceChildren(icon(dark ? "sun" : "moon"));
    refreshIcons();
  };
  themeBtn.addEventListener("click", () => {
    const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    localStorage.setItem("gla-theme", t);
    syncTheme();
  });
  syncTheme();
  renderLoop(document.getElementById("loop-wrap"));
  show(location.hash.slice(1) || "live");
  refreshIcons();
});
