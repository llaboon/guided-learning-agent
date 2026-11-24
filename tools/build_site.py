"""Build the static GitHub Pages site into ``_site/``.

    python tools/build_site.py [--out _site]

The site is plain HTML/JS. This script adds three generated inputs:

* ``data/``: result summaries, domain graphs and compacted session traces
  for the trace explorer (from ``results/released`` and any
  ``results/<group>/experiment_*.json`` produced by later runs);
* ``py/gla_bundle.zip``: the ``gla`` package, the experiment driver and the
  domain files, loaded by Pyodide for the in-browser live session;
* ``data/manifest.json``: file list with SHA-256 digests.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASED = ROOT / "results" / "released"

# Released v2.4 groups -> (domain, label)
RELEASED_GROUPS = {
    "linear": ("early_math", "Linear domain, 13 skills (main)"),
    "branched": ("early_math_branched", "Branched domain, 21 skills"),
    "alpha_half": ("early_math", "Learning rates x0.5"),
    "alpha_double": ("early_math", "Learning rates x2"),
}
ROW_KEYS = ("condition", "profile", "seed", "pre", "post", "norm_gain",
            "n_learned", "gap_coverage", "leakage_rate", "chitchat_rate",
            "turns", "blocked_rate", "validator_first_pass",
            "validator_final_pass")
# Resubmission phases (results/resub/<phase>/experiment_*.json). Fill-in
# reruns and the validator arm are merged into the group they complete.
PHASES = {
    "main": ("early_math", "Resubmission main run: 8 conditions, linear domain"),
    "branched": ("early_math_branched", "Resubmission branched domain"),
    "softgate": ("early_math", "Live rerun: soft prerequisite gate"),
    "thr09": ("early_math", "Live rerun: mastery threshold 0.9"),
    "xjudge": ("early_math", "Cross-family judge (Gemma 4 31B)"),
    "xtutor": ("early_math", "Cross-family tutor (Gemma 4 31B)"),
}
MERGE = {"main_fill1": "main", "main_fill2": "main", "validated": "main",
         "xjudge_fill": "xjudge"}
TRACE_KEYS = ("condition", "student_profile", "seed", "transcript",
              "directives", "annotations", "state_events", "final_state",
              "final_belief", "pre_scores", "post_scores", "gain",
              "annotation_metrics", "learned_skills", "n_turns",
              "validation_log")


def read(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                 encoding="utf-8")


def find_trace(name: str, dirs: list[Path]) -> Path | None:
    for d in dirs:
        p = d / name
        if p.exists():
            return p
    return None


def add_group(gid, label, domain, rows, trace_dirs, out, index, status):
    entries = []
    for r in rows:
        name = Path(r.get("trace", "")).name
        src = find_trace(name, trace_dirs) if name else None
        entry = {k: r[k] for k in ROW_KEYS if k in r}
        entry["group"] = gid
        if src is not None:
            t = read(src)
            write(out / "data" / "traces" / gid / name,
                  {k: t[k] for k in TRACE_KEYS if k in t})
            entry["file"] = f"data/traces/{gid}/{name}"
        entries.append(entry)
    entries.sort(key=lambda e: (e["condition"], e["profile"], e["seed"]))
    index["groups"].append({"id": gid, "label": label, "domain": domain,
                            "status": status, "n": len(entries),
                            "with_trace": sum("file" in e for e in entries)})
    index["sessions"].extend(entries)
    print(f"[site] {gid}: {len(entries)} rows, "
          f"{sum('file' in e for e in entries)} traces")


def build_data(out: Path) -> None:
    index = {"groups": [], "sessions": []}
    rel_traces = [RELEASED / "results"]
    for gid, (domain, label) in RELEASED_GROUPS.items():
        p = RELEASED / "results" / f"{gid}.json"
        if p.exists():
            add_group(gid, label, domain, read(p)["rows"], rel_traces, out,
                      index, "released")
    xf = RELEASED / "results" / "experiment_qwen3_cross_family.json"
    if xf.exists():
        add_group("qwen3_cross_family", "Cross-family rerun (Qwen3)",
                  "early_math", read(xf)["rows"], rel_traces, out, index,
                  "released")
    # Resubmission phases: results/resub/<phase>/experiment_*.json
    merged, dirs = {}, {}
    for exp in sorted((ROOT / "results" / "resub").glob("*/experiment_*.json")):
        phase = exp.parent.name
        gid = MERGE.get(phase, phase)
        if gid not in PHASES:
            continue
        rows = merged.setdefault(gid, {})
        for r in read(exp)["rows"]:
            rows[(r["condition"], r["profile"], r["seed"])] = r
        dirs.setdefault(gid, []).append(exp.parent)
    for gid, (domain, label) in PHASES.items():
        if gid in merged:
            add_group("resub_" + gid, label, domain, list(merged[gid].values()),
                      dirs[gid], out, index, "new")
    # Show the resubmission main run first when it exists.
    index["groups"].sort(key=lambda g: (g["id"] != "resub_main", g["status"] != "new"))
    write(out / "data" / "index.json", index)

    for name in ("analysis_summary.json", "paired_effects.json"):
        if (RELEASED / name).exists():
            shutil.copy2(RELEASED / name, out / "data" / name)
    for name in ("no_learning_null.json", "qwen3_cross_family_summary.json"):
        p = RELEASED / "results" / name
        if p.exists():
            shutil.copy2(p, out / "data" / name)
    for dom in (ROOT / "data" / "domains").glob("early_math*.json"):
        d = read(dom)
        write(out / "data" / "domains" / dom.name, {
            "domain_id": d["domain_id"], "name": d["name"],
            "skills": [{"id": s["id"], "name": s["name"],
                        "description": s["description"],
                        "prerequisites": s.get("prerequisites", [])}
                       for s in d["skills"]]})


def build_bundle(out: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("gla", "experiments", "data/domains"):
            for p in sorted((ROOT / sub).rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".json"):
                    z.write(p, p.relative_to(ROOT).as_posix())
    target = out / "py" / "gla_bundle.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(buf.getvalue())
    print(f"[site] bundle {len(buf.getvalue()) // 1024} KiB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "_site"))
    out = Path(ap.parse_args().out).resolve()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    build_data(out)
    build_bundle(out)
    manifest = {}
    for p in sorted(out.rglob("*")):
        if p.is_file():
            manifest[p.relative_to(out).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    write(out / "data" / "manifest.json", manifest)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"[site] {len(manifest)} files -> {out}")


if __name__ == "__main__":
    main()
