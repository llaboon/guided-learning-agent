"""Cross-family annotation agreement (reviewer qKCP-5, a7k4-2).

Re-annotates every tutor turn of saved traces with a second annotator
(e.g. gemma-4-31B-it) using the identical prompt, and reports per-field
agreement and Cohen's kappa against the in-experiment (Qwen) labels.

    GLA_REANN_URL=http://localhost:8103/v1 python3 experiments/reannotate.py \
        "results/resub/main/exp_*.json" --out results/resub/analysis/reannotation.json
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gla.annotator import annotate_tutor_turn  # noqa: E402
from gla.knowledge_map import load_domain  # noqa: E402
from gla.llm import Endpoint  # noqa: E402


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0, round(po, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("--domain", default="early_math")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    kmap = load_domain(a.domain)
    ep = Endpoint(os.environ["GLA_REANN_URL"], os.environ.get("GLA_REANN_MODEL"), tag="reann")
    items = []
    for path in sorted(glob.glob(a.pattern)):
        t = json.load(open(path, encoding="utf-8"))
        tutor_turns = [x["text"] for x in t["transcript"] if x["role"] == "tutor"]
        for text, ann in zip(tutor_turns, t["annotations"]):
            items.append((t["condition"], text, ann))
    with ThreadPoolExecutor(a.workers) as ex:
        new = list(ex.map(lambda it: annotate_tutor_turn(ep, kmap, it[1]), items))
    rep = {"annotator": ep.model, "n_turns": len(items), "fields": {}, "by_condition_leak": {}}
    for field in ("skill", "act", "leaked", "comprehensible"):
        k, po = kappa([str(i[2][field]) for i in items], [str(n[field]) for n in new])
        rep["fields"][field] = {"agreement": po, "kappa": k}
    collapse = lambda x: "ask" if x in ("ask", "both") else x  # noqa: E731
    k, po = kappa([collapse(i[2]["act"]) for i in items], [collapse(n["act"]) for n in new])
    rep["fields"]["act_collapsed_ask_both"] = {"agreement": po, "kappa": k}
    rep["act_confusion"] = Counter(f"{i[2]['act']}->{n['act']}" for i, n in zip(items, new)).most_common(12)
    for c in sorted({i[0] for i in items}):
        idx = [j for j, i in enumerate(items) if i[0] == c and i[2]["act"] in ("teach", "ask", "both")]
        q = sum(items[j][2]["leaked"] for j in idx) / max(len(idx), 1)
        g = sum(new[j]["leaked"] for j in idx) / max(len(idx), 1)
        rep["by_condition_leak"][c] = {"n_substantive": len(idx), "qwen": round(q, 4), "reannotator": round(g, 4)}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: rep[k] for k in ("annotator", "n_turns", "fields", "by_condition_leak")}, ensure_ascii=False, indent=1))
    print("REANNOTATION_DONE")


if __name__ == "__main__":
    main()
