#!/usr/bin/env python3
"""Aggregate real token/cost telemetry from Claude Code transcripts."""
import json, os, sys, glob, collections, datetime, pathlib

ROOT = os.path.expanduser("~/.claude/projects")

# USD per 1M tokens. cacheWrite=1.25x in, cacheRead=0.1x in (5m TTL).
RATES = {
    "opus":   (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku":  (0.80, 4.0),
    "fable":  (3.0, 15.0),   # guess; treat as sonnet-class
}

def fam(model):
    m = (model or "").lower()
    for k in RATES:
        if k in m: return k
    if not m or m == "<synthetic>": return None
    return "other"

def cost(f, i, o, cw, cr):
    r = RATES.get(f)
    if not r: return 0.0
    inr, outr = r
    return (i*inr + o*outr + cw*inr*1.25 + cr*inr*0.10) / 1e6

sessions = []   # dict per transcript
for proj in sorted(os.listdir(ROOT)):
    pdir = os.path.join(ROOT, proj)
    if not os.path.isdir(pdir): continue
    for fp in glob.glob(os.path.join(pdir, "*.jsonl")):
        s = {
            "proj": proj, "file": os.path.basename(fp),
            "i":0,"o":0,"cw":0,"cr":0,"cost":0.0,
            "turns":0, "models": collections.Counter(),
            "switches":0, "seq": [], "first":None,"last":None,
            "compacts":0, "tool_calls":collections.Counter(),
            "sidechain_turns":0,
        }
        last_model = None
        try:
            with open(fp, "r", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line and '"isCompactSummary"' not in line:
                        continue
                    try: d = json.loads(line)
                    except Exception: continue
                    if d.get("isCompactSummary"): s["compacts"] += 1
                    msg = d.get("message") or {}
                    u = msg.get("usage")
                    ts = d.get("timestamp")
                    if ts:
                        if s["first"] is None or ts < s["first"]: s["first"] = ts
                        if s["last"] is None or ts > s["last"]: s["last"] = ts
                    if not isinstance(u, dict): continue
                    model = msg.get("model")
                    f = fam(model)
                    if f is None: continue
                    i  = u.get("input_tokens") or 0
                    o  = u.get("output_tokens") or 0
                    cw = u.get("cache_creation_input_tokens") or 0
                    cr = u.get("cache_read_input_tokens") or 0
                    s["i"]+=i; s["o"]+=o; s["cw"]+=cw; s["cr"]+=cr
                    s["cost"] += cost(f,i,o,cw,cr)
                    s["turns"] += 1
                    if d.get("isSidechain"): s["sidechain_turns"] += 1
                    s["models"][model] += 1
                    if last_model is not None and model != last_model:
                        s["switches"] += 1
                        s["seq"].append(model)
                    if last_model is None: s["seq"].append(model)
                    last_model = model
                    for c in (msg.get("content") or []):
                        if isinstance(c, dict) and c.get("type")=="tool_use":
                            s["tool_calls"][c.get("name")] += 1
        except Exception as e:
            continue
        if s["turns"]: sessions.append(s)

json.dump(sessions, open(sys.argv[1] if len(sys.argv)>1 else "/tmp/sessions.json","w"))
print("sessions parsed:", len(sessions))
