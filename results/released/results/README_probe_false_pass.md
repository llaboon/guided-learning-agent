# Double-probe calibration

The commonly cited 0.25% value is the probability of two independent lucky
guesses at exactly `m=0`. For a partially mastered skill, the simulator uses
`P(correct|m)=0.05+0.85m`, so the two-pass probability is its square and rises
with `m`. `probe_false_pass_table.json` reports the values used for the
qualification in the manuscript.
