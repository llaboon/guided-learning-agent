"""Small privacy-conscious Gradio demo for one GLA simulation session.

The demo uses one user-provided OpenAI-compatible endpoint for tutor, child
renderer, and blind annotator. The API key is held in memory for the request,
never written to a trace, and discarded when the callback returns. Production
deployments should add authentication, rate limits, request timeouts, and a
separate endpoint for each role.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gla.assessment import run_state_test, score_by_skill
from gla.knowledge_map import load_domain
from gla.llm import Endpoint
from gla.metrics import annotation_metrics, learned_skills, learning_gain
from gla.session import run_session
from gla.student_sim import StatefulStudentSim, StudentProfile
from gla.student_state import GroundTruthState


PROFILES = {
    "zero": StudentProfile("zero", name="乐乐", age=5, mastered=[], attention=0.8),
    "mid": StudentProfile(
        "mid", name="朵朵", age=5,
        mastered=["counting_10", "counting_objects", "number_recognition"],
        attention=0.9,
    ),
    "beggar": StudentProfile(
        "beggar", name="皮皮", age=5, mastered=["counting_10"],
        attention=0.85, beg_for_answer=0.4,
    ),
}


def run_demo(api_key, base_url, model, profile_name, turns):
    if not api_key or not base_url or not model:
        raise ValueError("base URL、model 和 API key 都必须填写")
    turns = max(4, min(int(turns), 24))
    profile = PROFILES[profile_name]
    kmap = load_domain("early_math")
    endpoint = Endpoint(base_url.rstrip("/"), model=model, api_key=api_key,
                        tag="demo", log_path=None, timeout=120)
    state = GroundTruthState(kmap, mastered=profile.mastered, seed=7)
    student = StatefulStudentSim(profile, kmap, endpoint, state=state,
                                 rng=random.Random(7007))
    pre = score_by_skill(run_state_test(student, kmap, form="A", render=False))
    trace = run_session("gla_full", student, kmap, endpoint, endpoint,
                        max_turns=turns, verbose=False)
    post = score_by_skill(run_state_test(student, kmap, form="B", render=False))
    gaps = set(kmap.skills) - set(profile.mastered)
    result = learning_gain(pre, post, target_skills=gaps)
    result["annotation_metrics"] = annotation_metrics(trace, kmap, profile.mastered)
    result["learned_skills"] = learned_skills(trace)
    return json.dumps({"metrics": result, "transcript": trace["transcript"]},
                      ensure_ascii=False, indent=2)


def build_app():
    import gradio as gr

    with gr.Blocks(title="GLA demo") as app:
        gr.Markdown("## GLA online demo\nUse an OpenAI-compatible endpoint. The key is used only for this request.")
        with gr.Row():
            base_url = gr.Textbox(label="Base URL", value="https://api.openai.com/v1")
            model = gr.Textbox(label="Model")
        with gr.Row():
            api_key = gr.Textbox(label="API key", type="password")
            profile = gr.Dropdown(list(PROFILES), value="zero", label="Learner profile")
            turns = gr.Slider(4, 24, value=12, step=1, label="Turns")
        run = gr.Button("Run one session")
        output = gr.Code(label="Metrics and transcript", language="json")
        run.click(run_demo, [api_key, base_url, model, profile, turns], output)
    return app


if __name__ == "__main__":
    build_app().launch()
