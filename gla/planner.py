"""Curriculum planners: choose next objective + activity each tutor turn."""

import random


class Directive:
    def __init__(self, activity, skill_id=None, note=""):
        self.activity = activity      # diagnose | teach | practice | end
        self.skill_id = skill_id
        self.note = note

    def to_dict(self):
        return {"activity": self.activity, "skill": self.skill_id, "note": self.note}


class ZPDPlanner:
    """Full GLA planner: adaptive selection driven by the learner model.

    Cold-start triage: every ZPD skill is probed before teaching. A skill is
    fast-forwarded past mastery only after DIAG_CONFIRM *consecutive* passed
    probes (v2.3: a single pass proved poisonous -- one lucky guess marked a
    root skill mastered, unlocking children whose real prerequisite stayed
    unlearned, so every later turn hit the ground-truth prereq gate; double
    confirmation drops the false-pass rate from GUESS to GUESS^2 while a
    truly-known skill still costs 2 turns instead of a full teach cycle).
    Probes that never produce valid evidence (the executor drifted off-skill,
    the child begged or got distracted) are bounded by MAX_DIAG_ATTEMPTS,
    after which the planner just teaches. A failed probe starts the micro
    teaching loop: teach -> practice, re-teach on failure (up to MAX_TEACH),
    advance after PRACTICE_TO_ADVANCE consecutive correct practices. Skills
    that eat too many turns are parked so the session moves on.
    """

    PRACTICE_TO_ADVANCE = 2
    MAX_TEACH = 3
    MAX_TURNS_PER_SKILL = 8
    DIAG_CONFIRM = 2
    MAX_DIAG_ATTEMPTS = 4
    DIAGNOSE_PASS_WEIGHT = 2.0   # applied on the confirming pass, for margin

    def __init__(self, kmap, learner_model):
        self.kmap = kmap
        self.lm = learner_model
        self.correct_streak = {sid: 0 for sid in kmap.skills}
        self.teach_count = {sid: 0 for sid in kmap.skills}
        self.turns_on = {sid: 0 for sid in kmap.skills}
        self.last_wrong = {sid: False for sid in kmap.skills}
        self.diag_passes = {sid: 0 for sid in kmap.skills}
        self.diag_attempts = {sid: 0 for sid in kmap.skills}
        self.parked = set()
        self.pending_diagnose = None

    def observe(self, skill_id, correct):
        if skill_id is None or correct is None:
            return
        was_diagnose = (skill_id == self.pending_diagnose)
        self.pending_diagnose = None
        if correct:
            self.correct_streak[skill_id] += 1
            self.last_wrong[skill_id] = False
        else:
            self.correct_streak[skill_id] = 0
            self.last_wrong[skill_id] = True
        self.lm.update(skill_id, correct, source="session_probe")
        if was_diagnose:
            if correct:
                self.diag_passes[skill_id] += 1
                if self.diag_passes[skill_id] >= self.DIAG_CONFIRM:
                    # Confirmed twice: trust it and move on.
                    self.lm.update(skill_id, True,
                                   weight=self.DIAGNOSE_PASS_WEIGHT,
                                   source="diagnose_pass")
            else:
                self.diag_passes[skill_id] = 0

    def _pick(self):
        mastered = self.lm.mastered_ids()
        zpd = [s for s in self.kmap.zpd_skills(mastered) if s not in self.parked]
        if not zpd:
            # Revisit parked skills rather than idle -- with a fresh budget,
            # else pick/park/repick loops straight into an early "end".
            zpd = self.kmap.zpd_skills(mastered)
            for s in zpd:
                self.turns_on[s] = 0
            self.parked.clear()
        return zpd[0] if zpd else None

    def next_directive(self, _depth=0):
        if _depth > len(self.kmap.skills) + 2:
            return Directive("end", note="规划器无可选目标")
        sid = self._pick()
        if sid is None:
            return Directive("end", note="课程目标全部达成")
        skill = self.kmap.skills[sid]
        self.turns_on[sid] += 1
        if self.turns_on[sid] > self.MAX_TURNS_PER_SKILL:
            self.parked.add(sid)
            return self.next_directive(_depth + 1)
        passes = self.diag_passes[sid]
        needs_probe = (self.lm.n_evidence(sid) < 1
                       or 0 < passes < self.DIAG_CONFIRM)
        if needs_probe and self.diag_attempts[sid] < self.MAX_DIAG_ATTEMPTS:
            self.pending_diagnose = sid
            self.diag_attempts[sid] += 1
            if passes:
                note = (f"孩子刚才答对了，再用一个不同的小问题确认孩子真的会"
                        f"「{skill.name}」；只提问，不要讲解、不要示范")
            else:
                note = (f"只用一个轻松的小问题探测孩子是否已会「{skill.name}」；"
                        f"不要讲解、不要示范")
            return Directive("diagnose", sid, note=note)
        if self.correct_streak[sid] >= self.PRACTICE_TO_ADVANCE:
            self.lm.update(sid, True, weight=2.0, source="advance")
            self.turns_on[sid] -= 1
            return self.next_directive(_depth + 1)
        if self.teach_count[sid] == 0 or (
                self.last_wrong[sid] and self.teach_count[sid] < self.MAX_TEACH):
            self.teach_count[sid] += 1
            self.last_wrong[sid] = False
            again = "孩子刚才没答上来，换一种更简单的方式再" if self.teach_count[sid] > 1 else ""
            return Directive("teach", sid,
                             note=f"{again}用具体例子讲解「{skill.name}」，本回合以讲解示范为主。教法：{skill.teach_hints}")
        return Directive("practice", sid,
                         note=f"出一道「{skill.name}」的小练习让孩子自己回答，答对要表扬")


