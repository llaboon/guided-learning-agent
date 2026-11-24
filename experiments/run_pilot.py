"""Pilot run: validate the full pipeline plumbing with 1 student × 2 conditions.

Usage:  python3 experiments/run_pilot.py [max_turns]
"""

import json
import random
import sys

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from gla import config
from gla.llm import Endpoint
from gla.knowledge_map import load_domain
from gla.student_sim import StudentProfile, StudentSim
from gla.assessment import run_test, score_by_skill
from gla.session import run_session, save_trace
from gla.metrics import learning_gain, per_skill_gain, curriculum_coverage, efficiency


def main():
    max_turns = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    kmap = load_domain("early_math")
    print(f"domain={kmap.domain_id} skills={len(kmap.skills)}")

    tutor_ep = Endpoint(config.TUTOR_BASE_URL, config.TUTOR_MODEL, tag="tutor",
                        log_path=f"{config.RESULTS_DIR}/calls_tutor.jsonl")
    student_ep = Endpoint(config.STUDENT_BASE_URL, config.STUDENT_MODEL, tag="student",
                          log_path=f"{config.RESULTS_DIR}/calls_student.jsonl")
    judge_ep = tutor_ep
    print(f"tutor={tutor_ep.model} student={student_ep.model}")

    profile = StudentProfile("pilot01", name="乐乐", age=5,
                             mastered=["counting_10"], attention=0.9)

    report = {}
    for condition in ("vanilla", "gla_full"):
        print(f"\n===== condition: {condition} =====")
        rng = random.Random(config.SEED)
        student = StudentSim(profile, kmap, student_ep, rng=rng)

        pre = run_test(student, kmap, form="A", judge=judge_ep)
        pre_scores = score_by_skill(pre)
        print("pre :", pre_scores)

        trace = run_session(condition, student, kmap, tutor_ep, judge_ep,
                            max_turns=max_turns)

        post = run_test(student, kmap, form="B",
                        transcript=trace["transcript"], judge=judge_ep)
        post_scores = score_by_skill(post)
        print("post:", post_scores)

        gain = learning_gain(pre_scores, post_scores)
        trace.update({"pre_test": pre, "post_test": post,
                      "pre_scores": pre_scores, "post_scores": post_scores,
                      "gain": gain,
                      "per_skill_gain": per_skill_gain(pre_scores, post_scores),
                      "coverage": curriculum_coverage(trace, kmap),
                      "efficiency": efficiency(trace, gain)})
        path = save_trace(trace, f"pilot_{condition}")
        print(f"gain={gain} coverage={trace['coverage']['coverage']} -> {path}")
        report[condition] = {"gain": gain, "coverage": trace["coverage"],
                             "efficiency": trace["efficiency"]}

    print("\n===== PILOT SUMMARY =====")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("PILOT_DONE")


if __name__ == "__main__":
    main()
