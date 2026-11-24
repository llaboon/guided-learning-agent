"""Persistent learner model: per-skill mastery beliefs updated from evidence."""


class LearnerModel:
    """Beta-Bernoulli belief per skill. Also tracks language/engagement notes."""

    PRIOR_A = 1.0
    PRIOR_B = 2.0          # pessimistic prior: assume unknown until evidence
    MASTERY_THRESHOLD = 0.6
    UNCERTAIN_WIDTH = 0.30  # if belief in [t-w/2, t+w/2] → probe more

    def __init__(self, kmap):
        self.kmap = kmap
        self.beliefs = {sid: [self.PRIOR_A, self.PRIOR_B] for sid in kmap.skills}
        self.evidence_log = []

    def update(self, sid, correct, weight=1.0, source="probe"):
        a, b = self.beliefs[sid]
        if correct:
            a += weight
        else:
            b += weight
        self.beliefs[sid] = [a, b]
        self.evidence_log.append(
            {"skill": sid, "correct": bool(correct), "weight": weight, "source": source})

    def taught_boost(self, sid, weight=0.5):
        """Small optimistic bump after an apparently-successful teaching episode."""
        a, b = self.beliefs[sid]
        self.beliefs[sid] = [a + weight, b]
        self.evidence_log.append({"skill": sid, "correct": None,
                                  "weight": weight, "source": "taught"})

    def mastery(self, sid):
        a, b = self.beliefs[sid]
        return a / (a + b)

    def n_evidence(self, sid):
        a, b = self.beliefs[sid]
        return (a - self.PRIOR_A) + (b - self.PRIOR_B)

    def mastered_ids(self):
        return {sid for sid in self.beliefs
                if self.mastery(sid) >= self.MASTERY_THRESHOLD}

    def is_uncertain(self, sid):
        m = self.mastery(sid)
        half = self.UNCERTAIN_WIDTH / 2
        near_threshold = abs(m - self.MASTERY_THRESHOLD) <= half
        return near_threshold or self.n_evidence(sid) < 1

    def snapshot(self):
        return {sid: round(self.mastery(sid), 3) for sid in self.beliefs}

    def summary_text(self):
        lines = []
        for sid in self.kmap.order:
            s = self.kmap.skills[sid]
            m = self.mastery(sid)
            tag = "已掌握" if m >= self.MASTERY_THRESHOLD else (
                "不确定" if self.is_uncertain(sid) else "未掌握")
            lines.append(f"- {s.name}({sid}): 掌握度{m:.2f} [{tag}]")
        return "\n".join(lines)
