#!/usr/bin/env python3
import json, os, collections, statistics as st

S = json.load(open(os.environ.get("SESSIONS", "sessions.json")))
import collections as _c
for _r in S: _r["models"]=_c.Counter(_r["models"]); _r["tool_calls"]=_c.Counter(_r["tool_calls"])

def tot(k, rows=S): return sum(r[k] for r in rows)
def pct(a,b): return f"{100*a/b:.1f}%" if b else "n/a"

print("=" * 72)
print("GLOBAL  (all projects, all time)")
print("=" * 72)
print(f"sessions={len(S)}  turns={tot('turns'):,}")
print(f"input(uncached)={tot('i'):,}  output={tot('o'):,}  cacheWrite={tot('cw'):,}  cacheRead={tot('cr'):,}")
T = tot('i')+tot('cw')+tot('cr')
print(f"total prompt tokens = {T:,}")
print(f"  cacheRead share  = {pct(tot('cr'),T)}   <- ideal: very high")
print(f"  cacheWrite share = {pct(tot('cw'),T)}   <- cache (re)build cost")
print(f"  uncached share   = {pct(tot('i'),T)}")
print(f"est cost = ${tot('cost'):,.0f}")
print(f"output tokens as share of billed-expensive = {pct(tot('o'), tot('o')+tot('i'))} of (out+uncached-in)")

# ---- cost split by model family
print()
print("=" * 72); print("SPEND BY MODEL FAMILY (session-attributed by dominant model)"); print("=" * 72)
fam_cost = collections.Counter(); fam_tok = collections.Counter(); fam_sess=collections.Counter()
for r in S:
    for m,c in r["models"].items():
        f = "opus" if "opus" in (m or "") else "sonnet" if "sonnet" in (m or "") else "haiku" if "haiku" in (m or "") else "fable" if "fable" in (m or "") else "other"
        fam_tok[f] += c
    dom = r["models"].most_common(1)[0][0] or ""
    f = "opus" if "opus" in dom else "sonnet" if "sonnet" in dom else "haiku" if "haiku" in dom else "fable" if "fable" in dom else "other"
    fam_cost[f] += r["cost"]; fam_sess[f]+=1
for f,c in fam_cost.most_common():
    print(f"  {f:8s} ${c:10,.0f}  {pct(c,tot('cost')):>7s}  sessions={fam_sess[f]:5d}  assistant-turns={fam_tok[f]:,}")

# ---- THEORY 1: model switching / cache churn
print()
print("=" * 72); print("THEORY 1 — model switching & context clearing"); print("=" * 72)
multi = [r for r in S if len(r["models"])>1]
print(f"sessions using >1 model: {len(multi)}/{len(S)} ({pct(len(multi),len(S))})")
print(f"  their spend: ${tot('cost',multi):,.0f} ({pct(tot('cost',multi),tot('cost'))} of total)")
sw = sorted(S, key=lambda r:-r["switches"])
print(f"  total in-session model switches: {tot('switches'):,}")
print(f"  median switches (multi-model sessions): {st.median([r['switches'] for r in multi]) if multi else 0}")
print()
print("  cacheWrite share by switch count bucket (higher = more cache rebuild):")
for lo,hi,lbl in [(0,0,"0 switches"),(1,2,"1-2"),(3,9,"3-9"),(10,10**9,"10+")]:
    b=[r for r in S if lo<=r["switches"]<=hi]
    if not b: continue
    tb=tot('i',b)+tot('cw',b)+tot('cr',b)
    print(f"    {lbl:12s} n={len(b):5d}  cacheWrite={pct(tot('cw',b),tb):>6s}  cacheRead={pct(tot('cr',b),tb):>6s}  $/session={tot('cost',b)/len(b):8,.2f}  $/turn={tot('cost',b)/max(1,tot('turns',b)):6.3f}")
print()
comp=[r for r in S if r["compacts"]>0]
print(f"  sessions with a compact summary: {len(comp)} ({pct(len(comp),len(S))}); their spend ${tot('cost',comp):,.0f} ({pct(tot('cost',comp),tot('cost'))})")

# ---- THEORY 2: skill/system-prompt baseline
print()
print("=" * 72); print("THEORY 2 — per-turn prompt weight (skills/system overhead proxy)"); print("=" * 72)
print("  mean prompt tokens per assistant turn (uncached+cacheWrite+cacheRead)/turns:")
for lbl, rows in [("ALL", S)]:
    print(f"    {lbl}: {(tot('i',rows)+tot('cw',rows)+tot('cr',rows))/max(1,tot('turns',rows)):,.0f} tok/turn")
byproj = collections.defaultdict(list)
for r in S: byproj[r["proj"]].append(r)
print("  per-project (top 12 by spend):  cacheWrite/turn is the churn signal")
rank = sorted(byproj.items(), key=lambda kv:-tot('cost',kv[1]))[:12]
for p,rows in rank:
    t=max(1,tot('turns',rows))
    print(f"    {p[-46:]:46s} $ {tot('cost',rows):9,.0f} sess={len(rows):4d} turns={tot('turns',rows):6,d} "
          f"prompt/turn={(tot('i',rows)+tot('cw',rows)+tot('cr',rows))//t:7,d} cw/turn={tot('cw',rows)//t:6,d} out/turn={tot('o',rows)//t:5,d}")

# ---- THEORY 3: gates in context -> output/turn and tool mix
print()
print("=" * 72); print("THEORY 3 — what is actually consuming turns (tool mix)"); print("=" * 72)
tc = collections.Counter()
for r in S: tc.update(r["tool_calls"])
tt = sum(tc.values())
for n,c in tc.most_common(18):
    print(f"    {str(n)[:44]:44s} {c:8,d}  {pct(c,tt):>6s}")

# ---- THEORY 4: fleet / subagent cost
print()
print("=" * 72); print("THEORY 4 — fleet worktrees & subagents"); print("=" * 72)
wt = [r for r in S if "worktree" in r["proj"]]
print(f"worktree sessions: {len(wt)} ({pct(len(wt),len(S))})  spend ${tot('cost',wt):,.0f} ({pct(tot('cost',wt),tot('cost'))})")
if wt:
    print(f"  $/worktree-session median=${st.median([r['cost'] for r in wt]):.2f} mean=${tot('cost',wt)/len(wt):.2f} max=${max(r['cost'] for r in wt):.2f}")
    fm=collections.Counter()
    for r in wt:
        for m,c in r["models"].items(): fm[m]+=c
    print("  models used inside worktree sessions:", dict(fm.most_common(6)))
side = [r for r in S if r["sidechain_turns"]>0]
print(f"sessions containing subagent (sidechain) turns: {len(side)} ({pct(len(side),len(S))})")
print(f"  sidechain turns = {tot('sidechain_turns'):,} of {tot('turns'):,} ({pct(tot('sidechain_turns'),tot('turns'))})")

# top-cost sessions
print()
print("=" * 72); print("TOP 15 SESSIONS BY COST"); print("=" * 72)
for r in sorted(S,key=lambda r:-r["cost"])[:15]:
    t=max(1,r["turns"])
    print(f"  ${r['cost']:8,.2f} turns={r['turns']:5d} sw={r['switches']:3d} cmp={r['compacts']:2d} "
          f"prompt/turn={(r['i']+r['cw']+r['cr'])//t:7,d} cw={r['cw']:11,d} cr={r['cr']:12,d} {r['proj'][-40:]}")
