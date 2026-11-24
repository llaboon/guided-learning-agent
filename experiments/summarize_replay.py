"""Compact table of replay_sensitivity.json (C4 vs each condition)."""
import json
import sys

rep = json.load(open(sys.argv[1], encoding="utf-8"))
print("usable traces:", rep["n_usable"], "skipped:", rep["n_skipped"])
for name, v in rep["variants"].items():
    s = v["summary"]
    means = {c: s[c]["true_gain"]["mean"] for c in sorted(s)}
    print("VAR", name, "mean_true_gain", {c: round(x, 3) for c, x in means.items()})
    for comp, mets in v["pairwise"].items():
        g = mets["true_gain"]; n = mets["n_learned"]
        print("  ", comp, "gain", g["mean"], [g["lo"], g["hi"]], "| learned", n["mean"], [n["lo"], n["hi"]])
