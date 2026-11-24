"""Central config: model endpoints, paths, experiment defaults.

The canonical setup uses OpenAI-compatible vLLM servers:
  tutor/judge : Qwen3.5-35B-A3B, port 8101
  student     : Qwen3.5-0.8B,    port 8102
Override with GLA_HOST or the per-role GLA_*_URL environment variables.
"""

import os

HOST = os.environ.get("GLA_HOST", "localhost")

TUTOR_BASE_URL = os.environ.get("GLA_TUTOR_URL", f"http://{HOST}:8101/v1")
STUDENT_BASE_URL = os.environ.get("GLA_STUDENT_URL", f"http://{HOST}:8102/v1")
JUDGE_BASE_URL = os.environ.get("GLA_JUDGE_URL", TUTOR_BASE_URL)

API_KEY = "EMPTY"

# Resolved lazily from /v1/models if left as None.
TUTOR_MODEL = os.environ.get("GLA_TUTOR_MODEL")
STUDENT_MODEL = os.environ.get("GLA_STUDENT_MODEL")
JUDGE_MODEL = os.environ.get("GLA_JUDGE_MODEL")

WORK_DIR = os.environ.get("GLA_WORK_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(WORK_DIR, "data")
RESULTS_DIR = os.environ.get("GLA_RESULTS_DIR", os.path.join(WORK_DIR, "results"))

MAX_SESSION_TURNS = int(os.environ.get("GLA_MAX_TURNS", "30"))
SEED = int(os.environ.get("GLA_SEED", "20260831"))
