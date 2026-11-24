#!/usr/bin/env bash
# Progress of resubmission phases.
cd "$(dirname "$0")/.."
for d in results/resub/*/; do
  log="$d/run.log"; [ -f "$log" ] || continue
  n=$(grep -c '^\[done' "$log"); f=$(grep -c '^\[FAIL' "$log")
  tot=$(grep -m1 -o 'total runs: [0-9]*' "$log")
  fin=$(grep -c EXPERIMENT_DONE "$log")
  echo "$(basename "$d"): done=$n fail=$f $tot finished=$fin"
  grep '^\[FAIL' "$log" | head -2 | cut -c1-200
done
