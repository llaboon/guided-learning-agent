"""Session orchestrator: runs one tutoring session under a given condition.

v2 unified loop (all conditions share the same measurement machinery):
tutor turn -> judge annotation -> ground-truth state update -> student render
-> (GLA only) tutor-side belief update & replanning.
"""

import json
import os
import time

from . import config
from .annotator import annotate_tutor_turn
from .learner_model import LearnerModel
from .planner import ZPDPlanner, FixedOrderPlanner, ReactivePlanner, SingleProbePlanner
from .student_sim import OPENING_UTTERANCE
from .tutor import (BaselineTutor, GLAExecutor, VANILLA_SYSTEM, SOCRATIC_SYSTEM,
                    DirectiveValidator, informed_system, grade_session_reply)

# Primary conditions C0..C4 plus the resubmission additions:
#   informed           C1+: prompt-only tutor given the same domain map,
#                      prerequisites and teaching hints, told to diagnose,
#                      verify mastery twice and follow prerequisites.
#   gla_full_validated C4+V: C4 with a programmatic directive validator
#                      (independent annotator, bounded regeneration).
CONDITIONS = ("vanilla", "socratic", "gla_fixed", "gla_reactive", "gla_full",
              "informed", "gla_full_validated", "gla_single_probe")


def build_tutor(condition, tutor_ep, kmap, lm, validator_ep=None):
    if condition == "gla_full":
        return ZPDPlanner(kmap, lm), GLAExecutor(tutor_ep, kmap)
    if condition == "gla_single_probe":
        return SingleProbePlanner(kmap, lm), GLAExecutor(tutor_ep, kmap)
    if condition == "gla_full_validated":
        if validator_ep is None:
            raise ValueError("gla_full_validated requires a validator endpoint")
        return ZPDPlanner(kmap, lm), GLAExecutor(
            tutor_ep, kmap, validator=DirectiveValidator(validator_ep, kmap))
    if condition == "gla_fixed":
        return FixedOrderPlanner(kmap, lm), GLAExecutor(tutor_ep, kmap)
    if condition == "gla_reactive":
        return ReactivePlanner(kmap, lm), GLAExecutor(tutor_ep, kmap)
    if condition == "socratic":
        return None, BaselineTutor(tutor_ep, SOCRATIC_SYSTEM, "socratic")
    if condition == "informed":
        return None, BaselineTutor(tutor_ep, informed_system(kmap), "informed")
    return None, BaselineTutor(tutor_ep, VANILLA_SYSTEM, "vanilla")


def run_session(condition, student, kmap, tutor_ep, judge_ep,
                max_turns=None, verbose=True, validator_ep=None, on_turn=None):
    """Run one session. ``on_turn`` (optional) receives a dict after every
    tutor/child exchange; it is used by the browser demo for live display
    and has no effect on the session itself."""
    assert condition in CONDITIONS
    max_turns = max_turns or config.MAX_SESSION_TURNS

    lm = LearnerModel(kmap)
    planner, tutor = build_tutor(condition, tutor_ep, kmap, lm, validator_ep)

    transcript = [{"role": "student", "text": OPENING_UTTERANCE}]
    directives, annotations, snapshots = [], [], []

    for turn in range(max_turns):
        directive, summary = None, None
        if planner is not None:
            directive = planner.next_directive()
            directives.append(directive.to_dict())
            if directive.activity == "end":
                break
            summary = lm.summary_text()

        t_utt = tutor.generate(transcript, directive=directive,
                               learner_summary=summary)
        transcript.append({"role": "tutor", "text": t_utt})

        ann = annotate_tutor_turn(judge_ep, kmap, t_utt)
        ann["turn"] = turn
        # Keep the simulator's sampled outcome alongside the blind annotation.
        # This is required for post-hoc learning-rule sensitivity analysis. The
        # outcome is generated before the state update and does not expose any
        # tutor-side ground truth during the live run.
        ann["drawn_correct"] = None
        annotations.append(ann)

        # The child answers against the *current* state; the state then
        # learns from the turn (teach and/or attempted practice).
        s_utt = student.respond_v2(transcript, ann)
        transcript.append({"role": "student", "text": s_utt})
        ann["drawn_correct"] = getattr(student, "last_drawn_correct", None)
        student.state.turn_update(
            ann, getattr(student, "last_drawn_correct", None), turn=turn)

        if planner is not None:
            if directive.activity in ("diagnose", "practice"):
                # v2.3 evidence hygiene: only the child's template-drawn
                # answer on the directive's own skill counts. Judge-graded
                # renders are contaminated (a demo-then-ask turn shows the
                # answer, the render parrots it, the grader passes it) and
                # leaked turns make the parrot correct by construction.
                drawn = getattr(student, "last_drawn_correct", None)
                on_skill = ann["skill"] == directive.skill_id
                if on_skill and not ann.get("leaked") and drawn is not None:
                    planner.observe(directive.skill_id, drawn)
                elif on_skill and ann["act"] in ("teach", "both"):
                    # v2.4: info-free turn that still carried instruction
                    # (leaked demo, child begged/drifted). Nudge the belief
                    # the way ground truth moves so leak loops stay bounded
                    # (4 boosts cross the mastery threshold) instead of
                    # freezing the planner on one skill forever.
                    lm.taught_boost(directive.skill_id)
            elif directive.activity == "teach":
                lm.taught_boost(directive.skill_id)
            snapshots.append(lm.snapshot())

        if verbose:
            act = directive.activity if directive else ann["act"]
            print(f"  [{turn:02d}|{act}] 师: {t_utt[:56]}")
            print(f"           生: {s_utt[:56]}", flush=True)

        if on_turn is not None:
            on_turn({"turn": turn,
                     "directive": directive.to_dict() if directive else None,
                     "tutor": t_utt, "child": s_utt, "annotation": dict(ann),
                     "state": student.state.snapshot(),
                     "belief": lm.snapshot() if planner is not None else None})

    return {
        "condition": condition,
        "student_profile": student.profile.to_dict(),
        "transcript": transcript,
        "directives": directives,
        "annotations": annotations,
        "belief_snapshots": snapshots,
        "final_belief": lm.snapshot() if planner is not None else None,
        "state_events": list(student.state.events),
        "final_state": student.state.snapshot(),
        "n_turns": sum(1 for t in transcript if t["role"] == "tutor"),
        "validation_log": getattr(tutor, "validation_log", None),
    }


def save_trace(trace, name):
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    path = os.path.join(config.RESULTS_DIR, f"{name}_{int(time.time())}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=1)
    return path
