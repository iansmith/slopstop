#!/usr/bin/env python3
"""Deep dive: baseline overhead, context growth, tool_result bytes, wall-clock."""
import json, os, glob, collections, statistics as st, datetime

ROOT = os.path.expanduser("~/.claude/projects")
TARGETS = ["-Users-iansmith-ticket-plugin", "-Users-iansmith-lyos-mobile-v2",
           "-Users-iansmith-louis14", "-Users-iansmith-mazzy", "-Users-iansmith-sophie"]

def ch2tok(n): return n // 4

res_bytes = collections.Counter()   # tool name -> total chars of tool_result
res_calls = collections.Counter()
res_max   = collections.Counter()
first_turn = collections.defaultdict(list)   # proj -> first-turn prompt tokens
growth = collections.defaultdict(list)       # bucket -> prompt tokens
durations = []                                # (hours, cost-ish turns, proj)
big_bash = []                                 # (chars, snippet)

for proj in TARGETS:
    pdir = os.path.join(ROOT, proj)
    if not os.path.isdir(pdir): continue
    for fp in glob.glob(os.path.join(pdir, "*.jsonl")):
        pend = {}   # tool_use_id -> name
        turn_i = 0
        ftok = None
        tsmin = tsmax = None
        nturns = 0
        with open(fp, errors="replace") as fh:
            for line in fh:
                if '"' not in line: continue
                try: d = json.loads(line)
                except Exception: continue
                ts = d.get("timestamp")
                if ts:
                    if tsmin is None or ts < tsmin: tsmin = ts
                    if tsmax is None or ts > tsmax: tsmax = ts
                msg = d.get("message") or {}
                content = msg.get("content")
                # map tool_use ids to names
                if isinstance(content, list):
                    for c in content:
                        if not isinstance(c, dict): continue
                        if c.get("type") == "tool_use":
                            pend[c.get("id")] = c.get("name")
                        elif c.get("type") == "tool_result":
                            nm = pend.get(c.get("tool_use_id"), "?")
                            body = c.get("content")
                            if isinstance(body, list):
                                txt = "".join(x.get("text","") for x in body if isinstance(x,dict))
                            else:
                                txt = str(body or "")
                            n = len(txt)
                            res_bytes[nm] += n; res_calls[nm] += 1
                            if n > res_max[nm]: res_max[nm] = n
                            if nm == "Bash" and n > 40000:
                                big_bash.append((n, txt[:180].replace("\n"," ")))
                u = msg.get("usage")
                if isinstance(u, dict) and msg.get("model"):
                    p = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                    turn_i += 1; nturns += 1
                    if ftok is None:
                        ftok = p; first_turn[proj].append(p)
                    for lo,hi,lbl in [(1,1,"turn 1"),(2,10,"turns 2-10"),(11,50,"11-50"),
                                      (51,150,"51-150"),(151,400,"151-400"),(401,10**9,"401+")]:
                        if lo <= turn_i <= hi: growth[lbl].append(p); break
        if tsmin and tsmax and nturns >= 20:
            try:
                a=datetime.datetime.fromisoformat(tsmin.replace("Z","+00:00"))
                b=datetime.datetime.fromisoformat(tsmax.replace("Z","+00:00"))
                durations.append(((b-a).total_seconds()/3600, nturns, proj))
            except Exception: pass

print("="*74); print("BASELINE OVERHEAD  (turn-1 prompt tokens = system + tools + skills + CLAUDE.md)"); print("="*74)
for p, v in first_turn.items():
    if v: print(f"  {p[-34:]:34s} n={len(v):4d}  median={int(st.median(v)):8,d}  p10={int(sorted(v)[len(v)//10]):8,d}  min={min(v):8,d}")
allf = [x for v in first_turn.values() for x in v]
print(f"  ALL: median turn-1 prompt = {int(st.median(allf)):,} tokens")

print(); print("="*74); print("CONTEXT GROWTH — median prompt tokens by turn index"); print("="*74)
for lbl in ["turn 1","turns 2-10","11-50","51-150","151-400","401+"]:
    v = growth.get(lbl)
    if not v: continue
    print(f"  {lbl:12s} n={len(v):7,d}  median={int(st.median(v)):8,d}  p90={int(sorted(v)[int(len(v)*0.9)]):8,d}")

print(); print("="*74); print("TOOL_RESULT VOLUME — what is actually filling the context"); print("="*74)
tot = sum(res_bytes.values())
print(f"  total tool_result chars = {tot:,}  (~{ch2tok(tot):,} tokens)")
for nm, n in res_bytes.most_common(14):
    print(f"    {str(nm)[:40]:40s} {ch2tok(n):11,d} tok  {100*n/tot:5.1f}%  calls={res_calls[nm]:7,d}  avg={ch2tok(n)//max(1,res_calls[nm]):7,d}  max={ch2tok(res_max[nm]):8,d}")

print(); print("="*74); print(f"BASH RESULTS > 10k tokens  (n={len(big_bash)})"); print("="*74)
for n, snip in sorted(big_bash, reverse=True)[:12]:
    print(f"  ~{ch2tok(n):7,d} tok | {snip[:150]}")

print(); print("="*74); print("WALL-CLOCK (sessions with >=20 turns)"); print("="*74)
if durations:
    hs=[d[0] for d in durations]
    print(f"  n={len(durations)}  median={st.median(hs):.2f}h  mean={sum(hs)/len(hs):.2f}h  p90={sorted(hs)[int(len(hs)*0.9)]:.2f}h  max={max(hs):.1f}h")
    per=[d[0]*3600/d[1] for d in durations]
    print(f"  seconds per assistant turn: median={st.median(per):.1f}s  p90={sorted(per)[int(len(per)*0.9)]:.1f}s")
