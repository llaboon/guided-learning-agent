"""Per-turn annotation of tutor utterances by the judge model.

One judge call per tutor turn powers: ground-truth state updates,
student rendering directives, leakage metric and coverage metric --
uniformly across all tutor conditions.
"""

import json
import re

from .llm import strip_think


def _skill_menu(kmap):
    return "\n".join(f"- {sid}: {s.name}（{s.description}）"
                     for sid, s in kmap.skills.items())


ANNOTATE_SYSTEM = """你是教学对话标注员。给定幼儿老师说的一段话，输出 JSON（只输出 JSON，不要别的）：
{"skill": "<知识点id或null>", "act": "<teach|ask|both|chitchat>", "comprehensible": <true|false>, "leaked": <true|false>, "expected": "<字符串或null>"}

字段定义：
- skill：这段话主要涉及下面清单中的哪个知识点；与清单无关则为 null。
- act：teach=讲解/示范知识；ask=向孩子提出需要动脑的问题或练习；both=既讲解又提问；chitchat=寒暄、游戏、组织性语言等与知识无关的话。
- comprehensible：讲解/提问是否用了5岁幼儿能听懂的语言和具体例子。
- leaked：如果这段话里出了练习题/提了问题，老师是否在孩子回答之前就把该题答案直接说了出来（讲解环节中示范例子的答案不算泄露；泄露仅指把留给孩子的问题的答案说穿）。
- expected：如果老师最后留给孩子的问题有唯一明确的标准答案（比如算数题、数数题），给出这个标准答案（尽量短，是数字就直接写数字）；如果是让孩子按顺序数数（例如从1数到10），写成「1到10」这种形式；开放式问题或没提问则为 null。

知识点清单：
{menu}"""


def annotate_tutor_turn(judge, kmap, tutor_text):
    sys = ANNOTATE_SYSTEM.replace("{menu}", _skill_menu(kmap))
    out = strip_think(judge.chat(
        [{"role": "system", "content": sys},
         {"role": "user", "content": f"老师说：{tutor_text}\n请输出JSON。"}],
        temperature=0.0, max_tokens=768))
    return _parse(out, kmap)


def _parse(out, kmap):
    default = {"skill": None, "act": "chitchat", "comprehensible": True,
               "leaked": False, "expected": None}
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return default
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return default
    skill = d.get("skill")
    if skill not in kmap.skills:
        skill = None
    act = d.get("act")
    if act not in ("teach", "ask", "both", "chitchat"):
        act = "chitchat"
    expected = d.get("expected")
    if not isinstance(expected, (str, int, float)):
        expected = None
    else:
        expected = str(expected).strip()[:20]
        if expected in ("", "null", "None", "无"):
            expected = None
    return {"skill": skill, "act": act,
            "comprehensible": bool(d.get("comprehensible", True)),
            "leaked": bool(d.get("leaked", False)),
            "expected": expected}
