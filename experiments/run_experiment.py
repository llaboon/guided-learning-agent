"""Main experiment: 5 tutor conditions x student profiles x seeds.

Measurement follows docs/literature_review.md track E recommendations:
state-driven simulated child (ESS), state-based pre/post learning gain,
per-turn judge annotations (leakage, gap coverage), permutation tests.

Usage:
  python3 experiments/run_experiment.py [--turns 20] [--seeds 1,2] [--workers 6]
                                        [--conditions all|c1,c2] [--render]
"""

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from gla import config
from gla.llm import Endpoint
from gla.knowledge_map import load_domain
from gla.student_state import GroundTruthState
from gla.student_sim import StudentProfile, StatefulStudentSim
from gla.assessment import run_state_test, score_by_skill
from gla.session import run_session, save_trace, CONDITIONS
from gla.metrics import learning_gain, annotation_metrics, learned_skills

PROFILES = [
    StudentProfile("zero", name="乐乐", age=5, mastered=[], attention=0.8),
    StudentProfile("mid", name="朵朵", age=5,
                   mastered=["counting_10", "counting_objects", "number_recognition"],
                   attention=0.9),
    StudentProfile("beggar", name="皮皮", age=5, mastered=["counting_10"],
                   attention=0.85, beg_for_answer=0.4,
                   persona_extra="6. 你特别爱撒娇耍赖，经常想让老师直接告诉你答案。"),
    # Branched-domain profile only: scattered priors across
    # strands -- evidence-based skipping should pay off most here.
    StudentProfile("scatter", name="跳跳", age=5,
                   mastered=["counting_10", "quantity_compare", "shape_basic",
                             "pattern_ab", "position_direction"],
                   attention=0.85),
]


def run_one(condition, profile, seed, kmap, tutor_ep, student_ep, judge_ep,
            turns, render, validator_ep=None, tag=""):
    rng = random.Random(seed * 1000 + sum(ord(c) for c in profile.pid) % 1000)
    state = GroundTruthState(kmap, mastered=profile.mastered, seed=seed)
    student = StatefulStudentSim(profile, kmap, student_ep, state=state, rng=rng)

    pre = run_state_test(student, kmap, form="A", render=render)
    pre_scores = score_by_skill(pre)

    trace = run_session(condition, student, kmap, tutor_ep, judge_ep,
                        max_turns=turns, verbose=False,
                        validator_ep=validator_ep)

    post = run_state_test(student, kmap, form="B", render=render)
    post_scores = score_by_skill(post)

    gaps = set(kmap.skills) - set(profile.mastered)
    gain = learning_gain(pre_scores, post_scores, target_skills=gaps)
    ann_m = annotation_metrics(trace, kmap, profile.mastered)
    trace.update({
        "seed": seed, "pre_scores": pre_scores, "post_scores": post_scores,
        "pre_test": pre, "post_test": post, "gain": gain,
        "annotation_metrics": ann_m, "learned_skills": learned_skills(trace),
    })
    path = save_trace(trace, f"exp{tag}_{condition}_{profile.pid}_s{seed}")
    vlog = trace.get("validation_log") or []
    row = {"condition": condition, "profile": profile.pid, "seed": seed,
           "pre": gain["pre"], "post": gain["post"],
           "abs_gain": gain["abs_gain"], "norm_gain": gain["norm_gain"],
           "n_learned": len(trace["learned_skills"]),
           "learned": ",".join(trace["learned_skills"]),
           "gap_coverage": ann_m["gap_coverage"],
           "leakage_rate": ann_m["leakage_rate"],
           "chitchat_rate": ann_m["chitchat_rate"],
           "turns": trace["n_turns"],
           "validator_first_pass": (round(sum(r["attempts"][0]["ok"] for r in vlog) / len(vlog), 3)
                                    if vlog else None),
           "validator_final_pass": (round(sum(r["final_ok"] for r in vlog) / len(vlog), 3)
                                    if vlog else None),
           "trace": os.path.relpath(path, config.WORK_DIR)}
    return row


def permutation_test(xs, ys, n=20000, seed=7):
    """Two-sided permutation test on difference of means."""
    rng = random.Random(seed)
    obs = sum(xs) / len(xs) - sum(ys) / len(ys)
    pool = list(xs) + list(ys)
    k = len(xs)
    hits = 0
    for _ in range(n):
        rng.shuffle(pool)
        d = sum(pool[:k]) / k - sum(pool[k:]) / (len(pool) - k)
        if abs(d) >= abs(obs) - 1e-12:
            hits += 1
    return obs, hits / n


