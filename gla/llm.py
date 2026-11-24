"""Thin OpenAI-compatible client wrapper with retries and call logging."""

import json
import os
import re
import time
import threading

_LOG_LOCK = threading.Lock()


class Endpoint:
    """One vLLM OpenAI-compatible endpoint (tutor / student / judge)."""

    def __init__(self, base_url, model=None, api_key=None, tag="llm",
                 log_path=None, timeout=180):
        # Imported lazily so the rest of the package (simulator, planner,
        # session loop) also runs where the SDK is unavailable, e.g. the
        # in-browser Pyodide demo, which supplies its own endpoint object.
        from openai import OpenAI

        if api_key is None:
            # Hosted APIs need a key; local vLLM accepts any string. The key
            # is never logged.
            api_key = (os.environ.get("GLA_API_KEY")
                       or os.environ.get("OPENAI_API_KEY") or "EMPTY")
        self.base_url = base_url
        self.tag = tag
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self.model = model or self._first_model()
        self.log_path = log_path

    def _first_model(self):
        for attempt in range(3):
            try:
                models = self.client.models.list()
                return models.data[0].id
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

    def chat(self, messages, temperature=0.7, max_tokens=1024, retries=6,
             nothink=True, **kw):
        if nothink:
            extra = kw.setdefault("extra_body", {})
            extra.setdefault("chat_template_kwargs", {"enable_thinking": False})
        last_err = None
        request_messages = list(messages)
        request_tokens = max_tokens
        for attempt in range(retries):
            try:
                t0 = time.time()
                resp = self.client.chat.completions.create(
                    model=self.model, messages=request_messages,
                    temperature=temperature, max_tokens=request_tokens, **kw)
                text = resp.choices[0].message.content or ""
                self._log(request_messages, text, time.time() - t0, resp.usage)
                return text
            except Exception as e:  # noqa: BLE001 — retry any transport/server error
                last_err = e
                # Long sessions eventually exceed the server's context budget
                # even when the generated reply is short.  vLLM reports both
                # the input length and the remaining completion budget in its
                # 400 response.  First shrink the completion, then retain the
                # system prompt and the most recent dialogue turns.  This
                # keeps the normal path unchanged and makes the endpoint
                # robust to longer transcripts.
                msg = str(e)
                m = re.search(
                    r"request has (\d+) input tokens \((\d+) > (\d+) - (\d+)\)",
                    msg,
                )
                if m:
                    input_tokens = int(m.group(1))
                    available = int(m.group(4))
                else:
                    # Recent vLLM releases use the shorter diagnostic below
                    # when the input itself already exceeds the context.
                    m = re.search(
                        r"maximum context length is (\d+) tokens.*?request has (\d+) input tokens",
                        msg,
                        flags=re.DOTALL,
                    )
                    input_tokens = int(m.group(2)) if m else None
                    available = int(m.group(1)) - input_tokens if m else None
                if input_tokens is None and "maximum context length" in msg:
                    # Newer vLLM wording without a parsable input count:
                    # fall through to history trimming below.
                    input_tokens, available = -1, None

                if input_tokens is not None:
                    # Shrink the completion first when there is room for a
                    # shorter reply.  If the prompt alone is too long,
                    # progressively retain the system prompt and the latest
                    # dialogue so the next retry has a smaller input.
                    if available is not None and available > 64 and request_tokens > available - 32:
                        request_tokens = max(64, available - 32)
                        continue
                    if len(request_messages) > 3:
                        tail_keep = max(2, (len(request_messages) - 1) // 2)
                        if request_messages[0].get("role") == "system":
                            request_messages = [request_messages[0]] + request_messages[-tail_keep:]
                        else:
                            request_messages = request_messages[-tail_keep:]
                        request_tokens = min(request_tokens, 256)
                        continue
                time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"[{self.tag}] chat failed after {retries} retries: {last_err}")

    def _log(self, messages, output, latency, usage):
        if not self.log_path:
            return
        rec = {
            "ts": time.time(), "tag": self.tag, "model": self.model,
            "latency_s": round(latency, 3),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "messages": messages, "output": output,
        }
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with _LOG_LOCK, open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def strip_think(text):
    """Remove reasoning preambles that thinking models may emit in-band."""
    if text is None:
        return ""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    # Qwen3.5 sometimes emits an unbracketed English "Thinking Process:" block
    # followed by the real answer after a separator or double newline.
    for marker in ("Thinking Process:", "思考过程："):
        if text.lstrip().startswith(marker):
            parts = text.split("\n\n")
            # Drop leading paragraphs that belong to the reasoning block:
            # keep from the last paragraph that doesn't look like reasoning.
            if len(parts) > 1:
                text = parts[-1]
    return text.strip()
