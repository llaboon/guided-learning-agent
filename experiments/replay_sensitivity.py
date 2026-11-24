"""Replay saved tutoring traces under alternative simulator assumptions.

The live tutor policy is held fixed while the ground-truth update rule is
varied. This isolates how much of a reported condition difference is induced
by the simulator's prerequisite gate, learning increments, or mastery
threshold. New traces must contain ``annotations[*].drawn_correct``. Older
traces are accepted when that field is absent, but are reported as unusable.

Example::

    python experiments/replay_sensitivity.py --results-dir results \
        --out paper/aamas/supplement/results/replay_sensitivity.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gla.knowledge_map import load_domain
from gla.student_state import gate_factor


DEFAULT_VARIANTS = [
    {"name": "hard_default", "gate": "hard", "alpha_scale": 1.0, "threshold": 0.8, "redraw": False},
    {"name": "hard_default_redraw", "gate": "hard", "alpha_scale": 1.0, "threshold": 0.8},
    {"name": "soft_min_ratio", "gate": "soft_min", "alpha_scale": 1.0, "threshold": 0.8},
    {"name": "soft_mean_ratio", "gate": "soft_mean", "alpha_scale": 1.0, "threshold": 0.8},
    {"name": "hard_fast", "gate": "hard", "alpha_scale": 0.5, "threshold": 0.8},
    {"name": "hard_slow", "gate": "hard", "alpha_scale": 2.0, "threshold": 0.8},
    {"name": "hard_low_threshold", "gate": "hard", "alpha_scale": 1.0, "threshold": 0.7},
    {"name": "hard_high_threshold", "gate": "hard", "alpha_scale": 1.0, "threshold": 0.9},
    {"name": "no_gate", "gate": "none", "alpha_scale": 1.0, "threshold": 0.8},
    {"name": "soft_min_low_threshold", "gate": "soft_min", "alpha_scale": 1.0, "threshold": 0.7},
    {"name": "teach_heavy", "gate": "hard", "alpha_scale": 1.0, "threshold": 0.8,
     "teach_mult": 2.0, "practice_mult": 0.5},
    {"name": "practice_heavy", "gate": "hard", "alpha_scale": 1.0, "threshold": 0.8,
     "teach_mult": 0.5, "practice_mult": 2.0},
]

CONDS = ("vanilla|socratic|gla_fixed|gla_reactive|gla_full_validated|gla_full"
         "|informed|gla_single_probe")


def _trace_key(path: Path):
    match = re.search(
        r"^exp(?:_[a-z0-9]+)*?_(" + CONDS + r")_([a-z]+)_s(\d+)(?:_\d+)?\.json$",
        path.name,
    )
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def select_latest(results_dir: Path):
    selected = {}
    for path in results_dir.glob("exp_*.json"):
        key = _trace_key(path)
        if key is None:
            continue
        old = selected.get(key)
        if old is None or path.stat().st_mtime > old.stat().st_mtime:
            selected[key] = path
    return selected


def _gate(m, prerequisites, threshold, mode):
    return gate_factor(m, prerequisites, threshold=threshold, mode=mode)


def replay(trace, kmap, variant):
    profile = trace.get("student_profile", {})
    initial = set(profile.get("mastered", []))
    m = {sid: (1.0 if sid in initial else 0.0) for sid in kmap.skills}
    threshold = float(variant["threshold"])
    scale = float(variant["alpha_scale"])
    tm = float(variant.get("teach_mult", 1.0))
    pm = float(variant.get("practice_mult", 1.0))
    alpha_teach = 0.12 * scale * tm
    alpha_ok = 0.25 * scale * pm
    alpha_try = 0.08 * scale * pm
    alpha_leaked = 0.04 * scale * pm
    rng = random.Random(int(trace.get("seed", 0)) + 991)
    redraw = bool(variant.get("redraw", True))
    blocked = 0
    progress = 0.0

    for ann in trace.get("annotations", []):
        sid = ann.get("skill")
        act = ann.get("act")
        if sid not in m or act not in ("teach", "ask", "both"):
            continue
        skill = kmap.skills[sid]
        gate = _gate(m, skill.prerequisites, threshold, variant["gate"])
        if gate == 0.0:
            blocked += 1
            continue
        delta = 0.0
        if act in ("teach", "both"):
            delta += alpha_teach
        if act in ("ask", "both"):
            drawn = ann.get("drawn_correct")
            if redraw and drawn is not None and not ann.get("leaked"):
                # Open-loop replay: the tutor's turns are fixed, but the
                # child's answer is re-drawn from the replayed state.
                p = m[sid] * 0.9 + (1 - m[sid]) * 0.05
                drawn = rng.random() < p
            if ann.get("leaked"):
                delta += alpha_leaked
            elif drawn is True:
                delta += alpha_ok
            elif drawn is False:
                delta += alpha_try
        if delta == 0.0:
            continue
        if not ann.get("comprehensible", True):
            delta *= 0.3
        delta = min(delta * gate, 0.30) + rng.gauss(0.0, 0.02)
        before = m[sid]
        m[sid] = min(1.0, max(0.0, before + delta))
        progress += m[sid] - before

    gaps = [sid for sid in kmap.skills if sid not in initial]
    true_gain = sum(m[sid] for sid in gaps) / len(gaps) if gaps else 0.0
    learned = sum(m[sid] >= threshold for sid in gaps)
    return {
        "true_gain": round(true_gain, 6),
        "n_learned": learned,
        "blocked_rate": round(blocked / max(len(trace.get("annotations", [])), 1), 6),
        "progress": round(progress, 6),
    }


def mean_sd(values):
    if not values:
        return None
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / max(len(values) - 1, 1)
    return {"mean": round(mean, 6), "sd": round(math.sqrt(var), 6), "n": len(values)}


def paired_ci(diffs, seed=7, draws=5000):
    if not diffs:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        means.append(sum(rng.choice(diffs) for _ in diffs) / len(diffs))
    means.sort()
    lo = means[int(0.025 * draws)]
    hi = means[int(0.975 * draws)]
    return {"mean": round(sum(diffs) / len(diffs), 6), "lo": round(lo, 6),
            "hi": round(hi, 6), "n": len(diffs)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--domain", default="early_math")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    selected = {}
    for d in args.results_dir.split(","):
        selected.update(select_latest(Path(d)))
    usable, skipped = [], []
    for key, path in selected.items():
        trace = json.loads(path.read_text(encoding="utf-8"))
        if not trace.get("annotations") or "drawn_correct" not in trace["annotations"][0]:
            skipped.append(str(path))
            continue
        usable.append((key, trace, path))

    kmap = load_domain(args.domain)
    report = {"domain": args.domain, "n_selected": len(selected),
              "n_usable": len(usable), "n_skipped": len(skipped),
              "skipped": skipped, "variants": {}}
    for variant in DEFAULT_VARIANTS:
        rows = []
        for (condition, profile, seed), trace, path in usable:
            result = replay(trace, kmap, variant)
            rows.append({"condition": condition, "profile": profile, "seed": seed,
                         "trace": str(path), **result})
        by_condition = defaultdict(list)
        for row in rows:
            by_condition[row["condition"]].append(row)
        summary = {}
        for condition, condition_rows in by_condition.items():
            summary[condition] = {metric: mean_sd([r[metric] for r in condition_rows])
                                  for metric in ("true_gain", "n_learned", "blocked_rate")}
        pairwise = {}
        for baseline in ("vanilla", "socratic", "informed", "gla_fixed",
                         "gla_reactive", "gla_single_probe", "gla_full_validated"):
            full = {(r["profile"], r["seed"]): r for r in by_condition.get("gla_full", [])}
            base = {(r["profile"], r["seed"]): r for r in by_condition.get(baseline, [])}
            keys = sorted(set(full) & set(base))
            if not keys:
                continue
            pairwise[f"gla_full_vs_{baseline}"] = {
                metric: paired_ci([full[k][metric] - base[k][metric] for k in keys])
                for metric in ("true_gain", "n_learned", "blocked_rate")
            }
        report["variants"][variant["name"]] = {
            "config": variant, "summary": summary, "pairwise": pairwise,
            "rows": rows,
        }

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
