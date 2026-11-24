"""Static interface verification for the v2 pipeline (no LLM calls)."""
import inspect
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib

failures = []


def check(desc, fn):
    try:
        fn()
        print(f"[OK]   {desc}")
    except Exception as e:
        failures.append((desc, repr(e)))
        print(f"[FAIL] {desc}: {e!r}")


def sig(obj):
    return str(inspect.signature(obj))


# ---- module imports ----
mods = {}
for name in ["gla.config", "gla.llm", "gla.knowledge_map", "gla.learner_model",
             "gla.planner", "gla.tutor", "gla.metrics", "gla.assessment",
             "gla.annotator", "gla.student_state", "gla.student_sim",
             "gla.session"]:
    check(f"import {name}", lambda n=name: mods.__setitem__(n, importlib.import_module(n)))

# experiments/run_experiment.py imports (module-level PROFILES construction runs here)
check("import experiments.run_experiment",
      lambda: mods.__setitem__("rx", importlib.import_module("experiments.run_experiment")))

if failures:
    print("\nIMPORT FAILURES -- aborting deep checks")
    for d, e in failures:
        print(" -", d, e)
    sys.exit(1)

km = mods["gla.knowledge_map"]
lm_mod = mods["gla.learner_model"]
pl = mods["gla.planner"]
tu = mods["gla.tutor"]
me = mods["gla.metrics"]
As = mods["gla.assessment"]
an = mods["gla.annotator"]
ss = mods["gla.student_state"]
si = mods["gla.student_sim"]
se = mods["gla.session"]
rx = mods["rx"]

# ---- knowledge map ----
kmap = None
def _load():
    global kmap
    kmap = km.load_domain("early_math")
    assert len(kmap.skills) == 13, f"expected 13 skills, got {len(kmap.skills)}"
    assert list(kmap.order), "kmap.order empty"
check("load_domain('early_math') 13 skills + order", _load)
check("Skill.items_of_form('A') on every skill",
      lambda: [sk.items_of_form("A") and sk.items_of_form("B")
               for sk in kmap.skills.values()])
check("Skill has .prerequisites/.name/.description",
      lambda: [(sk.prerequisites, sk.name, sk.description) for sk in kmap.skills.values()])

# ---- llm.Endpoint ----
check(f"Endpoint signature {sig(mods['gla.llm'].Endpoint.__init__)}",
      lambda: inspect.signature(mods["gla.llm"].Endpoint.__init__).bind(
          None, "http://x/v1", None, tag="t", log_path="p"))
check("llm.strip_think exists", lambda: mods["gla.llm"].strip_think)

# ---- learner model ----
def _lm():
    L = lm_mod.LearnerModel(kmap)
    L.taught_boost(next(iter(kmap.skills)))
    assert isinstance(L.summary_text(), str)
    L.snapshot()
check("LearnerModel(kmap) + taught_boost/summary_text/snapshot", _lm)

# ---- planners ----
def _planners():
    L = lm_mod.LearnerModel(kmap)
    for cls in (pl.ZPDPlanner, pl.FixedOrderPlanner):
        p = cls(kmap, L)
        d = p.next_directive()
        assert hasattr(d, "activity") and hasattr(d, "skill_id") and hasattr(d, "to_dict")
        p.observe(d.skill_id or next(iter(kmap.skills)), True)
check("ZPD/FixedOrder planners: ctor(kmap,lm), next_directive, observe, Directive fields", _planners)

# ---- tutors ----
def _tutors():
    assert isinstance(tu.VANILLA_SYSTEM, str) and isinstance(tu.SOCRATIC_SYSTEM, str)
    inspect.signature(tu.BaselineTutor.__init__).bind(None, "ep", "sys_prompt", "name")
    inspect.signature(tu.GLAExecutor.__init__).bind(None, "ep")
    for cls in (tu.BaselineTutor, tu.GLAExecutor):
        inspect.signature(cls.generate).bind(None, [], directive=None, learner_summary=None)
    inspect.signature(tu.grade_session_reply).bind("judge", "skill", "t", "s")
check("tutor.py: BaselineTutor/GLAExecutor/generate kwargs/grade_session_reply", _tutors)