def aggregate(rows):
    by_cond = {}
    for r in rows:
        by_cond.setdefault(r["condition"], []).append(r)
    summary = {}
    for cond, rs in by_cond.items():
        def mstd(key):
            vals = [r[key] for r in rs]
            m = sum(vals) / len(vals)
            sd = (sum((v - m) ** 2 for v in vals) / max(len(vals) - 1, 1)) ** 0.5
            return round(m, 3), round(sd, 3)
        summary[cond] = {k: mstd(k) for k in
                         ("norm_gain", "abs_gain", "n_learned", "gap_coverage",
                          "leakage_rate", "chitchat_rate")}
        summary[cond]["n_runs"] = len(rs)
    tests = {}
    if "gla_full" in by_cond:
        base_vals = [r["norm_gain"] for r in by_cond["gla_full"]]
        for cond, rs in by_cond.items():
            if cond == "gla_full":
                continue
            obs, p = permutation_test(base_vals, [r["norm_gain"] for r in rs])
            tests[f"gla_full_vs_{cond}"] = {"diff_norm_gain": round(obs, 3),
                                            "p_value": round(p, 4)}
    return summary, tests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=24)
    ap.add_argument("--seeds", default="1,2")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--conditions", default="all")
    ap.add_argument("--profiles", default="all")
    ap.add_argument("--domain", default="early_math",
                    help="domain id under data/domains/ (extension: early_math_branched)")
    ap.add_argument("--alpha-scale", type=float, default=1.0,
                    help="scale all learning-rate alphas (protocol \u00a79 sensitivity)")
    ap.add_argument("--render", action="store_true",
                    help="render test answers with the student LLM (slower)")
    ap.add_argument("--validator-url", default=os.environ.get("GLA_VALIDATOR_URL"),
                    help="OpenAI-compatible endpoint for the directive validator")
    ap.add_argument("--tag", default="", help="suffix for trace/experiment file names")
    args = ap.parse_args()

    if args.alpha_scale != 1.0:
        from gla import student_state as _ss
        for _n in ("ALPHA_TEACH", "ALPHA_PRACTICE_OK",
                   "ALPHA_PRACTICE_TRY", "ALPHA_LEAKED"):
            setattr(_ss, _n, getattr(_ss, _n) * args.alpha_scale)

    seeds = [int(s) for s in args.seeds.split(",")]
    conds = list(CONDITIONS) if args.conditions == "all" else args.conditions.split(",")

    kmap = load_domain(args.domain)
    known = set(kmap.skills)
    if args.profiles == "all":
        cand = list(PROFILES)
    else:
        cand = [p for p in PROFILES if p.pid in args.profiles.split(",")]
    profs = [p for p in cand if p.mastered <= known]
    skipped = [p.pid for p in cand if not p.mastered <= known]
    if skipped:
        print(f"profiles skipped (not in domain {args.domain}): {skipped}", flush=True)
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    tutor_ep = Endpoint(config.TUTOR_BASE_URL, config.TUTOR_MODEL, tag="tutor",
                        log_path=f"{config.RESULTS_DIR}/calls_tutor.jsonl")
    student_ep = Endpoint(config.STUDENT_BASE_URL, config.STUDENT_MODEL,
                          tag="student",
                          log_path=f"{config.RESULTS_DIR}/calls_student.jsonl")
    judge_ep = Endpoint(config.JUDGE_BASE_URL, config.JUDGE_MODEL, tag="judge")
    validator_ep = (Endpoint(args.validator_url, os.environ.get("GLA_VALIDATOR_MODEL"),
                             tag="validator") if args.validator_url else None)
    from gla import student_state as _ss_cfg

    jobs = [(c, p, s) for c in conds for p in profs for s in seeds]
    print(f"total runs: {len(jobs)} (turns={args.turns}, workers={args.workers}, "
          f"gate={_ss_cfg.GATE_MODE}, threshold={_ss_cfg.MASTERED_TRUE}, "
          f"alpha_scale={args.alpha_scale})", flush=True)

    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, c, p, s, kmap, tutor_ep, student_ep, judge_ep,
                          args.turns, args.render, validator_ep,
                          (("_" + args.tag) if args.tag else "")): (c, p.pid, s)
                for (c, p, s) in jobs}
        for fut in as_completed(futs):
            c, pid, s = futs[fut]
            try:
                row = fut.result()
                rows.append(row)
                print(f"[done {len(rows)}/{len(jobs)}] {c}/{pid}/s{s} "
                      f"norm_gain={row['norm_gain']} learned={row['n_learned']} "
                      f"leak={row['leakage_rate']} ({time.time()-t0:.0f}s)",
                      flush=True)
            except Exception as e:  # noqa: BLE001 — keep other runs going
                print(f"[FAIL] {c}/{pid}/s{s}: {type(e).__name__}: {e}", flush=True)

    summary, tests = aggregate(rows)
    out = {"rows": rows, "summary": summary, "tests": tests,
           "config": {"turns": args.turns, "seeds": seeds, "conditions": conds,
                      "profiles": [p.pid for p in profs],
                      "domain": args.domain,
                      "alpha_scale": args.alpha_scale,
                      "gate": _ss_cfg.GATE_MODE,
                      "mastery_threshold": _ss_cfg.MASTERED_TRUE,
                      "tutor_model": tutor_ep.model, "student_model": student_ep.model,
                      "judge_model": judge_ep.model,
                      "validator_model": validator_ep.model if validator_ep else None,
                      "tag": args.tag}}
    out_path = os.path.join(config.RESULTS_DIR,
                            f"experiment{('_' + args.tag) if args.tag else ''}_{int(time.time())}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("\n===== SUMMARY (mean, std) =====")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("===== TESTS =====")
    print(json.dumps(tests, ensure_ascii=False, indent=1))
    print(f"saved -> {out_path}")
    print("EXPERIMENT_DONE")


if __name__ == "__main__":
    main()
