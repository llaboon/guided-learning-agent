"""Design-aware analysis of experiment result files (CPU only).

Unit = profile-seed block (every block appears under every condition).
For each comparison against a reference condition we report the mean paired
difference, a percentile bootstrap 95% CI over blocks, the exact sign-flip
p-value, and Holm-adjusted p-values across the comparison family.

    python experiments/analyze_paired.py results/resub/main/experiment_*.json \
        --ref gla_full --metrics norm_gain,n_learned --out out.json
"""

import argparse
import glob
import itertools
import json
import math
import random


def load_rows(patterns):
    rows = []
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            with open(path, encoding="utf-8") as f:
                rows.extend(json.load(f)["rows"])
    # keep the last row per (condition, profile, seed)
    dedup = {}
    for r in rows:
        dedup[(r["condition"], r["profile"], r["seed"])] = r
    return list(dedup.values())


def signflip_p(diffs):
    n = len(diffs)
    obs = abs(sum(diffs))
    if n <= 20:
        hits = total = 0
        for signs in itertools.product((1, -1), repeat=n):
            total += 1
            if abs(sum(s * d for s, d in zip(signs, diffs))) >= obs - 1e-12:
                hits += 1
        return hits / total
    rng = random.Random(3)
    hits = 0
    for _ in range(50000):
        if abs(sum(d if rng.random() < .5 else -d for d in diffs)) >= obs - 1e-12:
            hits += 1
    return hits / 50000


def boot_ci(diffs, draws=10000, seed=1):
    rng = random.Random(seed)
    ms = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(draws))
    return [round(ms[int(.025 * draws)], 4), round(ms[int(.975 * draws)], 4)]


def holm(pvals):
    order = sorted(pvals, key=lambda k: pvals[k])
    out, running = {}, 0.0
    m = len(order)
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvals[k]))
        out[k] = round(running, 5)
    return out


def summarize(rows, metrics):
    by = {}
    for r in rows:
        by.setdefault(r["condition"], []).append(r)
    out = {}
    for c, rs in sorted(by.items()):
        out[c] = {"n": len(rs)}
        for k in metrics:
            v = [r[k] for r in rs if r.get(k) is not None]
            if not v:
                continue
            m = sum(v) / len(v)
            sd = math.sqrt(sum((x - m) ** 2 for x in v) / max(len(v) - 1, 1))
            out[c][k] = [round(m, 4), round(sd, 4)]
    return out


def paired(rows, ref, metrics, others=None):
    blocks = {}
    for r in rows:
        blocks.setdefault(r["condition"], {})[(r["profile"], r["seed"])] = r
    res = {}
    for k in metrics:
        comps, pv = {}, {}
        for c in sorted(blocks):
            if c == ref or (others and c not in others):
                continue
            keys = sorted(set(blocks[ref]) & set(blocks[c]))
            if not keys:
                continue
            d = [blocks[ref][b][k] - blocks[c][b][k] for b in keys]
            p = signflip_p(d)
            comps[c] = {"n_blocks": len(d), "mean_diff": round(sum(d) / len(d), 4),
                        "ci95": boot_ci(d), "p_signflip": round(p, 5)}
            pv[c] = p
        for c, ph in holm(pv).items():
            comps[c]["p_holm"] = ph
        res[k] = comps
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--ref", default="gla_full")
    ap.add_argument("--metrics", default="norm_gain,n_learned,leakage_rate,chitchat_rate")
    ap.add_argument("--profiles", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--brief", action="store_true", help="print a compact table")
    a = ap.parse_args()
    rows = load_rows(a.files)
    if a.profiles:
        rows = [r for r in rows if r["profile"] in a.profiles.split(",")]
    metrics = a.metrics.split(",")
    rep = {"files": a.files, "ref": a.ref, "n_rows": len(rows),
           "summary": summarize(rows, metrics + ["validator_first_pass", "validator_final_pass"]),
           "paired_vs_ref": paired(rows, a.ref, metrics)}
    txt = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
    if not a.brief:
        print(txt)
        return
    for c, v in rep["summary"].items():
        print("SUM", c, v)
    for m, comps in rep["paired_vs_ref"].items():
        for c, v in comps.items():
            print("PAIR", m, f"{a.ref}-{c}", v["mean_diff"], v["ci95"], "p", v["p_signflip"], "holm", v["p_holm"], "n", v["n_blocks"])


if __name__ == "__main__":
    main()