# ---- metrics ----
def _metrics():
    ps = {s: 0.0 for s in kmap.skills}
    qs = {s: 1.0 for s in kmap.skills}
    g = me.learning_gain(ps, qs, target_skills=set(list(kmap.skills)[:5]))
    assert "norm_gain" in g and "abs_gain" in g, g
    trace = {"annotations": [{"skill": list(kmap.skills)[0], "act": "teach",
                              "comprehensible": True, "leaked": False}],
             "state_events": [{"event": "learned", "skill": list(kmap.skills)[0]}]}
    m = me.annotation_metrics(trace, kmap, initial_mastered=[])
    for k in ("gap_coverage", "leakage_rate", "chitchat_rate"):
        assert k in m, (k, m)
    assert me.learned_skills(trace) == [list(kmap.skills)[0]]
check("metrics: learning_gain(target_skills=), annotation_metrics, learned_skills", _metrics)

# ---- ground-truth state + stateful student ----
def _state():
    st = ss.GroundTruthState(kmap, mastered=["counting_10"], seed=1)
    s0 = next(s for s in kmap.order if st.prereqs_ok(s) and not st.is_mastered(s))
    for t in range(60):
        if st.is_mastered(s0):
            break
        st.turn_update({"skill": s0, "act": "both", "comprehensible": True,
                        "leaked": False},
                       drawn_correct=st.answer_correct(s0), turn=t)
    assert st.is_mastered(s0), "teach+practice loop should master"
    assert isinstance(st.answer_correct(s0), bool)
    st.snapshot()
check("GroundTruthState expose->mastered, answer_correct, snapshot", _state)

def _student():
    prof = {q.pid: q for q in rx.PROFILES}["zero"]
    import random
    st = ss.GroundTruthState(kmap, mastered=prof.mastered, seed=1)
    stu = si.StatefulStudentSim(prof, kmap, endpoint=None, state=st,
                                rng=random.Random(0))
    assert hasattr(stu, "respond_v2") and hasattr(stu, "answer_item_v2")
    inspect.signature(stu.respond_v2).bind([], {"skill": None, "act": "chitchat",
                                                "comprehensible": True, "leaked": False})
check("StatefulStudentSim ctor + respond_v2/answer_item_v2 present", _student)

# ---- assessment ----
check(f"run_state_test signature {sig(As.run_state_test)}",
      lambda: inspect.signature(As.run_state_test).bind("stu", kmap, "A", render=False))
check("score_by_skill exists", lambda: As.score_by_skill)

# ---- annotator ----
check("annotate_tutor_turn signature",
      lambda: inspect.signature(an.annotate_tutor_turn).bind("judge", kmap, "text"))
def _parse():
    d = an._parse('{"skill": "counting_10", "act": "both", "comprehensible": true, "leaked": false}', kmap)
    assert d["skill"] == "counting_10" and d["act"] == "both"
check("annotator._parse round-trip", _parse)

# ---- session ----
def _session():
    assert se.CONDITIONS[:5] == ("vanilla", "socratic", "gla_fixed", "gla_reactive", "gla_full"), se.CONDITIONS
    assert {"informed", "gla_full_validated"} <= set(se.CONDITIONS), se.CONDITIONS
    inspect.signature(se.run_session).bind("vanilla", "stu", kmap, "tut", "judge",
                                           max_turns=5, verbose=False)
    inspect.signature(se.build_tutor).bind("gla_full", "ep", kmap, "lm")
check("session: CONDITIONS/run_session/build_tutor signatures", _session)

# ---- run_experiment ----
def _rx():
    profile_ids = {q.pid for q in rx.PROFILES}
    assert {"zero", "mid", "beggar"} <= profile_ids
    assert "scatter" in profile_ids, "branched-domain scatter profile missing"
    inspect.signature(rx.run_one).bind("vanilla", rx.PROFILES[0], 1, kmap,
                                       "t", "s", "j", 20, False)
    obs, p = rx.permutation_test([1.0, 2.0], [0.5, 0.4], n=100)
    assert 0 <= p <= 1
    rows = [{"condition": "vanilla", "norm_gain": 0.1, "abs_gain": 0.1, "n_learned": 1,
             "gap_coverage": 0.5, "leakage_rate": 0.0, "chitchat_rate": 0.2},
            {"condition": "gla_full", "norm_gain": 0.6, "abs_gain": 0.5, "n_learned": 5,
             "gap_coverage": 0.9, "leakage_rate": 0.0, "chitchat_rate": 0.1}]
    summ, tests = rx.aggregate(rows)
    assert "gla_full" in summ
check("run_experiment: PROFILES/run_one/permutation_test/aggregate", _rx)

print()
if failures:
    print(f"INTERFACE_CHECK_FAILED ({len(failures)}):")
    for d, e in failures:
        print(" -", d, "->", e)
    sys.exit(1)
print("INTERFACE_CHECK_PASSED")
