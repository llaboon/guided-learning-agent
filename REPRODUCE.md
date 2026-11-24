# Reproducing the experiments

There are three levels. Each level is independent of the ones below it.

| Level | Needs | Time | What it confirms |
|---|---|---|---|
| 1. Offline checks | Python 3.10+ | 1 min | Simulator calibration, pipeline wiring, released data consistency |
| 2. Re-analysis | Python 3.10+ | 2 min | Every table number from the released traces, including replay sensitivity |
| 3. Model-based rerun | 4 GPUs with 80+ GB (we used H20 96 GB) | 3 to 6 h per phase | New traces under the paper's model setup |

## 1. Offline checks

```bash
python -m pip install -r requirements.txt   # only the openai SDK
python experiments/validate_state.py        # STATE_VALIDATION_PASS
python scripts/check_interfaces.py          # INTERFACE_CHECK_PASSED
python experiments/dryrun_mock.py           # DRYRUN_OK, all 8 conditions on scripted models
python scripts/test_probe_confirm.py        # PROBE_TEST_PASS
python scripts/verify_release.py            # RELEASE_VERIFY_PASSED
```

`validate_state.py` checks that composed child answers grade exactly as the
state decided, that turns without teaching never move the state, that an
oracle tutor masters all 13 skills without hitting the prerequisite gate, and
that empirical slip and guess rates match the nominal 0.10 and 0.05.

## 2. Re-analysis of released traces

```bash
# Paired profile-seed effects with bootstrap CIs, exact sign-flip p and Holm
python experiments/analyze_paired.py \
  results/resub/main/experiment_*.json results/resub/main_fill*/experiment_*.json \
  results/resub/validated/experiment_*.json --ref gla_full \
  --metrics norm_gain,n_learned,leakage_rate,chitchat_rate --brief

# Replay the main-run traces under 12 alternative simulator rules
python experiments/replay_sensitivity.py \
  --results-dir results/resub/main,results/resub/main_fill1,results/resub/main_fill2 \
  --out /tmp/replay.json
python experiments/summarize_replay.py /tmp/replay.json
```

The outputs should match `results/resub/analysis/main.txt` and
`results/resub/analysis/replay_sensitivity.txt` exactly; all resampling uses
fixed seeds. The replay holds the tutor's turns and the judge annotations
fixed and re-applies a different learning rule (soft or no prerequisite
gate, 0.5x or 2x learning rates, threshold 0.7 or 0.9, teach-heavy or
practice-heavy increments). It needs `annotations[*].drawn_correct`, which
every resubmission trace logs; the original 171 released traces predate this
field and are skipped.

## 3. Model-based rerun

### Serve the models

We used `vllm/vllm-openai:v0.30.0` with these arguments (one GPU each unless
noted; weights from Hugging Face):

```bash
MODELS=/path/to/models
docker run -d --gpus '"device=0"' --network host -v $MODELS:/models \
  --name gla_tutor vllm/vllm-openai:v0.30.0 \
  --model /models/Qwen3.5-35B-A3B --served-model-name qwen35_tutor --port 8101 \
  --max-model-len 16384 --gpu-memory-utilization 0.92 --max-num-seqs 64
docker run -d --gpus '"device=1"' --network host -v $MODELS:/models \
  --name gla_student vllm/vllm-openai:v0.30.0 \
  --model /models/Qwen3.5-0.8B --served-model-name qwen08_student --port 8102 \
  --max-model-len 16384 --gpu-memory-utilization 0.6
# Cross-family phases and the validator only:
docker run -d --gpus '"device=2,3"' --network host -v $MODELS:/models \
  --name gla_gemma vllm/vllm-openai:v0.30.0 \
  --model /models/gemma-4-31B-it --served-model-name gemma4_31b --port 8103 \
  --tensor-parallel-size 2 --max-model-len 16384 --gpu-memory-utilization 0.9 --max-num-seqs 64
python scripts/test_endpoints.py   # ALL_ENDPOINT_TESTS_PASSED
```

Qwen3.5 thinking is disabled per request
(`chat_template_kwargs.enable_thinking=false`, set in `gla/llm.py`).

### Run the phases

```bash
bash scripts/run_resubmission.sh main        # 7 conditions x 3 profiles x 5 seeds = 105 sessions
bash scripts/run_resubmission.sh validated   # C4+V, Gemma as validator, 15 sessions
bash scripts/run_resubmission.sh softgate    # live soft-gate rerun, 60 sessions
bash scripts/run_resubmission.sh thr09       # live threshold-0.9 rerun, 60 sessions
bash scripts/run_resubmission.sh xjudge      # Gemma as in-experiment judge, 54 sessions
bash scripts/run_resubmission.sh xtutor      # Gemma as tutor, 54 sessions
bash scripts/run_resubmission.sh branched    # 21-skill domain incl. scatter profile, 60 sessions
bash scripts/resub_status.sh                 # progress and failures per phase
```

Set `QWEN_URL`, `CHILD_URL`, `XFAM_URL` and `WORKERS` to override endpoints
and concurrency. A session that fails (for example an endpoint timeout) is
logged as `[FAIL]` and can be rerun alone with
`--conditions C --profiles P --seeds S --tag <phase>_fill`; the analysis
merges fill-in files by condition, profile and seed. In our run, 4 vanilla
main sessions and 1 vanilla xjudge session needed such a fill-in because the
vanilla tutor's long chit-chat exceeded the child renderer's context.

### Expected agreement

vLLM sampling at temperature 0.7 is not bit-reproducible across hardware,
batch composition or library versions, so a rerun produces different
transcripts. The simulator, the tests and the analysis are deterministic
given a transcript. Treat a rerun as a replication: with 15 sessions per
condition, condition means typically move by up to about 0.05 normalized gain
(the fixed-state no-learning null alone has SD of about 0.07 per session).
The ordering that should replicate is C4 learning more skills than C0, C1,
C1+, C2 and C3. The C4 versus C2 difference on normalized gain is small and
was not resolved in our own run.

### Other models

Any OpenAI-compatible endpoint can be used through `GLA_TUTOR_URL`,
`GLA_JUDGE_URL`, `GLA_STUDENT_URL`, the matching `*_MODEL` variables and
`GLA_API_KEY`. The browser demo on the project site runs the same code with
a key you supply.
