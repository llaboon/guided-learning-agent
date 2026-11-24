"""Print a compact view of one trace: python3 scripts/peek_trace.py <glob>."""
import glob
import json
import sys

path = sorted(glob.glob(sys.argv[1]))[-1]
t = json.load(open(path, encoding="utf-8"))
print(path)
for d, a in zip(t.get("directives") or [None] * len(t["annotations"]), t["annotations"]):
    print(d and (d["activity"], d["skill"]), (a["skill"], a["act"], a["leaked"], a.get("drawn_correct")))
for x in t["transcript"]:
    print(x["role"][:1], x["text"][:90].replace("\n", " "))
for r in t.get("validation_log") or []:
    print("VAL", r["activity"], [(x["ok"], x["problems"]) for x in r["attempts"]])
