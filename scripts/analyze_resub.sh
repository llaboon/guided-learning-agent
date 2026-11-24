#!/usr/bin/env bash
# Run all CPU analyses over results/resub and write results/resub/analysis/*.
cd "$(dirname "$0")/.."
R=results/resub; A=$R/analysis; mkdir -p $A
ap () { out=$1; shift; python3 experiments/analyze_paired.py "$@" --metrics norm_gain,n_learned,leakage_rate,chitchat_rate --out $A/$out.json --brief > $A/$out.txt; }
ap main $R/main/experiment_*.json $R/main_fill1/experiment_*.json $R/main_fill2/experiment_*.json $R/validated/experiment_*.json
ap softgate $R/softgate/experiment_*.json
ap thr09 $R/thr09/experiment_*.json
ap xjudge $R/xjudge/experiment_*.json $R/xjudge_fill/experiment_*.json
ap xtutor $R/xtutor/experiment_*.json
[ -d $R/branched ] && ap branched $R/branched/experiment_*.json
[ -d $R/branched ] && ap branched_scatter $R/branched/experiment_*.json --profiles scatter
python3 experiments/replay_sensitivity.py --results-dir $R/main,$R/main_fill1,$R/main_fill2 \
  --out $A/replay_sensitivity.json > /dev/null
python3 experiments/summarize_replay.py $A/replay_sensitivity.json > $A/replay_sensitivity.txt
echo ANALYSIS_DONE
cat $A/*.txt
