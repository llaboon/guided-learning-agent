# Cross-family robustness check

This file documents an exploratory rerun of the linear-domain protocol with a
different Qwen model family. It is kept separate from the canonical 75-session
Qwen3.5 result set and is not pooled into the paper's main tables.

- **Sessions:** 30 total, 5 conditions x 3 profiles x 2 seeds, 24 tutor turns per session.
- **Tutor and in-experiment judge:** `Qwen3-30B-A3B-Instruct-2507`.
- **Student renderer:** `Qwen3-VL-4B-Instruct`.
- **Conditions:** `vanilla`, `socratic`, `gla_fixed`, `gla_reactive`, `gla_full`.
- **Profiles:** `zero`, `mid`, `beggar`.
- **Remote result:** `results/experiment_1795245352.json`.
- **Local result:** `results/experiment_1795245352.json`.

The condition summaries below report mean and sample standard deviation. The
permutation values are the session-level two-sided tests emitted by the
experiment runner. The paired effects match profile-seed blocks. Exact
sign-flip values enumerate all 64 sign assignments for six blocks. Bootstrap
intervals use 20,000 resamples with seed 7 and are included as descriptive
uncertainty intervals because this check has only six blocks per comparison.

| condition | normalized gain | learned skills | gap coverage | leakage | chitchat |
|---|---:|---:|---:|---:|---:|
| vanilla | -0.104 +/- 0.058 | 0.000 | 0.000 | 0.000 | 0.965 |
| socratic | -0.122 +/- 0.072 | 0.000 | 0.026 | 0.000 | 0.785 |
| gla_fixed | -0.026 +/- 0.077 | 0.667 | 0.611 | 0.000 | 0.007 |
| gla_reactive | -0.090 +/- 0.033 | 0.000 | 0.525 | 0.028 | 0.000 |
| gla_full | 0.017 +/- 0.076 | 1.000 | 0.203 | 0.000 | 0.264 |

| comparison | paired mean difference | bootstrap 95% interval | exact sign-flip p |
|---|---:|---:|---:|
| gla_full - vanilla | 0.122 | [0.042, 0.195] | 0.09375 |
| gla_full - socratic | 0.139 | [0.051, 0.222] | 0.09375 |
| gla_full - gla_fixed | 0.043 | [-0.045, 0.139] | 0.50000 |
| gla_full - gla_reactive | 0.107 | [0.035, 0.166] | 0.06250 |

The runner's pooled permutation tests were `p=.0210`, `.0146`, `.3545`, and
`.0135` for the same four comparisons, respectively. The direction against
the two prompt baselines persists, while the full-versus-fixed component
contrast is small and uncertain. This check therefore supports a cautious
baseline comparison and bounds claims about component generality across model
families. It is exploratory and does not replace the canonical Qwen3.5
dataset.
