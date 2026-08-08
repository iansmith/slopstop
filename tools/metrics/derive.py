#!/usr/bin/env python3
"""Derive per-launch facts for a run from the HARNESS transcript, not from the orchestrator.

    python3 tools/metrics/derive.py <TICKET> --repo <path>        # write run-derived.jsonl
    python3 tools/metrics/derive.py <TICKET> --repo <path> --check # compare against run.jsonl

WHY THIS EXISTS (BILL-494).  `run.jsonl` is written by the orchestrator as it goes, which
makes every line in it a *claim*.  PLTF-2563 shows what that costs: the `implement` span
opened and was never closed, the `close` span was stamped twice in one command, and no
`waiting_for_user` span was ever written -- so the run's own verdict was "no timing numbers
may be derived from this file".  Anthropic's guidance is explicit that a model "can fail to
follow a prompted rule" under pressure or in a long session, and that a real guardrail has to
be deterministic.  A 97-minute run is a long session.

The harness, meanwhile, recorded all of it: one child transcript per subagent, each carrying
the model, the effort, and exact bounds.  This reads those.  It adds no instruction anyone can
skip, which is the property the deleted `tools/metrics/spans.py` called out explicitly --
"a collector change, not a process change".

TWO FILES, DELIBERATELY.  The derived record is written BESIDE `run.jsonl`, never into it:

  * Appending would break invariant 4 -- a completed run's last line must be `run_closed`, and
    derived lines land after it.  The file is append-only, so re-sorting is not available.
  * More importantly, merging destroys the audit.  `run.jsonl` holds the orchestrator's claims;
    this holds the harness's observations.  Keeping them apart is what lets one check the
    other; a merged file can only be checked against itself.

`:archive` needs no change -- it already pushes every file in the tracking directory.

RECOVERY.  Because nothing here depends on the orchestrator surviving, a run killed by quota
exhaustion loses `run.jsonl`'s tail and loses nothing here.  Derive early anyway: transcripts
get deleted for size (PLTF-2563's were, at 25 MB), and this output is a few hundred bytes per
launch.
"""

import argparse
import collections
import json
import pathlib
import re
import sys

PROJECTS = pathlib.Path.home() / ".claude" / "projects"


def slug(repo: pathlib.Path) -> str:
    """~/.claude/projects uses the absolute path with separators replaced by '-'."""
    return str(repo.resolve()).replace("/", "-")


def _load(path):
    for line in path.open():
        line = line.strip()
        if line:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def child_facts(path: pathlib.Path):
    """model, effort and true bounds for one subagent, straight from its own transcript."""
    models, effort, first, last, n = collections.Counter(), None, None, None, 0
    for d in _load(path):
        msg = d.get("message") or {}
        if msg.get("model"):
            models[msg["model"]] += 1
            n += 1
        for src in (d, msg):
            if "effort" in src:
                effort = src["effort"]
        ts = d.get("timestamp")
        if ts:
            first = first or ts
            last = ts
    return {"agent_id": path.stem.removeprefix("agent-"),
            "model_observed": models.most_common(1)[0][0] if models else None,
            "effort_observed": effort, "started_at": first, "finished_at": last,
            "assistant_messages": n}


def launches(session: pathlib.Path):
    """Every Agent/Task launch the parent made, in order, with what it ASKED for."""
    out, pending = [], {}
    for d in _load(session):
        ts = d.get("timestamp")
        for c in ((d.get("message") or {}).get("content") or []):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") in ("Task", "Agent"):
                i = c.get("input") or {}
                rec = {"label": i.get("description"), "requested_at": ts,
                       "subagent_type": i.get("subagent_type"),
                       "model_requested": i.get("model"), "agent_id": None}
                pending[c["id"]] = rec
                out.append(rec)
            # Only ASYNC launches report an agentId; sync ones return the agent's text.
            # So agentId is an exact link when present, and absence is normal, not an error.
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                blob = json.dumps(c.get("content"))
                m = blob.find("agentId: ")
                if m != -1:
                    pending[c["tool_use_id"]]["agent_id"] = blob[m + 9:].split()[0].strip('",')
    return out


def window(track):
    """The run's own [first, last] `at`, used to scope which subagents belong to it.

    Without this the deriver collects every subagent the repo has ever run -- 128 of them on
    server-v2, spanning a dozen tickets -- and a cross-check then matches 'implement' against
    whichever ticket happened to use that word first. The run.jsonl bounds are the honest
    scope: they are what the orchestrator itself says this run covered.
    """
    if not (track and (track / "run.jsonl").exists()):
        return None, None
    ats = sorted(d["at"] for d in _load(track / "run.jsonl") if d.get("at"))
    return (ats[0][:19], ats[-1][:19]) if ats else (None, None)


def attribute(rows, ticket):
    """Keep only the launches belonging to `ticket`, by label, carrying forward.

    The time window alone is NOT attribution, and trusting it produced a confidently wrong
    report: PLTF-2565's run.jsonl opens at its morning intake and closes ten hours later, so its
    window swallows PLTF-2562's and PLTF-2563's entire runs. `--check` then compared 1 launch
    note against 28 launches and called it a mismatch, when the run made exactly one launch and
    recorded exactly one note -- perfect agreement reported as near-total failure.

    Carry-forward rather than a strict key match, because plenty of real launches never name
    their ticket: "Handoff requirements adversary", "Delta check round 2", "Re-run
    mutation-check on tip". A strict filter drops those; the window wrongly claims them. The
    last ticket key seen in a label, in time order, is the one they belong to.

    A launch before any labelled launch is unattributable. It is dropped and counted, never
    assigned to the requested ticket on the grounds that nothing else claimed it.
    """
    keys = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
    out, cur, unattributed = [], None, 0
    for r in sorted(rows, key=lambda r: r.get("started_at") or ""):
        found = keys.findall(str(r.get("stage") or ""))
        if found:
            cur = found[0]
        if cur is None:
            unattributed += 1
            continue
        if cur == ticket:
            out.append({**r, "attributed_via": "label" if found else "carry-forward"})
    return out, unattributed


