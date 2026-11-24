"""Outcome metrics: learning gain, coverage, efficiency."""


def learning_gain(pre_scores, post_scores, target_skills=None):
    """Absolute and normalized gain over (target) skills."""
    sids = list(target_skills or pre_scores.keys())
    pre = sum(pre_scores[s] for s in sids) / len(sids)
    post = sum(post_scores[s] for s in sids) / len(sids)
    norm = (post - pre) / (1 - pre) if pre < 1.0 else 0.0
    return {"pre": round(pre, 3), "post": round(post, 3),
            "abs_gain": round(post - pre, 3), "norm_gain": round(norm, 3)}


def per_skill_gain(pre_scores, post_scores):
    return {s: round(post_scores[s] - pre_scores[s], 3) for s in pre_scores}


def curriculum_coverage(trace, kmap):
    """Fraction of skills the tutor actually addressed (GLA conditions only)."""
    touched = {d["skill"] for d in trace.get("directives", []) if d.get("skill")}
    return {"touched": sorted(touched),
            "coverage": round(len(touched) / len(kmap.skills), 3)}


def efficiency(trace, gain):
    n = max(trace.get("n_turns", 1), 1)
    return {"turns": n, "gain_per_10turns": round(gain["abs_gain"] / n * 10, 4)}


def annotation_metrics(trace, kmap, initial_mastered):
    """Condition-agnostic metrics from per-turn judge annotations.

    gap_coverage: 主动触达率 —— touched∩初始缺口 / 初始缺口（track E 建议的
    "主动引导"直接度量，分母为预置知识缺口集合）。
    """
    anns = trace.get("annotations", [])
    touched = {a["skill"] for a in anns if a.get("skill")}
    gaps = set(kmap.skills) - set(initial_mastered)
    substantive = [a for a in anns if a["act"] in ("teach", "ask", "both")]
    leaked = sum(1 for a in substantive if a.get("leaked"))
    return {
        "touched_skills": sorted(touched),
        "coverage_all": round(len(touched) / len(kmap.skills), 3),
        "gap_coverage": round(len(touched & gaps) / len(gaps), 3) if gaps else 1.0,
        "substantive_turns": len(substantive),
        "chitchat_rate": round(1 - len(substantive) / max(len(anns), 1), 3),
        "leakage_rate": round(leaked / max(len(substantive), 1), 3),
    }


def learned_skills(trace):
    ev = trace.get("state_events", [])
    return sorted({e["skill"] for e in ev if e["event"] == "learned"})
