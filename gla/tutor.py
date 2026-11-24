"""Tutor agents: baselines (vanilla / socratic) and the GLA executor."""

from .llm import strip_think

VANILLA_SYSTEM = "你是一个AI助手。请回应这个孩子说的话。"

SOCRATIC_SYSTEM = """你是一位耐心的幼儿老师，正在陪一个学龄前小朋友学习。
- 每次只说一到三句很短的话，用幼儿能听懂的词。
- 用提问引导孩子自己思考，不要直接把答案告诉孩子。
- 孩子答对要具体地表扬；答错不要批评，给一点小提示再让他试一次。
- 每次结尾带一个简单的问题。"""

GLA_EXECUTOR_SYSTEM = """你是一位耐心的幼儿老师，正在按照教学计划一对一辅导一个学龄前小朋友。
表达要求：
- 每次只说一到三句很短的话，用幼儿能听懂的词，可以用小动物、玩具、水果举例子。
- 结尾带一个简单的问题让孩子有话可接（讲解回合用「你听懂了吗」这类确认问题，练习回合才出题）。
- 孩子答对要具体表扬；答错不批评，给小提示让他再试。
教学纪律：
- 严格围绕下面"本轮教学指令"进行，不要跳到别的知识点。
- 出练习时绝不能自己说出答案；讲解时可以示范一个例子，但练习题要留给孩子自己想。"""


class BaselineTutor:
    def __init__(self, endpoint, system_prompt, tag):
        self.ep = endpoint
        self.system = system_prompt
        self.tag = tag

    def generate(self, transcript, directive=None, learner_summary=None):
        msgs = [{"role": "system", "content": self.system}]
        for t in transcript:
            role = "assistant" if t["role"] == "tutor" else "user"
            msgs.append({"role": role, "content": t["text"]})
        if not transcript:
            msgs.append({"role": "user", "content": "（孩子刚坐下，等你先开口。）"})
        return strip_think(self.ep.chat(msgs, temperature=0.7, max_tokens=1024))


INFORMED_SYSTEM_HEAD = """你是一位耐心、专业的幼儿数学老师，正在一对一辅导一个学龄前小朋友。孩子不会主动提问，也说不出自己想学什么，所以整节课由你主动引导。

你拿到了完整的课程信息（与智能导师系统使用的完全相同）：
{curriculum}

教学流程要求（请在对话中自己完成，不需要说出来）：
1. 主动诊断：先用轻松的小问题判断孩子已经会哪些知识点；一个知识点至少连续答对两个不同的小问题才算孩子已经会了，否则当作不会。
2. 按先修关系教学：只教先修知识点都已掌握的内容，从最基础的开始。
3. 每个知识点先讲解示范（可以用上面的教法提示），再出练习让孩子自己回答；孩子连续答对两次再进入下一个知识点，答错就换更简单的方式再讲。
4. 出练习时绝不能在孩子回答之前说出答案；孩子撒娇要答案也不要直接告诉他，给提示让他自己想。
5. 每次只说一到三句很短的话，用幼儿能听懂的词，可以用小动物、玩具、水果举例子；结尾带一个简单的问题。
6. 始终围绕课程知识点，不要长时间闲聊。"""


def informed_system(kmap):
    """Prompt-only baseline that receives the same domain information as GLA
    (skill inventory, descriptions, prerequisites, teaching hints) and an
    explicit diagnose / verify / prerequisite-order instruction, but no
    external learner model or planner (reviewer qKCP, point 1)."""
    lines = []
    for sid in kmap.order:
        s = kmap.skills[sid]
        pre = "、".join(kmap.skills[p].name for p in s.prerequisites) or "无"
        lines.append(f"- {s.name}（{s.description}）；先修：{pre}；教法提示：{s.teach_hints}")
    return INFORMED_SYSTEM_HEAD.replace("{curriculum}",
                                        "知识点（按先修顺序）：\n" + "\n".join(lines))


ACTIVITY_RULES = {
    "diagnose": "只提问、不讲解不示范：用一个轻松的小问题探测孩子会不会这个知识点。",
    "teach": "以讲解示范为主：演示这个知识点本身的完整做法和答案（示范不算泄露），内容不要换成别的任务。结尾只能问「你听懂了吗」「要不要再看一遍」这类确认问题，绝不能让孩子自己解题、数数或回答练习。",
    "practice": "出一道这个知识点的小题让孩子自己回答；孩子回答之前绝不能说出答案。",
}


