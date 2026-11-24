import io, sys
sys.path.insert(0, ".")
from gla.knowledge_map import load_domain
from gla.learner_model import LearnerModel
from gla.planner import ZPDPlanner

km = load_domain()
root = km.order[0]

# Case 1: single lucky pass must NOT fast-forward mastery.
lm = LearnerModel(km)
pl = ZPDPlanner(km, lm)
d1 = pl.next_directive(); assert (d1.activity, d1.skill_id) == ("diagnose", root), d1.to_dict()
pl.observe(root, True)
assert root not in lm.mastered_ids(), "one pass must not master"
d2 = pl.next_directive(); assert (d2.activity, d2.skill_id) == ("diagnose", root), d2.to_dict()
pl.observe(root, False)
assert root not in lm.mastered_ids()
d3 = pl.next_directive(); assert (d3.activity, d3.skill_id) == ("teach", root), d3.to_dict()
print("case1 lucky-guess contained:", d1.activity, d2.activity, d3.activity)

# Case 2: two consecutive passes fast-forward in exactly 2 turns.
lm = LearnerModel(km)
pl = ZPDPlanner(km, lm)
pl.next_directive(); pl.observe(root, True)
pl.next_directive(); pl.observe(root, True)
assert root in lm.mastered_ids(), "double pass must master"
d = pl.next_directive()
assert d.skill_id != root, d.to_dict()
print("case2 double-pass fast-forward ok; next ->", d.activity, d.skill_id)

# Case 3: probes that never return evidence stop after MAX_DIAG_ATTEMPTS.
lm = LearnerModel(km)
pl = ZPDPlanner(km, lm)
acts = []
for _ in range(pl.MAX_DIAG_ATTEMPTS + 1):
    d = pl.next_directive(); acts.append(d.activity)  # no observe(): drifted
assert acts[:pl.MAX_DIAG_ATTEMPTS] == ["diagnose"] * pl.MAX_DIAG_ATTEMPTS, acts
assert acts[-1] == "teach", acts
print("case3 probe attempts bounded:", acts)
print("PROBE_TEST_PASS")
