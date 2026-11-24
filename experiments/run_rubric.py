"""Rubric panel: stronger-judge (Qwen3.5-122B) evaluation.

Component A (--mode annotate): turn-level re-annotation agreement. Re-annotates
tutor turns of sampled runs with the 122B judge using the SAME annotation
protocol as the 35B judge that drove the ground-truth state; reports per-field
agreement + Cohen's kappa on leakage.

Component B (--mode quality): blind session-level teaching-quality rubric,
scored under two fixed panel framings (child-education researcher /
developmental psychologist); reported per condition.

Usage:
  GLA_HOST=127.0.0.1 python3 experiments/run_rubric.py --mode annotate --workers 4
  GLA_HOST=127.0.0.1 python3 experiments/run_rubric.py --mode quality --workers 4
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from gla import config
from gla.annotator import annotate_tutor_turn
from gla.knowledge_map import load_domain
from gla.llm import Endpoint, strip_think

DEFAULT_DATASETS = ("results/experiment_1788234362.json",
                    "results/experiment_1788235140.json")
ANNOTATE_CONDS = (("gla_full", 6), ("vanilla", 6), ("gla_reactive", 4))

PANEL = (
    ("教研员", "你是一位资深幼儿数学教育教研员，正在盲评一节 AI 老师和 5 岁孩子的对话课。"
             "你不知道课程由哪种系统设计。请严格、独立地评审。"),
    ("发展心理学家", "你是一位儿童发展心理学专家，正在盲评一节 AI 老师和 5 岁孩子的对话课。"
                "你不知道课程由哪种系统设计。请严格、独立地评审。"),
)

RUBRIC_BODY = """请对下面这节对话课，从四个维度各打 1-5 分（1=很差 2=偏弱 3=中等 4=良好 5=很好）：
- lang 语言适配：教师语言是否符合 5 岁儿童水平（短句、具体、亲切、少术语）。
- scaffold 讲解与脚手架：讲解是否清晰有例子；是否「先教后练、答错退一步重教」；问题有无梯度。
- feedback 反馈与激励：对孩子回答（包含错误、走神、撒娇讨答案）的反馈是否具体、鼓励、有针对性。
- goal 目标一致性：是否围绕明确知识点推进，是否频繁跑题或空转。
只输出 JSON（不要别的）：
{"lang": n, "scaffold": n, "feedback": n, "goal": n, "comment": "<不超过40字的中文点评>"}

【对话开始】
{transcript}
【对话结束】"""


def _judge_endpoint():
    base = os.environ.get("GLA_RUBRIC_URL")
    if not base:
        host = os.environ.get("GLA_HOST", "127.0.0.1")
        base = f"http://{host}:8103/v1"
    return Endpoint(base, tag="rubric")


def _load_rows(datasets):
    rows = []
    for p in datasets:
        d = json.load(open(p))
        rows += d.get("rows", d.get("runs", []))
    return rows


def _trace(path):
    return json.load(open(path))


def _digest(trace):
    lines = []
    for t in trace["transcript"]:
        who = "师" if t["role"] == "tutor" else "生"
        lines.append(f"{who}: {t['text']}")
    return "\n".join(lines)


def _parse_json(out):
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _kappa(a, b):
    """Cohen's kappa for two binary lists."""
    n = len(a)
    if n == 0:
        return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa = sum(a) / n
    pb = sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


# ---------------- component A: annotation agreement ----------------

def _annotate_run(args):
    ep, kmap, row = args
    tr = _trace(row["trace"])
    anns = tr["annotations"]
    turns = [t for t in tr["transcript"] if t["role"] == "tutor"]
    out = []
    for ann, t in zip(anns, turns):
        new = annotate_tutor_turn(ep, kmap, t["text"])
        out.append({
            "text": t["text"][:120],
            "orig": {k: ann.get(k) for k in ("skill", "act", "leaked", "comprehensible")},
            "new": {k: new.get(k) for k in ("skill", "act", "leaked", "comprehensible")},
        })
    return row["condition"], row["profile"], row["seed"], out


