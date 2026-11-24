"""Simulated child learner backed by a (weak) LLM with a controlled knowledge profile."""

import random
import re

from .llm import strip_think

OPENING_UTTERANCE = "老师……我不知道要学什么。"


class StudentProfile:
    def __init__(self, pid, name="乐乐", age=5, mastered=None,
                 attention=0.85, beg_for_answer=0.0, persona_extra=""):
        self.pid = pid
        self.name = name
        self.age = age
        self.mastered = set(mastered or [])
        self.attention = attention  # probability of staying on-task each turn
        self.beg_for_answer = beg_for_answer  # P(直接索要答案) when asked a question
        self.persona_extra = persona_extra

    def to_dict(self):
        return {"pid": self.pid, "name": self.name, "age": self.age,
                "mastered": sorted(self.mastered), "attention": self.attention,
                "beg_for_answer": self.beg_for_answer,
                "persona_extra": self.persona_extra}


class StudentSim:
    def __init__(self, profile, kmap, endpoint, rng=None):
        self.profile = profile
        self.kmap = kmap
        self.ep = endpoint
        self.rng = rng or random.Random(0)

    def _knowledge_block(self):
        known, unknown = [], []
        for sid in self.kmap.order:
            s = self.kmap.skills[sid]
            line = f"{s.name}（{s.description}）"
            (known if sid in self.profile.mastered else unknown).append(line)
        kb = "你已经会的东西（只有这些！）：\n" + ("\n".join(f"- {x}" for x in known) or "- （几乎什么都还不会）")
        ub = "你还完全不会的东西（除非老师在对话里教会你）：\n" + "\n".join(f"- {x}" for x in unknown)
        return kb + "\n" + ub

    def system_prompt(self):
        p = self.profile
        return f"""你在扮演一个{p.age}岁的小朋友，名字叫{p.name}。你正在和一位老师说话。

{self._knowledge_block()}

你必须严格遵守的扮演规则：
1. 说话像{p.age}岁孩子：句子很短（一般不超过20个字），用词简单，偶尔有点语无伦次。
2. 你不知道自己该学什么，也不会主动提出想学的内容或问出有条理的问题。
3. 遇到"你还完全不会"清单里的问题：你会答错或说"不知道"，绝不能凭空答对。
4. 但你会认真听讲：如果老师在前面的对话里已经清楚地教过某个知识、带你练习过，你就可以慢慢学会并用它答题。
5. 只输出小朋友说的那一两句话本身，不要任何解释、动作描写或旁白。
{p.persona_extra}"""

    def _history_as_messages(self, transcript, system_suffix=""):
        """Map dialogue to the student model's perspective (tutor=user).
        NOTE: the served chat template requires the system message to be the
        first (and only) one, so extra directives are folded into it."""
        msgs = [{"role": "system", "content": self.system_prompt() + system_suffix}]
        for turn in transcript:
            role = "user" if turn["role"] == "tutor" else "assistant"
            msgs.append({"role": role, "content": turn["text"]})
        return msgs

    def respond(self, transcript):
        suffix = ""
        if self.rng.random() > self.profile.attention:
            suffix = "\n\n（特别注意：接下来这一句你走神了，说一句和学习无关的孩子气的话，比如想玩、想吃东西。）"
        msgs = self._history_as_messages(transcript, system_suffix=suffix)
        out = strip_think(self.ep.chat(msgs, temperature=0.9, max_tokens=1024))
        return _clip_utterance(out)

    def answer_item(self, question, transcript=None):
        """Answer a test item. transcript=None → pre-test (closed book);
        with transcript → post-test conditioned on the tutoring session."""
        sys_content = self.system_prompt()
        if transcript:
            convo = "\n".join(
                f"{'老师' if t['role'] == 'tutor' else self.profile.name}：{t['text']}"
                for t in transcript)
            sys_content += ("\n\n这是你和老师刚刚上课的完整对话，老师教过的内容你已经学到了：\n" + convo)
        msgs = [{"role": "system", "content": sys_content},
                {"role": "user",
                 "content": f"现在老师单独问你一个小问题，请直接回答：{question}"}]
        out = strip_think(self.ep.chat(msgs, temperature=0.3, max_tokens=512))
        return _clip_utterance(out, limit=60)


def _clip_utterance(text, limit=80):
    text = (text or "").strip().replace("\n", " ")
    return text[:limit] if len(text) > limit else text


_COUNT_RE = re.compile(r"^1到(\d+)$")


def expand_expected(expected, correct, rng):
    """Expand compact expected forms ("1到10") into an utterable sequence;
    wrong versions skip a number or stop early. Returns None if not compact."""
    m = _COUNT_RE.fullmatch(str(expected or "").strip())
    if not m:
        return None
    n = min(int(m.group(1)), 20)
    nums = [str(i) for i in range(1, n + 1)]
    if not correct:
        if rng.random() < 0.5 and n >= 4:
            drop = rng.randrange(2, n - 1)
            nums = nums[:drop] + nums[drop + 1:]      # skips a number
        else:
            nums = nums[:max(2, n - rng.randint(2, 3))]   # stops early
    return "、".join(nums)