class SingleProbePlanner(ZPDPlanner):
    """Ablation of verified diagnosis (reviewer a7k4, point 4): one passed
    probe is trusted, so known skills cost one turn instead of two, at the
    price of a higher false-pass rate."""

    DIAG_CONFIRM = 1


class FixedOrderPlanner(ZPDPlanner):
    """Ablation C2: same executor, but the curriculum advances on a fixed
    schedule (teach, teach, practice per skill, in topological order)
    regardless of learner evidence."""

    TURNS_PER_SKILL = 3

    def __init__(self, kmap, learner_model):
        super().__init__(kmap, learner_model)
        self._idx = 0
        self._turns_on_skill = 0

    def observe(self, skill_id, correct):
        pass  # ignores evidence by design

    def next_directive(self, _depth=0):
        if self._idx >= len(self.kmap.order):
            return Directive("end", note="固定课程走完")
        sid = self.kmap.order[self._idx]
        skill = self.kmap.skills[sid]
        self._turns_on_skill += 1
        if self._turns_on_skill > self.TURNS_PER_SKILL:
            self._idx += 1
            self._turns_on_skill = 0
            return self.next_directive(_depth + 1)
        act = "teach" if self._turns_on_skill <= 2 else "practice"
        note = (f"用具体例子讲解「{skill.name}」，本回合以讲解示范为主。教法：{skill.teach_hints}"
                if act == "teach" else f"出一道「{skill.name}」的小练习让孩子自己回答")
        return Directive(act, sid, note=note)


class ReactivePlanner(ZPDPlanner):
    """Ablation C3 (gla_reactive): diagnosis + learner model + the same micro
    teaching loop are kept, but macro planning is removed -- each turn greedily
    targets the skill with the weakest current belief, with no prerequisite or
    ZPD reasoning. Belief ties break at random (a reactive tutor has no
    curriculum prior; without jitter, dict-order ties would replicate the
    topological curriculum by accident)."""

    TIEBREAK_SEED = 20260831

    def __init__(self, kmap, learner_model):
        super().__init__(kmap, learner_model)
        self._rng = random.Random(self.TIEBREAK_SEED)

    def _pick(self):
        mastered = self.lm.mastered_ids()
        cands = [s for s in self.kmap.order
                 if s not in mastered and s not in self.parked]
        if not cands:
            cands = [s for s in self.kmap.order if s not in mastered]
            for s in cands:
                self.turns_on[s] = 0
            self.parked.clear()
        if not cands:
            return None
        return min(cands, key=lambda s: (self.lm.mastery(s), self._rng.random()))
