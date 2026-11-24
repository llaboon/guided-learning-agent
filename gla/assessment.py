"""Pre/post testing and answer grading (rule-based fast path + LLM judge fallback)."""

import re

from .llm import strip_think

_CN_DIGITS = {"零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
              "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}


def _normalize_numbers(text):
    out = text
    for cn, ar in _CN_DIGITS.items():
        out = out.replace(cn, ar)
    return out


def _extract_numbers(text):
    return re.findall(r"\d+", _normalize_numbers(text))


def grade_answer(question, expected, reply, judge=None):
    """Return True/False (correct), using rules first, judge fallback."""
    reply = (reply or "").strip()
    if not reply:
        return False
    exp_norm = _normalize_numbers(expected.strip())
    if exp_norm.isdigit():
        nums = _extract_numbers(reply)
        if nums:
            return nums[-1] == exp_norm  # children restate; last number ≈ final answer
        if judge is None:
            return False
    else:
        if exp_norm in _normalize_numbers(reply):
            return True
        if judge is None:
            return False
    verdict = strip_think(judge.chat(
        [{"role": "system",
          "content": "你是判卷老师。判断孩子的回答是否答对了问题。只输出一个字：对 或 错。"},
         {"role": "user",
          "content": f"问题：{question}\n标准答案：{expected}\n孩子的回答：{reply}\n孩子答对了吗？"}],
        temperature=0.0, max_tokens=512))
    return verdict.strip().startswith("对")


def run_test(student, kmap, form, transcript=None, judge=None, skills=None):
    """Administer all items of a form. Returns {skill_id: [(q, reply, correct), ...]}."""
    results = {}
    for sid in (skills or kmap.order):
        skill = kmap.skills[sid]
        rows = []
        for item in skill.items_of_form(form):
            reply = student.answer_item(item["q"], transcript=transcript)
            ok = grade_answer(item["q"], item["a"], reply, judge=judge)
            rows.append({"q": item["q"], "expected": item["a"],
                         "reply": reply, "correct": bool(ok)})
        results[sid] = rows
    return results


def score_by_skill(test_results):
    return {sid: (sum(r["correct"] for r in rows) / len(rows) if rows else 0.0)
            for sid, rows in test_results.items()}


def run_state_test(student, kmap, form, render=True):
    """v2 testing: correctness sampled from the ground-truth state; the LLM
    only renders the child's wording (kept for trace realism)."""
    results = {}
    for sid in kmap.order:
        skill = kmap.skills[sid]
        rows = []
        for item in skill.items_of_form(form):
            ok = student.state.answer_correct(sid)
            reply = (student.answer_item_v2(item["q"], item["a"], ok)
                     if render else "")
            rows.append({"q": item["q"], "expected": item["a"],
                         "reply": reply, "correct": bool(ok)})
        results[sid] = rows
    return results
