# GLA: Teaching the Child Who Cannot Ask

GLA (Guided Learning Agent) is a tutoring agent for learners who cannot say
what they need, such as a five-year-old starting early math. An external
learner model and a prerequisite-aware planner decide what to diagnose,
teach or practice next; an LLM executor turns each directive into one short
utterance. The agent is evaluated against a simulated child whose knowledge
is held in a transparent state engine, so learning gains are measured against
ground truth rather than judged from transcripts.

**Live site:** <https://llaboon.github.io/guided-learning-agent/>. It runs real
sessions in your browser with your own OpenAI-compatible API key, and shows
every released result table and session trace.

## Repository layout

| Path | Contents |
|---|---|
| `gla/` | Agent (planner, learner model, executor, validator), simulated child, state engine, metrics |
| `experiments/` | Experiment driver, offline validation, mock dry run, replay sensitivity, paired analysis, trace audit |
| `data/domains/` | Linear (13 skills) and branched (21 skills) early-math skill graphs with test items |
| `results/released/` | The 171 sessions and summaries reported in the original submission |
| `results/resub/` | Every session run for the resubmission, with per-phase summaries and analyses |
| `site/`, `tools/` | Static GitHub Pages site and its build and smoke-test scripts |
| `docs/` | Experiment protocol and results analysis notes |

## Quick start (no model needed)

```bash
python -m pip install -r requirements.txt
python experiments/validate_state.py     # simulator calibration: STATE_VALIDATION_PASS
python scripts/check_interfaces.py       # INTERFACE_CHECK_PASSED
python experiments/dryrun_mock.py        # full pipeline on scripted models: DRYRUN_OK
python scripts/verify_release.py         # every summary row matches its trace
```

These checks run in CI on every push. Reproducing the model-based numbers
needs GPU-served models; see [REPRODUCE.md](REPRODUCE.md).

## Conditions

| Id | Name | What it has |
|---|---|---|
| `vanilla` | C0 | Plain assistant prompt |
| `socratic` | C1 | Pedagogical prompt |
| `informed` | C1+ | Prompt with the full skill graph, prerequisites, teaching hints and explicit diagnose and verify rules |
| `gla_fixed` | C2 | GLA executor, fixed teach-teach-practice curriculum |
| `gla_reactive` | C3 | Learner model and micro-loop, greedy weakest-skill choice without prerequisites |
| `gla_full` | C4 | Learner model, double-confirmed diagnosis, prerequisite planner |
| `gla_single_probe` | C4-1 | C4 trusting a single passed probe |
| `gla_full_validated` | C4+V | C4 with an independent validator that checks and regenerates executor turns |

## Main resubmission results

Linear domain, 24 tutor turns, 3 profiles x 5 seeds (15 sessions per
condition), tutor and judge Qwen3.5-35B-A3B, child renderer Qwen3.5-0.8B.
Differences are paired over profile-seed blocks with bootstrap 95% CIs and
exact sign-flip p-values, Holm-adjusted within the family.

| Condition | Normalized gain | Skills learned | Leakage |
|---|---:|---:|---:|
| C0 vanilla | -0.039 | 0.00 | 0.000 |
| C1 socratic | -0.042 | 0.07 | 0.018 |
| C1+ informed | 0.030 | 0.13 | 0.084 |
| C2 fixed | 0.114 | 0.47 | 0.011 |
| C3 reactive | 0.035 | 0.40 | 0.069 |
| C4 GLA | 0.132 | 1.67 | 0.006 |
| C4-1 single probe | 0.120 | 1.60 | 0.014 |
| C4+V validated | 0.147 | 1.67 | 0.003 |

C4 learns more skills than every prompt baseline and both planner ablations
(for example +1.53 skills over the informed prompt, Holm p = .002; +1.20 over
C2, Holm p = .020). On normalized gain, C4 beats C0 and C1 clearly, but its
advantage over C2 (+0.018, CI [-0.059, 0.094]) is not resolved. The replay
sensitivity analysis in `results/resub/analysis/` shows the C4-C2 gain
ordering depends on the simulator: it reverses under soft prerequisite
gates, no gate, doubled learning rates and teach-heavy increments, while the
skills-learned advantage over C2 keeps a CI above zero in 9 of the 12
variants. Full tables for every phase are on the site and in
`results/resub/analysis/*.txt`.

## Limits

All learners are simulated. The simulator's learning rule, prerequisite gate
and mastery threshold were designed by the authors and affect the ordering of
conditions, as the sensitivity analysis shows. No study with real children has
been run. The executor's pedagogical constraints are enforced by prompt and,
in C4+V, by an LLM validator with bounded retries; neither is a formal
guarantee.

## Using your own model

Any OpenAI-compatible endpoint works:

```bash
export GLA_TUTOR_URL=https://api.openai.com/v1 GLA_TUTOR_MODEL=gpt-4.1-mini
export GLA_JUDGE_URL=$GLA_TUTOR_URL GLA_JUDGE_MODEL=$GLA_TUTOR_MODEL
export GLA_STUDENT_URL=$GLA_TUTOR_URL GLA_STUDENT_MODEL=$GLA_TUTOR_MODEL
export GLA_API_KEY=...      # falls back to OPENAI_API_KEY; never logged
python experiments/run_experiment.py --turns 12 --seeds 1 --profiles zero \
  --conditions vanilla,informed,gla_full --workers 3
```

Results from other models are new replications, not reproductions of the
reported numbers. Call logs (`results/calls_*.jsonl`) contain full prompts and
are excluded from version control.

## License

Code is released under the MIT License. Domain files, released traces and
result summaries are released under CC BY 4.0. See [LICENSE](LICENSE) and
[DATA_LICENSE](DATA_LICENSE).
