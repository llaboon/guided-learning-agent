"""Offline dry run of the full experiment pipeline with mock endpoints.

Exercises run_one end-to-end (pre-test -> session loop -> post-test ->
metrics -> aggregation -> JSON dump) for every condition without any LLM.
The mock tutor teaches skills in topo order (teach, teach, ask), so the
oracle-like transcript should produce clear learning under all conditions.
"""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gla.knowledge_map import load_domain
from experiments import run_experiment as rx


class MockEndpoint:
    """Stands in for gla.llm.Endpoint; routes on prompt content."""

    def __init__(self, kmap, tag):
        self.kmap = kmap
        self.tag = tag
        self.rng = random.Random(42)
        self._script = []            # (skill, phase) queue for the tutor
        for sid in kmap.order:
            self._script += [(sid, "teach"), (sid, "teach"), (sid, "ask")]
        self._i = 0

    def chat(self, messages, **kw):
        sysmsg = messages[0]["content"] if messages else ""
        user = messages[-1]["content"] if messages else ""
        if "标注员" in sysmsg:                      # judge: per-turn annotation
            return self._annotate(user)
        if "教学观察员" in sysmsg:                  # judge: grade a reply
            return self.rng.choice(["对", "错"])
        if self.tag == "student":                   # renderer chitchat paths
            return self.rng.choice(["嗯嗯！", "好呀好呀。", "哦……"])
        return self._tutor_turn()                   # tutor under any condition

    def _tutor_turn(self):
        sid, phase = self._script[min(self._i, len(self._script) - 1)]
        self._i += 1
        name = self.kmap.skills[sid].name
        if phase == "teach":
            return f"我们来学{name}。你看，老师示范一遍：MOCK[{sid}]。"
        return f"轮到你啦，试试这道{name}的题：MOCK[{sid}]，等于几呀？"

    def _annotate(self, user_text):
        import re
        m = re.search(r"MOCK\[(\w+)\]", user_text)
        sid = m.group(1) if m else None
        act = "ask" if "等于几" in user_text else "teach"
        expected = "3" if act == "ask" else None
        return json.dumps({"skill": sid, "act": act, "comprehensible": True,
                           "leaked": False, "expected": expected},
                          ensure_ascii=False)


def main():
    kmap = load_domain("early_math")
    rows = []
    from gla.session import CONDITIONS
    for cond in CONDITIONS:
        for prof in rx.PROFILES:
            ep_t = MockEndpoint(kmap, "tutor")
            ep_s = MockEndpoint(kmap, "student")
            ep_j = MockEndpoint(kmap, "judge")
            row = rx.run_one(cond, prof, 1, kmap, ep_t, ep_s, ep_j,
                             turns=12, render=False,
                             validator_ep=MockEndpoint(kmap, "validator"))
            rows.append(row)
            print(f"[dry] {cond:9s} {prof.pid:6s} pre={row['pre']:.2f} "
                  f"post={row['post']:.2f} ng={row['norm_gain']:.2f} "
                  f"learned={row['n_learned']} cover={row['gap_coverage']:.2f} "
                  f"leak={row['leakage_rate']:.2f}")
    summary, tests = rx.aggregate(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("tests:", json.dumps(tests, ensure_ascii=False))
    print("DRYRUN_OK")


if __name__ == "__main__":
    main()
