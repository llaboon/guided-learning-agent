"""In-browser runtime for the GLA demo.

Runs inside Pyodide in a dedicated Web Worker. It reuses the unmodified
``gla`` package and replaces only the network layer: ``BrowserEndpoint``
sends OpenAI-compatible chat requests with a synchronous XMLHttpRequest
(allowed in workers), so the session loop stays the same synchronous code
that produced the paper's traces. The API key lives in this worker's memory
only and is never written to the trace.
"""

import json
import random
import time

from js import XMLHttpRequest, postMessage


class EndpointError(RuntimeError):
    pass


def emit(kind, **payload):
    payload["type"] = kind
    postMessage(json.dumps(payload, ensure_ascii=False))


def _wait(seconds):
    # time.sleep is not reliable inside Pyodide; a short busy wait is fine
    # in a dedicated worker.
    end = time.time() + seconds
    while time.time() < end:
        pass


class BrowserEndpoint:
    def __init__(self, role, base_url, model, api_key, options):
        self.tag = role
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._key = api_key
        self.vllm_nothink = bool(options.get("vllm_nothink"))
        self.cap = int(options.get("max_tokens") or 800)
        self.token_param = "max_tokens"
        self.send_temperature = True

    def _post(self, payload):
        xhr = XMLHttpRequest.new()
        xhr.open("POST", self.base_url + "/chat/completions", False)
        xhr.setRequestHeader("Content-Type", "application/json")
        if self._key:
            xhr.setRequestHeader("Authorization", "Bearer " + self._key)
        xhr.timeout = 180000
        try:
            xhr.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:  # network error, CORS rejection or timeout
            return 0, str(e)
        return int(xhr.status), str(xhr.responseText or "")

    def chat(self, messages, temperature=0.7, max_tokens=1024, retries=3,
             nothink=True, **_kw):
        last = ""
        attempt = 0
        while attempt <= retries:
            payload = {"model": self.model, "messages": messages,
                       self.token_param: min(int(max_tokens), self.cap)}
            if self.send_temperature:
                payload["temperature"] = temperature
            if self.vllm_nothink and nothink:
                payload["chat_template_kwargs"] = {"enable_thinking": False}
            t0 = time.time()
            status, text = self._post(payload)
            if status == 200:
                try:
                    data = json.loads(text)
                    content = data["choices"][0]["message"].get("content") or ""
                except (ValueError, KeyError, IndexError, TypeError):
                    raise EndpointError(f"{self.tag}: unreadable response")
                usage = data.get("usage") or {}
                emit("call", role=self.tag, ok=True,
                     latency=round(time.time() - t0, 2),
                     prompt_tokens=usage.get("prompt_tokens"),
                     completion_tokens=usage.get("completion_tokens"))
                return content
            low = text.lower()
            # Newer OpenAI models reject max_tokens / non-default temperature;
            # adapt once without spending a retry.
            if status == 400 and "max_completion_tokens" in low and self.token_param == "max_tokens":
                self.token_param = "max_completion_tokens"
                continue
            if status == 400 and "temperature" in low and self.send_temperature:
                self.send_temperature = False
                continue
            if status == 400 and "chat_template_kwargs" in low and self.vllm_nothink:
                self.vllm_nothink = False
                continue
            emit("call", role=self.tag, ok=False, status=status)
            last = f"HTTP {status}: {text[:300]}" if status else (
                "network error (endpoint unreachable or CORS not allowed): " + text[:200])
            if status in (400, 401, 403, 404, 422):
                break
            attempt += 1
            if attempt <= retries:
                _wait(min(2.0 * attempt, 6.0))
        raise EndpointError(f"{self.tag}: {last}")


def _endpoints(cfg, kmap):
    if cfg.get("mock"):
        from experiments.dryrun_mock import MockEndpoint
        return {r: MockEndpoint(kmap, "student" if r == "child" else r)
                for r in ("tutor", "judge", "child")}
    roles = cfg["roles"]
    opts = cfg.get("options", {})
    eps = {}
    for role in ("tutor", "judge", "child"):
        r = roles.get(role) or roles["tutor"]
        eps[role] = BrowserEndpoint(role, r["base_url"], r["model"],
                                    r.get("api_key", ""), opts)
    return eps


def run_live(cfg_json):
    cfg = json.loads(cfg_json)
    from gla.knowledge_map import load_domain
    from gla.student_state import GroundTruthState
    from gla.student_sim import StatefulStudentSim
    from gla.assessment import run_state_test, score_by_skill
    from gla.session import run_session
    from gla.metrics import learning_gain, annotation_metrics, learned_skills
    from experiments.run_experiment import PROFILES

    kmap = load_domain(cfg.get("domain", "early_math"))
    profile = next(p for p in PROFILES if p.pid == cfg["profile"])
    seed = int(cfg.get("seed", 1))
    turns = max(2, min(int(cfg.get("turns", 12)), 40))
    eps = _endpoints(cfg, kmap)
    emit("domain", order=list(kmap.order),
         skills={sid: {"name": s.name, "prerequisites": s.prerequisites}
                 for sid, s in kmap.skills.items()})

    results = []
    for idx, condition in enumerate(cfg["conditions"]):
        # Same seeding as experiments/run_experiment.py::run_one, so the
        # simulated child is identical across compared conditions.
        rng = random.Random(seed * 1000 + sum(ord(c) for c in profile.pid) % 1000)
        state = GroundTruthState(kmap, mastered=profile.mastered, seed=seed)
        student = StatefulStudentSim(profile, kmap, eps["child"], state=state, rng=rng)
        pre = score_by_skill(run_state_test(student, kmap, form="A", render=False))
        emit("session_start", index=idx, condition=condition,
             profile=profile.to_dict(), state=state.snapshot(), pre=pre)
        validator = eps["judge"] if condition == "gla_full_validated" else None
        trace = run_session(condition, student, kmap, eps["tutor"], eps["judge"],
                            max_turns=turns, verbose=False, validator_ep=validator,
                            on_turn=lambda d, i=idx: emit("turn", index=i, **d))
        post = score_by_skill(run_state_test(student, kmap, form="B", render=False))
        gaps = set(kmap.skills) - set(profile.mastered)
        gain = learning_gain(pre, post, target_skills=gaps)
        trace.update({"seed": seed, "domain": kmap.domain_id,
                      "pre_scores": pre, "post_scores": post, "gain": gain,
                      "annotation_metrics": annotation_metrics(trace, kmap, profile.mastered),
                      "learned_skills": learned_skills(trace),
                      "models": None if cfg.get("mock") else {
                          r: {"base_url": eps[r].base_url, "model": eps[r].model}
                          for r in eps}})
        results.append(trace)
        emit("session_done", index=idx, condition=condition, trace=trace)
    emit("all_done", n=len(results))
