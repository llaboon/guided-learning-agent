# No-learning null

`no_learning_null.json` reports 10,000 independent pre/post test pairs per
profile while the ground-truth mastery state is held fixed. The test uses one
item per skill and the same normalized-gain formula as the main experiment.
The near-zero means and the reported quantiles quantify the measurement noise
that can produce small negative gains without tutoring progress.

Re-run with

```bash
python experiments/no_learning_null.py --draws 10000 \
  --out paper/aamas/supplement/results/no_learning_null.json
```
