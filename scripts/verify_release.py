"""Check that the released result files are internally consistent (CPU only).

    python scripts/verify_release.py

For every result group it checks that each summary row has a trace, that the
trace's condition/profile/seed/gain match the row, that the trace has the
expected number of tutor turns, and that the per-condition means in
``results/released/analysis_summary.json`` are reproduced from the rows.
Resubmission traces must also log ``drawn_correct`` on every annotation,
which the replay sensitivity analysis depends on.
"""

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "results" / "released"
RESUB = ROOT / "results" / "resub"
problems = []


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def check_rows(label, rows, trace_dirs, need_drawn):
    n_ok = 0
    for r in rows:
        name = Path(r["trace"]).name
        path = next((d / name for d in trace_dirs if (d / name).exists()), None)
        if path is None:
            problems.append(f"{label}: missing trace {name}")
            continue
        t = read(path)
        if (t["condition"], t["student_profile"]["pid"], t["seed"]) != (r["condition"], r["profile"], r["seed"]):
            problems.append(f"{label}: key mismatch in {name}")
        if abs(t["gain"]["norm_gain"] - r["norm_gain"]) > 1e-9:
            problems.append(f"{label}: gain mismatch in {name}")
        if t["n_turns"] != r["turns"]:
            problems.append(f"{label}: turn count mismatch in {name}")
        if need_drawn and any("drawn_correct" not in a for a in t["annotations"]):
            problems.append(f"{label}: drawn_correct missing in {name}")
        n_ok += 1
    print(f"[{label}] {n_ok}/{len(rows)} traces consistent")


def main():
    summary = read(REL / "analysis_summary.json")
    for group in ("linear", "branched", "alpha_half", "alpha_double"):
        rows = read(REL / "results" / f"{group}.json")["rows"]
        check_rows(group, rows, [REL / "results"], need_drawn=False)
        for cond, stats in summary[group]["stats"].items():
            xs = [r["norm_gain"] for r in rows if r["condition"] == cond]
            if abs(st.mean(xs) - stats["norm_gain"]["mean"]) > 1e-9:
                problems.append(f"{group}/{cond}: summary mean differs")
    if RESUB.exists():
        for exp in sorted(RESUB.glob("*/experiment_*.json")):
            rows = read(exp)["rows"]
            check_rows(f"resub/{exp.parent.name}", rows, [exp.parent],
                       need_drawn=True)
    for p in problems:
        print("[problem]", p)
    print("RELEASE_VERIFY_" + ("FAILED" if problems else "PASSED"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
