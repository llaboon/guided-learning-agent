"""Estimate the no-learning null for the state-based pre/post metric.

The test state is held fixed while independent pre- and post-test draws are
sampled.  This quantifies the measurement noise introduced by one item per
skill and the normalized-gain denominator, which is useful when interpreting
small negative gains in prompt-only conditions.

Example
-------
    python experiments/no_learning_null.py --draws 10000 \
        --out paper/aamas/supplement/results/no_learning_null.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gla.assessment import score_by_skill
from gla.knowledge_map import load_domain
from gla.metrics import learning_gain
from gla.student_sim import StudentProfile, StatefulStudentSim
from gla.student_state import GroundTruthState


PROFILES = {
    "zero": [],
    "mid": ["counting_10", "counting_objects", "number_recognition"],
    "beggar": ["counting_10"],
}


def one_draw(kmap, mastered, seed):
    state = GroundTruthState(kmap, mastered=mastered, seed=seed)
    profile = StudentProfile("null", name="null", age=5, mastered=mastered)
    student = StatefulStudentSim(profile, kmap, endpoint=None, state=state,
                                 rng=random.Random(seed + 17))

    # render=False keeps the null CPU-only.  The test is driven directly by
    # the unchanged state and therefore does not invoke an LLM endpoint.
    from gla.assessment import run_state_test
    pre = score_by_skill(run_state_test(student, kmap, form="A", render=False))
    post = score_by_skill(run_state_test(student, kmap, form="B", render=False))
    gaps = set(kmap.skills) - set(mastered)
    return learning_gain(pre, post, target_skills=gaps)


def summarize(values):
    norm = [v["norm_gain"] for v in values]
    abs_gain = [v["abs_gain"] for v in values]

    def stats(xs):
        mean = sum(xs) / len(xs)
        var = sum((x - mean) ** 2 for x in xs) / max(len(xs) - 1, 1)
        ordered = sorted(xs)
        lo = ordered[int(0.025 * len(ordered))]
        hi = ordered[min(int(0.975 * len(ordered)), len(ordered) - 1)]
        return {"mean": mean, "sd": var ** 0.5,
                "q025": lo, "q975": hi, "n": len(xs)}

    return {"norm_gain": stats(norm), "abs_gain": stats(abs_gain)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="early_math")
    parser.add_argument("--draws", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261121)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    kmap = load_domain(args.domain)
    report = {
        "description": "Independent pre/post tests with a fixed ground-truth state",
        "domain": args.domain,
        "draws": args.draws,
        "seed": args.seed,
        "profiles": {},
    }
    for name, mastered in PROFILES.items():
        values = [one_draw(kmap, mastered, args.seed + i)
                  for i in range(args.draws)]
        report["profiles"][name] = {
            "initial_mastered": mastered,
            **summarize(values),
        }

    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
