"""v2.1 harness validation (protocol §7), all offline — no LLM needed.

V1' Template-answer/grading consistency: composed replies grade exactly as
    the state-drawn correctness.
V2' Zero-teaching drift: chitchat/no-skill turns never move the state.
V3' Oracle upper bound: topo-order teach+practice masters all skills with
    zero blocked events in a bounded number of turns; out-of-order teaching
    is blocked by the prerequisite gate.
V4' Slip/guess calibration: empirical test accuracy matches nominal rates.
"""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gla import config
from gla.knowledge_map import load_domain
from gla.student_state import GroundTruthState, MASTERED_TRUE
from gla.student_sim import wrong_answer_text, compose_child_answer
from gla.assessment import grade_answer

SEED = config.SEED


def _ann(skill, act, comprehensible=True, leaked=False):
    return {"skill": skill, "act": act,
            "comprehensible": comprehensible, "leaked": leaked}


def v1_template_consistency(kmap, n=300):
    rng = random.Random(SEED)
    items = [(sid, it) for sid, sk in kmap.skills.items() for it in sk.items]
    agree = 0
    for _ in range(n):
        sid, item = items[rng.randrange(len(items))]
        correct = rng.random() < 0.5
        ans = item["a"] if correct else wrong_answer_text(item["a"], item["q"], rng)
        reply = compose_child_answer(correct, ans, rng)
        graded = grade_answer(item["q"], item["a"], reply, judge=None)
        agree += (graded == correct)
    rate = agree / n
    print(f"[V1'] template-vs-grade agreement: {agree}/{n} = {rate:.2%}")
    return rate


def v2_zero_drift(kmap):
    st = GroundTruthState(kmap, mastered=["counting_10"], seed=SEED)
    before = dict(st.m)
    for t in range(48):
        st.turn_update(_ann(None, "chitchat"), turn=t)
        st.turn_update(_ann("counting_10", "chitchat"), turn=t)
        st.turn_update(_ann(None, "teach"), turn=t)
    drift = max(abs(st.m[s] - before[s]) for s in st.m)
    ok = drift == 0.0
    print(f"[V2'] zero-teaching drift after 144 idle updates: {drift} -> "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def v3_oracle(kmap, max_turns=250):
    st = GroundTruthState(kmap, mastered=[], seed=SEED)
    turns = 0
    for sid in kmap.order:
        taught = 0
        while not st.is_mastered(sid) and turns < max_turns:
            if taught < 2:
                st.turn_update(_ann(sid, "teach"), turn=turns)
                taught += 1
            else:
                st.turn_update(_ann(sid, "ask"),
                               drawn_correct=st.answer_correct(sid), turn=turns)
            turns += 1
    blocked = sum(1 for e in st.events if e["event"] == "blocked_prereq")
    all_m = len(st.mastered) == len(kmap.skills)
    # out-of-order teaching must be blocked:
    st2 = GroundTruthState(kmap, mastered=[], seed=SEED)
    deep = [s for s in kmap.order if kmap.skills[s].prerequisites][-1]
    for t in range(4):
        st2.turn_update(_ann(deep, "teach"), turn=t)
    gate_ok = st2.m[deep] == 0.0 and any(
        e["event"] == "blocked_prereq" for e in st2.events)
    print(f"[V3'] oracle: mastered {len(st.mastered)}/{len(kmap.skills)} in "
          f"{turns} turns, blocked={blocked}; prereq gate holds={gate_ok}")
    return all_m and blocked == 0 and gate_ok and turns < max_turns


def v4_slip_guess(kmap, n=20000):
    st = GroundTruthState(kmap, mastered=["counting_10"], seed=SEED)
    acc_m = sum(st.answer_correct("counting_10") for _ in range(n)) / n
    unm = next(s for s in kmap.order if s != "counting_10")
    acc_u = sum(st.answer_correct(unm) for _ in range(n)) / n
    ok = abs(acc_m - (1 - st.SLIP)) < 0.02 and abs(acc_u - st.GUESS) < 0.02
    print(f"[V4'] mastered acc={acc_m:.3f} (nominal {1-st.SLIP}), "
          f"unmastered acc={acc_u:.3f} (nominal {st.GUESS}) -> {'OK' if ok else 'FAIL'}")
    return ok


def main():
    kmap = load_domain("early_math")
    print(f"domain={kmap.domain_id} skills={len(kmap.skills)} "
          f"mastery_threshold={MASTERED_TRUE}")
    r1 = v1_template_consistency(kmap)
    r2 = v2_zero_drift(kmap)
    r3 = v3_oracle(kmap)
    r4 = v4_slip_guess(kmap)
    result = {"v1_template_agreement": r1, "v2_zero_drift_ok": bool(r2),
              "v3_oracle_ok": bool(r3), "v4_slip_guess_ok": bool(r4)}
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    path = os.path.join(config.RESULTS_DIR, "state_validation.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"saved -> {path}")
    verdict = "PASS" if (r1 >= 0.98 and r2 and r3 and r4) else "CHECK_NEEDED"
    print(f"STATE_VALIDATION_{verdict}")


if __name__ == "__main__":
    main()