def derive(repo: pathlib.Path, ticket: str, lo=None, hi=None):
    root = PROJECTS / slug(repo)
    if not root.is_dir():
        sys.exit(f"no transcripts for {repo} at {root}")
    rows = []
    for session in sorted(root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        subs = root / session.stem / "subagents"
        if not subs.is_dir():
            continue
        kids = sorted((child_facts(p) for p in subs.glob("agent-*.jsonl")),
                      key=lambda k: k["started_at"] or "")
        if lo:
            kids = [k for k in kids if k["started_at"] and lo <= k["started_at"][:19] <= hi]
        if not kids:
            continue
        by_id = {k["agent_id"]: k for k in kids}
        used = set()
        for lch in launches(session):
            kid = by_id.get(lch["agent_id"]) if lch["agent_id"] else None
            if kid is None:
                # Sync launch: no agentId exists, so match on time -- the first child that
                # started at or after this launch and has not already been claimed.
                kid = next((k for k in kids if k["agent_id"] not in used
                            and (k["started_at"] or "") >= (lch["requested_at"] or "")), None)
            if kid is None:
                continue
            used.add(kid["agent_id"])
            rows.append({"ticket": ticket, "event": "derived", "stage": lch["label"],
                         "source": "harness-transcript", "session": session.stem,
                         **{k: v for k, v in lch.items() if k != "label"}, **kid})
    return rows


def seconds(a, b):
    import datetime as dt
    fmt = "%Y-%m-%dT%H:%M:%S"
    try:
        return (dt.datetime.strptime(b[:19], fmt) - dt.datetime.strptime(a[:19], fmt)).total_seconds()
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticket")
    ap.add_argument("--repo", required=True, type=pathlib.Path)
    ap.add_argument("--tracking", help="tracking dir (default: <repo>/.slopstop/ticket-*/<TICKET>)")
    ap.add_argument("--check", action="store_true", help="compare against run.jsonl, write nothing")
    ap.add_argument("--all", action="store_true",
                    help="every subagent in the repo, not just this run's window")
    args = ap.parse_args()

    track = pathlib.Path(args.tracking) if args.tracking else next(
        (p for p in args.repo.glob(f".slopstop/ticket-*/{args.ticket}") if p.is_dir()), None)
    lo, hi = (None, None) if args.all else window(track)
    rows = derive(args.repo, args.ticket, lo, hi)
    if not rows:
        sys.exit("no subagent transcripts found — nothing to derive")
    if not args.all:
        rows, dropped = attribute(rows, args.ticket)
        if dropped:
            print(f"  ({dropped} launch(es) before the first labelled one — unattributable, dropped)")
        if not rows:
            sys.exit(f"no launches attributable to {args.ticket}")

    print(f"  {len(rows)} launches derived from the harness transcript\n")
    print(f"  {'stage':34s} {'model':16s} {'effort':7s} {'sec':>6s}  subagent_type")
    for r in rows:
        d = seconds(r["started_at"], r["finished_at"])
        print(f"  {str(r['stage'])[:33]:34s} {str(r['model_observed']):16s} "
              f"{str(r['effort_observed']):7s} {d if d is None else int(d):>6}  {r['subagent_type']}")

    if args.check:
        crosscheck(rows, track)
        return
    if track and track.is_dir():
        out = track / "run-derived.jsonl"
        with out.open("a") as fh:                      # append-only, like run.jsonl
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(f"\n  wrote {out}")
    else:
        print("\n  no tracking dir found — printed only, nothing written")


def crosscheck(rows, track):
    """Compare the harness's observations against the orchestrator's claims."""
    if not (track and (track / "run.jsonl").exists()):
        print("\n  no run.jsonl to check against")
        return
    claims = list(_load(track / "run.jsonl"))
    opened = {}
    problems = []
    for d in claims:
        if d.get("event") != "span":
            continue
        if d.get("state") == "started":
            opened[d["stage"]] = d["at"]
        else:
            opened.pop(d["stage"], None)
    for stage, at in opened.items():
        cand = [r for r in rows if r["finished_at"] and stage.lower() in str(r["stage"]).lower()]
        fix = cand[0]["finished_at"] if cand else "unknown"
        problems.append(f"UNCLOSED span '{stage}' opened {at} — harness says it ended {fix}")
    claimed_launches = sum(1 for d in claims if (d.get("launch") or {}))
    if claimed_launches != len(rows):
        problems.append(f"launch notes in run.jsonl: {claimed_launches}; "
                        f"launches the harness recorded: {len(rows)}")
    print("\n  --- cross-check: harness vs orchestrator ---")
    for p in problems:
        print(f"  MISMATCH  {p}")
    if not problems:
        print("  the two records agree")


if __name__ == "__main__":
    main()
