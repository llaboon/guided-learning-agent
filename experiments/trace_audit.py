"""CPU-only audit of the released v2.4 linear-domain traces.

Produces two supplementary analyses used in the resubmission:

1. Directive compliance of the prompt-enforced executor (reviewer a7k4,
   point 3).  For every GLA turn we compare the planner directive with the
   blind per-turn annotation that drives the simulator, using the same rules
   as ``gla.tutor.DirectiveValidator``:
     * the annotated skill must equal the directed skill;
     * diagnose/practice turns must pose a question (act ask/both) and must
       not leak its answer;
     * teach turns must not pose a practice question (act teach);
     * diagnose turns should not demonstrate (act ask, not both).
   The rates are annotator-measured and inherit the annotator's act-label
   noise (62.8% act agreement with the 122B re-annotation).

2. Initial batch (seeds 1-3) versus extension batch (seeds 4-5) paired
   effects (reviewer qKCP, point 3), with exact sign-flip p-values per batch.

Usage:
    python experiments/trace_audit.py \
        --results paper/aamas/supplement/results \
        --out paper/aamas/supplement/results/trace_audit.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
from collections import defaultdict
from pathlib import Path

GLA_CONDITIONS = ("gla_fixed", "gla_reactive", "gla_full")
BASELINES = ("vanilla", "socratic", "gla_fixed", "gla_reactive")
PROFILES = ("zero", "mid", "beggar")


def turn_checks(directive, ann):
    act, skill = directive["activity"], directive.get("skill")
    out = {"skill_match": ann.get("skill") == skill}
    if act in ("diagnose", "practice"):
        out["poses_question"] = ann.get("act") in ("ask", "both")
        out["no_leak"] = not ann.get("leaked")
    if act == "teach":
        out["no_practice_task"] = ann.get("act") not in ("ask", "both")
    if act == "diagnose":
        out["no_demonstration"] = ann.get("act") == "ask"
    keys = [k for k in out if k != "no_demonstration"]
    out["all_core_rules"] = all(out[k] for k in keys)
    return out


def compliance(rows, results_dir):
    counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if row["condition"] not in GLA_CONDITIONS:
            continue
        trace = json.loads((results_dir / Path(row["trace"]).name)
                           .read_text(encoding="utf-8"))
        for d, a in zip(trace["directives"], trace["annotations"]):
            if d["activity"] == "end":
                continue
            key = (row["condition"], d["activity"])
            counts[key]["n"] += 1
            for name, ok in turn_checks(d, a).items():
                counts[key][name] += int(ok)
    report = {}
    for (cond, act), c in sorted(counts.items()):
        n = c["n"]
        report.setdefault(cond, {})[act] = {
            "n_turns": n,
            **{k: round(v / n, 4) for k, v in c.items() if k != "n"},
        }
    return report


def exact_signflip(diffs):
    obs = abs(sum(diffs))
    hits = total = 0
    for signs in itertools.product((1, -1), repeat=len(diffs)):
        total += 1
        hits += abs(sum(s * d for s, d in zip(signs, diffs))) >= obs - 1e-12
    return hits / total


def batch_split(rows):
    value = {(r["condition"], r["profile"], r["seed"]): r for r in rows}
    out = {}
    for label, seeds in (("seeds_1_3", (1, 2, 3)), ("seeds_4_5", (4, 5)),
                         ("combined", (1, 2, 3, 4, 5))):
        out[label] = {}
        for base in BASELINES:
            for metric in ("norm_gain", "n_learned"):
                diffs = [value[("gla_full", p, s)][metric]
                         - value[(base, p, s)][metric]
                         for p in PROFILES for s in seeds]
                out[label].setdefault(f"gla_full_vs_{base}", {})[metric] = {
                    "n_blocks": len(diffs),
                    "mean_difference": round(statistics.mean(diffs), 4),
                    "n_positive": sum(d > 0 for d in diffs),
                    "exact_signflip_p": round(exact_signflip(diffs), 5),
                }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="paper/aamas/supplement/results")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    results_dir = Path(args.results)
    rows = json.loads((results_dir / "linear.json")
                      .read_text(encoding="utf-8"))["rows"]
    report = {
        "dataset": "v2.4 linear final, 75 sessions",
        "directive_compliance": compliance(rows, results_dir),
        "compliance_note": ("annotator-measured; act labels have 62.8% "
                            "agreement with the 122B re-annotation"),
        "batch_split": batch_split(rows),
    }
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
