/* Dedicated worker that hosts Pyodide and the unmodified `gla` package.
   Messages in : {type: "init"} | {type: "run", config}
   Messages out: JSON strings emitted by browser_runtime.emit(), plus
                 {type: "ready"} / {type: "error"} objects. */
const PYODIDE_VERSION = "0.28.3";
importScripts(`https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.js`);

let pyodide = null;

async function boot() {
  if (pyodide) return;
  postMessage({ type: "status", text: "Loading Python runtime" });
  pyodide = await loadPyodide();
  postMessage({ type: "status", text: "Loading GLA package" });
  const base = new URL("../py/", self.location.href);
  const zip = await (await fetch(new URL("gla_bundle.zip", base))).arrayBuffer();
  pyodide.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/gla_src" });
  const runtime = await (await fetch(new URL("browser_runtime.py", base))).text();
  pyodide.FS.writeFile("/home/pyodide/gla_src/browser_runtime.py", runtime);
  await pyodide.runPythonAsync(`
import os, sys
os.environ["GLA_WORK_DIR"] = "/home/pyodide/gla_src"
os.environ["GLA_RESULTS_DIR"] = "/tmp/gla_results"
sys.path.insert(0, "/home/pyodide/gla_src")
import browser_runtime
`);
  postMessage({ type: "ready" });
}

self.onmessage = async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") {
      await boot();
    } else if (msg.type === "run") {
      await boot();
      pyodide.globals.set("_cfg_json", JSON.stringify(msg.config));
      // Clear the key from the JS side as soon as Python has a copy.
      msg.config = null;
      await pyodide.runPythonAsync("browser_runtime.run_live(_cfg_json)\ndel _cfg_json");
    }
  } catch (err) {
    let text = String(err && err.message ? err.message : err);
    const m = text.match(/EndpointError: (.*)/);
    if (m) text = m[1];
    else if (text.includes("Traceback")) text = text.trim().split("\n").slice(-1)[0];
    postMessage({ type: "error", text });
  }
};
