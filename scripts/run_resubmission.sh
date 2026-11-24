#!/usr/bin/env bash
# Resubmission experiment driver.  Usage: bash scripts/run_resubmission.sh <phase>
# Endpoints (override with env vars):
#   QWEN_URL   tutor / in-experiment judge (Qwen3.5-35B-A3B)
#   CHILD_URL  child renderer (Qwen3.5-0.8B)
#   XFAM_URL   cross-family model (gemma-4-31B-it): validator / judge / tutor
set -u
cd "$(dirname "$0")/.."
QWEN_URL=${QWEN_URL:-http://localhost:8101/v1}
CHILD_URL=${CHILD_URL:-http://localhost:8102/v1}
XFAM_URL=${XFAM_URL:-http://localhost:8103/v1}
W=${WORKERS:-16}
SEEDS=${SEEDS:-1,2,3,4,5}
export GLA_STUDENT_URL=$CHILD_URL

run () {  # name, extra args...
  local name=$1; shift
  export GLA_RESULTS_DIR=$PWD/results/resub/$name
  mkdir -p "$GLA_RESULTS_DIR"
  echo "==== PHASE $name start $(date -Is) ===="
  python3 experiments/run_experiment.py --turns 24 --workers "$W" --tag "$name" "$@" \
    2>&1 | tee "$GLA_RESULTS_DIR/run.log"
  echo "==== PHASE $name end $(date -Is) ===="
}

case "${1:-}" in
  main)      # E1: primary conditions + informed baseline + single probe, drawn outcomes logged
    GLA_TUTOR_URL=$QWEN_URL GLA_JUDGE_URL=$QWEN_URL \
      run main --seeds "$SEEDS" --conditions vanilla,socratic,gla_fixed,gla_reactive,gla_full,informed,gla_single_probe ;;
  validated) # E2: C4 + programmatic validator (validator = cross-family model)
    GLA_TUTOR_URL=$QWEN_URL GLA_JUDGE_URL=$QWEN_URL \
      run validated --seeds "$SEEDS" --conditions gla_full_validated --validator-url "$XFAM_URL" ;;
  softgate)  # E3: live rerun under a soft prerequisite gate
    GLA_GATE=soft_min GLA_TUTOR_URL=$QWEN_URL GLA_JUDGE_URL=$QWEN_URL \
      run softgate --seeds "$SEEDS" --conditions gla_fixed,gla_reactive,gla_full,informed ;;
  thr09)     # E3b: live rerun with mastery threshold 0.9
    GLA_MASTERY_THRESHOLD=0.9 GLA_TUTOR_URL=$QWEN_URL GLA_JUDGE_URL=$QWEN_URL \
      run thr09 --seeds "$SEEDS" --conditions gla_fixed,gla_reactive,gla_full,informed ;;
  xjudge)    # E4a: cross-family judge (Gemma annotates and drives the simulator)
    GLA_TUTOR_URL=$QWEN_URL GLA_JUDGE_URL=$XFAM_URL \
      run xjudge --seeds 1,2,3 --conditions vanilla,socratic,gla_fixed,gla_reactive,gla_full,informed ;;
  xtutor)    # E4b: cross-family tutor (Gemma tutors, Qwen judges)
    GLA_TUTOR_URL=$XFAM_URL GLA_JUDGE_URL=$QWEN_URL \
      run xtutor --seeds 1,2,3 --conditions vanilla,socratic,gla_fixed,gla_reactive,gla_full,informed ;;
  branched)  # E5: branched domain incl. scatter profile, single vs double probe
    GLA_TUTOR_URL=$QWEN_URL GLA_JUDGE_URL=$QWEN_URL \
      run branched --domain early_math_branched --seeds 1,2,3 \
      --conditions gla_fixed,gla_reactive,gla_full,gla_single_probe,informed ;;
  fill)      # re-run failed cells: fill <name> <tutor_url> <judge_url> <run_experiment args...>
    shift; n=$1; tu=$2; ju=$3; shift 3
    GLA_TUTOR_URL=$tu GLA_JUDGE_URL=$ju run "$n" "$@" ;;
  *) echo "phase: main|validated|softgate|thr09|xjudge|xtutor|branched|fill"; exit 2 ;;
esac