def wrong_answer_text(expected, question, rng):
    """A plausible child-wrong answer given the expected one."""
    exp = str(expected or "").strip()
    nums_q = re.findall(r"\d+", question or "")
    if re.fullmatch(r"\d+", exp):
        v = int(exp)
        cands = [str(v + 1), str(max(v - 1, 0))]              # off-by-one
        cands += [n for n in nums_q if n != exp]               # echo an operand
        wild = rng.randint(1, 10)
        cands.append(str(wild) if str(wild) != exp else str(v + 2))
        return rng.choice(cands)
    return rng.choice(["不知道", "嗯……不会", "这个没学过"])


def compose_child_answer(correct, answer, rng):
    """Compose the child's answer utterance programmatically.

    Content-critical turns bypass the renderer LLM: a weak LLM reliably
    'corrects' instructed-wrong arithmetic answers when it can see the
    question (measured 37.5% instruction fidelity in the v1 bench). Bare
    answers with child-like hedges cannot be corrected and grade cleanly.
    """
    a = str(answer).strip()
    if a.startswith("不知道") or a in ("嗯……不会", "这个没学过"):
        return rng.choice(["不知道……", "嗯……不会。", "这个没学过……", "唔……不知道。"])
    if correct:
        pool = [f"{a}！", f"是{a}！", f"嗯……{a}！", f"我知道，是{a}！", f"{a}，对吗？"]
    else:
        pool = [f"{a}？", f"是{a}吧！", f"嗯……{a}！", f"{a}！对不对呀？"]
    return rng.choice(pool)


class StatefulStudentSim(StudentSim):
    """v2 simulator: an external GroundTruthState decides what the child can
    do; the LLM only renders child-like language (BEAGLE/Generative-Students
    style, see docs/literature_review.md track E). Content-critical answers
    are template-composed so state and utterance can never disagree."""

    def __init__(self, profile, kmap, endpoint, state, rng=None):
        super().__init__(profile, kmap, endpoint, rng=rng)
        self.state = state
        self.last_drawn_correct = None   # session reads this for planner obs

    def _render(self, transcript, directive):
        suffix = "\n\n本轮表演指令（务必遵守，但不要复述指令本身）：" + directive
        msgs = self._history_as_messages(transcript, system_suffix=suffix)
        out = strip_think(self.ep.chat(msgs, temperature=0.8, max_tokens=1024))
        return _clip_utterance(out)

    def respond_v2(self, transcript, annotation):
        """Reply given the judge annotation of the tutor's last turn."""
        self.last_drawn_correct = None
        if self.rng.random() > self.profile.attention:
            return self._render(transcript, "你走神了，说一句和学习无关的孩子气的话（想玩、想吃、看见窗外东西之类）。")
        asked = annotation["act"] in ("ask", "both") and annotation["skill"]
        if asked and self.rng.random() < self.profile.beg_for_answer:
            return self._render(transcript, "撒娇耍赖，直接让老师告诉你答案，比如：老师你直接告诉我嘛！")
        if asked:
            sid = annotation["skill"]
            # Leaked answer → the child just parrots it back.
            correct = True if annotation.get("leaked") else self.state.answer_correct(sid)
            self.last_drawn_correct = correct
            expected = annotation.get("expected")
            if expected:  # content-critical: template, never the LLM
                seq = expand_expected(expected, correct, self.rng)
                if seq is not None:
                    return seq + ("！" if correct else "……对吗？")
                tutor_q = next((t["text"] for t in reversed(transcript)
                                if t["role"] == "tutor"), "")
                ans = expected if correct else wrong_answer_text(expected, tutor_q, self.rng)
                return compose_child_answer(correct, ans, self.rng)
            if correct:
                return self._render(transcript, "你会老师问的这个：认真想一想，用孩子的口吻给出正确回答。")
            return self._render(
                transcript,
                "你完全不会老师问的这个：给出一个典型的错误回答（比如数错、答非所问），或者说不知道。绝不能答对。")
        return self._render(transcript, "回应老师的话：简短接话，表现出愿意听但不会主动提出学习要求。")

    def answer_item_v2(self, question, expected, correct):
        """Test answer whose correctness was already decided by the state.
        Template-composed (no LLM) so grading is exact."""
        seq = expand_expected(expected, correct, self.rng)
        if seq is not None:
            return seq + ("！" if correct else "……对吗？")
        ans = expected if correct else wrong_answer_text(expected, question, self.rng)
        return compose_child_answer(correct, ans, self.rng)