def mode_annotate(args):
    ep = _judge_endpoint()
    print(f"rubric judge model = {ep.model}", flush=True)
    kmap = load_domain(args.domain)
    rows = _load_rows(args.dataset)
    sel = []
    for cond, n in ANNOTATE_CONDS:
        rs = sorted([r for r in rows if r["condition"] == cond],
                    key=lambda r: (r["profile"], r["seed"]))[:n]
        sel += rs
    print(f"sampled runs: {len(sel)}", flush=True)

    all_turns, by_run = [], []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_annotate_run, (ep, kmap, r)) for r in sel]
        for k, f in enumerate(as_completed(futs), 1):
            cond, prof, seed, turns = f.result()
            by_run.append({"condition": cond, "profile": prof, "seed": seed,
                           "turns": turns})
            all_turns += turns
            print(f"[{k}/{len(sel)}] {cond}/{prof}/s{seed}: {len(turns)} turns "
                  f"({time.time()-t0:.0f}s)", flush=True)

    n = len(all_turns)
    act_ok = sum(1 for t in all_turns if t["new"]["act"] == t["orig"]["act"])
    sk_ok = sum(1 for t in all_turns
                if (t["new"]["skill"] or None) == (t["orig"]["skill"] or None))
    lk_o = [1 if t["orig"]["leaked"] else 0 for t in all_turns]
    lk_n = [1 if t["new"]["leaked"] else 0 for t in all_turns]
    cp_o = [1 if t["orig"]["comprehensible"] else 0 for t in all_turns]
    cp_n = [1 if t["new"]["comprehensible"] else 0 for t in all_turns]
    summary = {
        "n_turns": n, "n_runs": len(sel),
        "act_agreement": round(act_ok / n, 4),
        "skill_agreement": round(sk_ok / n, 4),
        "leaked_agreement": round(sum(1 for x, y in zip(lk_o, lk_n) if x == y) / n, 4),
        "leaked_kappa": round(_kappa(lk_o, lk_n), 4),
        "leaked_orig_rate": round(sum(lk_o) / n, 4),
        "leaked_new_rate": round(sum(lk_n) / n, 4),
        "comprehensible_agreement": round(sum(1 for x, y in zip(cp_o, cp_n) if x == y) / n, 4),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    out_path = os.path.join(config.RESULTS_DIR, f"rubric_annotate_{int(time.time())}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "runs": by_run}, f, ensure_ascii=False, indent=1)
    print(f"saved -> {out_path}")
    print("RUBRIC_A_DONE")


# ---------------- component B: quality rubric panel ----------------

def _quality_run(ep, row):
    tr = _trace(row["trace"])
    text = _digest(tr)
    scores = {}
    for name, intro in PANEL:
        user = RUBRIC_BODY.replace("{transcript}", text)
        out = strip_think(ep.chat(
            [{"role": "system", "content": intro},
             {"role": "user", "content": user}],
            temperature=0.0, max_tokens=600))
        d = _parse_json(out) or {}
        scores[name] = {k: d.get(k) for k in ("lang", "scaffold", "feedback", "goal")}
        scores[name]["comment"] = str(d.get("comment", ""))[:80]
    dims = ("lang", "scaffold", "feedback", "goal")
    panel_mean = {}
    for k in dims:
        vals = [scores[nm][k] for nm, _ in PANEL
                if isinstance(scores[nm].get(k), (int, float))]
        panel_mean[k] = round(sum(vals) / len(vals), 3) if vals else None
    vals = [v for v in panel_mean.values() if v is not None]
    panel_mean["overall"] = round(sum(vals) / len(vals), 3) if vals else None
    return {"condition": row["condition"], "profile": row["profile"],
            "seed": row["seed"], "scores": scores, "panel_mean": panel_mean}


def mode_quality(args):
    ep = _judge_endpoint()
    print(f"rubric judge model = {ep.model}", flush=True)
    rows = _load_rows(args.dataset)
    conds = args.conditions.split(",")
    sel = [r for r in rows if r["condition"] in conds]
    print(f"sessions to score: {len(sel)} (conds={conds})", flush=True)
    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_quality_run, ep, r): r for r in sel}
        for k, f in enumerate(as_completed(futs), 1):
            res = f.result()
            results.append(res)
            print(f"[{k}/{len(sel)}] {res['condition']}/{res['profile']}/s{res['seed']} "
                  f"panel={res['panel_mean']['overall']} ({time.time()-t0:.0f}s)", flush=True)

    print("\n== condition means (panel mean of 2 framings) ==")
    agg = {}
    for c in conds:
        rs = [r["panel_mean"] for r in results if r["condition"] == c]
        if not rs:
            continue
        agg[c] = {k: round(sum(r[k] for r in rs if r.get(k) is not None)
                           / max(len(rs), 1), 3)
                  for k in ("lang", "scaffold", "feedback", "goal", "overall")}
        print(f"  {c:13s} {json.dumps(agg[c], ensure_ascii=False)}")
    out_path = os.path.join(config.RESULTS_DIR, f"rubric_quality_{int(time.time())}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"aggregate": agg, "runs": results}, f, ensure_ascii=False, indent=1)
    print(f"saved -> {out_path}")
    print("RUBRIC_B_DONE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("annotate", "quality"), required=True)
    ap.add_argument("--dataset", default=",".join(DEFAULT_DATASETS))
    ap.add_argument("--domain", default="early_math")
    ap.add_argument("--conditions", default="gla_full,gla_fixed,vanilla")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    args.dataset = args.dataset.split(",")
    if args.mode == "annotate":
        mode_annotate(args)
    else:
        mode_quality(args)


if __name__ == "__main__":
    main()