class GLAExecutor(BaselineTutor):
    def __init__(self, endpoint, kmap=None, validator=None):
        super().__init__(endpoint, GLA_EXECUTOR_SYSTEM, "gla")
        self.kmap = kmap
        self._last_skill = None
        # Optional programmatic output check (reviewer a7k4, point 3).
        self.validator = validator
        self.validation_log = []

    def generate(self, transcript, directive=None, learner_summary=None):
        msgs = self._messages(transcript, directive, learner_summary)
        text = strip_think(self.ep.chat(msgs, temperature=0.7, max_tokens=1024))
        if self.validator is None or directive is None:
            return text
        record = {"activity": directive.activity, "skill": directive.skill_id,
                  "attempts": []}
        for attempt in range(self.validator.max_retries + 1):
            ok, problems, ann = self.validator.check(directive, text)
            record["attempts"].append({"ok": ok, "problems": problems,
                                       "annotation": ann})
            if ok or attempt == self.validator.max_retries:
                break
            fix = ("\n\n你上一版回复没有通过教学纪律检查：" + "；".join(problems)
                   + "。请严格按本轮教学指令重写这一回合，只输出老师要说的话。")
            retry_msgs = [dict(msgs[0], content=msgs[0]["content"] + fix)] + msgs[1:]
            text = strip_think(self.ep.chat(retry_msgs, temperature=0.7,
                                            max_tokens=1024))
        record["final_ok"] = record["attempts"][-1]["ok"]
        self.validation_log.append(record)
        return text

    def _messages(self, transcript, directive=None, learner_summary=None):
        sys = self.system
        if directive is not None:
            skill_desc = f"目标知识点：{directive.skill_id}"
            if (directive.skill_id and self.kmap
                    and directive.skill_id in self.kmap.skills):
                sk = self.kmap.skills[directive.skill_id]
                skill_desc = f"目标知识点：{sk.name}（{sk.description}）"
            rule = ACTIVITY_RULES.get(directive.activity, "")
            sys += (f"\n\n本轮教学指令（必须执行）：\n- 活动类型：{directive.activity}。{rule}\n"
                    f"- {skill_desc}\n- 说明：{directive.note}\n"
                    f"- 无论前面聊到什么、孩子表现如何，这一回合都必须且只能围绕上面的目标知识点。")
            if (directive.skill_id and self._last_skill
                    and directive.skill_id != self._last_skill):
                sys += ("\n- 注意：上一个话题已经结束，不要再继续旧话题的问答或练习。"
                        "开头至多用一句话收尾，然后立刻把孩子带进上面的新目标知识点。")
            if directive.skill_id:
                self._last_skill = directive.skill_id
        if learner_summary:
            sys += f"\n\n当前对孩子掌握情况的估计：\n{learner_summary}"
        msgs = [{"role": "system", "content": sys}]
        for t in transcript:
            role = "assistant" if t["role"] == "tutor" else "user"
            msgs.append({"role": role, "content": t["text"]})
        if not transcript:
            msgs.append({"role": "user", "content": "（孩子刚坐下，等你先开口。）"})
        return msgs


class DirectiveValidator:
    """Checks an executor draft against its directive with an independent
    annotator (by default a different model family than the measurement
    judge, so the policy does not optimise against the scoring judge).

    Rules: the draft must address the directive's skill; diagnose/practice
    drafts must pose a question and must not leak its answer; teach drafts
    must not assign the child an exercise (act must be teach)."""

    def __init__(self, endpoint, kmap, max_retries=2):
        self.ep = endpoint
        self.kmap = kmap
        self.max_retries = max_retries

    def check(self, directive, text):
        from .annotator import annotate_tutor_turn
        ann = annotate_tutor_turn(self.ep, self.kmap, text)
        problems = []
        if directive.skill_id and ann["skill"] != directive.skill_id:
            name = self.kmap.skills[directive.skill_id].name
            problems.append(f"内容没有围绕目标知识点「{name}」")
        if directive.activity in ("diagnose", "practice"):
            if ann["act"] not in ("ask", "both"):
                problems.append("这一回合必须给孩子出一个小问题")
            if ann["leaked"]:
                problems.append("在孩子回答之前说出了答案")
        elif directive.activity == "teach" and (
                ann["act"] == "ask" or (ann["act"] == "both" and ann["expected"])):
            # A confirmation question ("did you get it?") is allowed; an
            # exercise with a definite answer is not.
            problems.append("讲解回合不能让孩子做题或回答练习，只能用「你听懂了吗」确认")
        if not ann["comprehensible"]:
            problems.append("语言对5岁孩子来说太难")
        return (not problems), problems, ann


def grade_session_reply(judge, skill, tutor_utterance, student_reply):
    """Judge whether the student's reply to a probe/practice was correct.
    Returns True / False / None (can't judge)."""
    verdict = strip_think(judge.chat(
        [{"role": "system",
          "content": ("你是教学观察员。老师刚才就某个知识点向孩子提问，请判断孩子的回答是否正确。"
                      "只输出一个词：对、错 或 无法判断。")},
         {"role": "user",
          "content": (f"知识点：{skill.name}（{skill.description}）\n"
                      f"老师的话：{tutor_utterance}\n孩子的回答：{student_reply}\n"
                      f"孩子答对了吗？")}],
        temperature=0.0, max_tokens=512))
    v = verdict.strip()
    if v.startswith("对"):
        return True
    if v.startswith("错"):
        return False
    return None
