"""Ground-truth cognitive state of the simulated child (v2.1, continuous).

The state is held by this transparent engine; the LLM only renders language
(see docs/literature_review.md track E). Learning follows the pre-registered
v0.1 mastery rule (docs/experiment_protocol.md §3): per-skill mastery
m ∈ [0,1], driven each turn by the blind judge annotation of the tutor's
utterance plus the child's drawn practice outcome.

Why continuous rather than the interim exposure counter: the v2.0 pilot
showed "2 teach exposures -> mastered" makes practice and diagnosis worthless
turns, so a lecture-twice-in-order script dominates every closed-loop policy.
The v0.1 rule rewards practice most (mastery learning), which no tutor
condition can game without actually adapting to the child.

The rule only rewards generic good pedagogy -- prerequisites satisfied,
comprehensible language, practice-centred teaching -- and references no GLA
internals; baseline conditions can satisfy it too (anti-circularity clause).
"""

import random
import os

# frozen parameters (protocol §3, calibrated by Session-A's V3 oracle)
MASTERED_TRUE = float(os.environ.get("GLA_MASTERY_THRESHOLD", "0.8"))
SLIP = 0.10
GUESS = 0.05                 # deviation from v0.1's 0.15: arithmetic guessing
                             # by a 5-year-old is rare; documented in protocol
ALPHA_TEACH = 0.12
ALPHA_PRACTICE_OK = 0.25
ALPHA_PRACTICE_TRY = 0.08
ALPHA_LEAKED = 0.04
LANG_PENALTY = 0.3
NOISE_SD = 0.02
MAX_TURN_DELTA = 0.30
# Prerequisite gate used by the simulator (sensitivity analysis, reviewer
# request). "hard": no progress unless every prerequisite is mastered.
# "soft_min" / "soft_mean": progress is scaled by min / mean of
# min(1, m_p / threshold) over prerequisites.  "none": no gate.
GATE_MODE = os.environ.get("GLA_GATE", "hard")


def gate_factor(m, prerequisites, threshold=None, mode=None):
    threshold = MASTERED_TRUE if threshold is None else threshold
    mode = GATE_MODE if mode is None else mode
    if not prerequisites or mode == "none":
        return 1.0
    ratios = [min(1.0, m[p] / threshold) for p in prerequisites]
    if mode == "hard":
        return 1.0 if all(r >= 1.0 for r in ratios) else 0.0
    if mode == "soft_min":
        return min(ratios)
    if mode == "soft_mean":
        return sum(ratios) / len(ratios)
    raise ValueError(f"unknown gate mode: {mode}")


class GroundTruthState:
    """Continuous mastery per skill; updated from blind per-turn annotations."""

    # kept as class attrs so tests/metrics can read nominal rates
    SLIP = SLIP
    GUESS = GUESS
    MASTERED_TRUE = MASTERED_TRUE

    def __init__(self, kmap, mastered=None, seed=0):
        self.kmap = kmap
        self.m = {sid: 0.0 for sid in kmap.skills}
        for sid in (mastered or []):
            if sid in self.m:
                self.m[sid] = 1.0
        self.rng = random.Random(seed)
        self.events = []

    # ---- queries ----
    def is_mastered(self, sid):
        return sid in self.m and self.m[sid] >= MASTERED_TRUE

    def prereqs_ok(self, sid):
        return all(self.m[p] >= MASTERED_TRUE
                   for p in self.kmap.skills[sid].prerequisites)

    def answer_correct(self, sid):
        if sid not in self.m:
            return False
        p = self.m[sid] * (1 - SLIP) + (1 - self.m[sid]) * GUESS
        return self.rng.random() < p

    @property
    def mastered(self):
        return {sid for sid, v in self.m.items() if v >= MASTERED_TRUE}

    # ---- learning rule ----
    def turn_update(self, ann, drawn_correct=None, turn=None):
        """Apply one tutor turn. `ann` is the blind judge annotation
        (skill/act/comprehensible/leaked); `drawn_correct` is the child's
        drawn outcome when the turn asked a question (None if no answer)."""
        sid = ann.get("skill")
        act = ann.get("act")
        if sid not in self.m or act not in ("teach", "ask", "both"):
            return 0.0
        gate = gate_factor(self.m, self.kmap.skills[sid].prerequisites)
        if gate <= 0.0:
            self.events.append({"turn": turn, "skill": sid,
                                "event": "blocked_prereq"})
            return 0.0

        delta = 0.0
        if act in ("teach", "both"):
            delta += ALPHA_TEACH
        if act in ("ask", "both"):
            if ann.get("leaked"):
                delta += ALPHA_LEAKED          # parroting a told answer
            elif drawn_correct is True:
                delta += ALPHA_PRACTICE_OK
            elif drawn_correct is False:
                delta += ALPHA_PRACTICE_TRY    # attempted, got it wrong
            # drawn_correct None: child never engaged the question

        if delta == 0.0:
            return 0.0
        if not ann.get("comprehensible", True):
            delta *= LANG_PENALTY
        delta = min(delta * gate, MAX_TURN_DELTA) + self.rng.gauss(0, NOISE_SD)

        before = self.m[sid]
        self.m[sid] = min(1.0, max(0.0, before + delta))
        self.events.append({"turn": turn, "skill": sid, "event": "progress",
                            "delta": round(self.m[sid] - before, 4),
                            "m": round(self.m[sid], 4)})
        if before < MASTERED_TRUE <= self.m[sid]:
            self.events.append({"turn": turn, "skill": sid, "event": "learned"})
        return self.m[sid] - before

    def snapshot(self):
        return {"mastered": sorted(self.mastered),
                "m": {sid: round(v, 3) for sid, v in self.m.items()}}
