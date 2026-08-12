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


USAGE_FIELDS = ("input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens")


def child_facts(path: pathlib.Path):
    """model, effort, true bounds and COMPUTE for one subagent, from its own transcript.

    The four token fields are summed over every `message.usage` block in the transcript, which
    is one block per assistant turn.  They are the only place per-launch compute exists:
    `hook-events.jsonl` records a POINTER to this file (`agent_transcript_path`) and no usage,
    and `.slopstop/metrics/costs.jsonl` is session-scoped with no ticket and no stage.  So
    "what did stage 9 cost on this ticket" is answerable only by reading here -- and only until
    the transcript is deleted for size, which is why BILL-494's "derive early" note matters
    more now than it did when it only meant losing the model name.

    `active_seconds` is this subagent's own wall time, first timestamp to last.  Summed across
    a stage's launches it exceeds the stage's wall clock whenever that stage ran workers
    concurrently (`gates` runs three), and that difference is the measurement -- it is how much
    the concurrency actually bought.
    """
    models, effort, first, last, n = collections.Counter(), None, None, None, 0
    usage = collections.Counter()
    for d in _load(path):
        msg = d.get("message") or {}
        if msg.get("model"):
            models[msg["model"]] += 1
            n += 1
        for src in (d, msg):
            if "effort" in src:
                effort = src["effort"]
        for k, v in (msg.get("usage") or {}).items():
            if k in USAGE_FIELDS and isinstance(v, int):
                usage[k] += v
        ts = d.get("timestamp")
        if ts:
            first = first or ts
            last = ts
    return {"agent_id": path.stem.removeprefix("agent-"),
            "model_observed": models.most_common(1)[0][0] if models else None,
            "effort_observed": effort, "started_at": first, "finished_at": last,
            "assistant_messages": n,
            "active_seconds": seconds(first, last),
            **{k: usage[k] for k in USAGE_FIELDS}}


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


def derive(repo: pathlib.Path, ticket: str, lo=None, hi=None, root=None):
    root = pathlib.Path(root) if root else PROJECTS / slug(repo)
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


GAP_THRESHOLD_S = 120   # run-jsonl.md: itemised above, summed below. NEVER dropped.


def human(sec):
    """Compact duration. These run from seconds to hours; a bare float count reads badly."""
    if sec is None:
        return "?"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


SIZE_TIERS = ("trivial", "standard", "large")


def band(lines, files):
    """The documented bands (run-jsonl.md). `trivial` needs BOTH; `large` needs EITHER."""
    if lines <= 20 and files <= 2:
        return "trivial"
    if lines > 300 or files > 15:
        return "large"
    return "standard"


def run_mode(claims):
    """The ticket's mode, from the intake note.

    Prefers the structured `mode` field (BILL-580). Falls back to the prose it used to be
    written as, because every run recorded before that field existed only has prose -- and
    the two spellings observed in the wild disagree: AATK-81 wrote `mode: normal`, PLTF-2562
    wrote `mode=NORMAL`. Returns None when neither is readable, which is a reportable state
    rather than an assumed `normal`.

    Takes the LAST intake resolution, not the first. Mode can be re-resolved mid-run:
    PLTF-2562 opened `mode=NORMAL`, escalated a discrepancy (the body carried no marker but
    the DoD described a backfill), waited 29m36s for the owner to add one, and re-resolved
    to `mode=BACKFILL`. Reading the first note calls that ticket normal and silently passes
    the exact defect this check exists to catch.
    """
    found = None
    for d in claims:
        if d.get("stage") != "intake":
            continue
        if d.get("mode") in ("normal", "refactor", "backfill"):
            found = d["mode"]
            continue
        m = re.search(r"\bmode\s*[:=]\s*(normal|refactor|backfill)\b",
                      str(d.get("result") or ""), re.I)
        if m:
            found = m.group(1).lower()
    return found


def size_check(claims):
    """Validate the stage-10a size note: is the label readable, and is it the right label?

    Stage 10a exists to collect "the data that will later decide what is safe to skip", and
    across the nine tickets whose compute was recovered on 2026-08-12 it produced four
    different note shapes -- prose in the enum field, aggregates nested instead of top-level,
    totals with no production split, and a backfill ticket tiered from production counts that
    its own mode forbids being non-zero. Prose alone did not hold; this is the same
    enforcement shape BILL-574 used for the gap rule.

    Returns a list of problem strings, empty when the note is well-formed.
    """
    note = next((d for d in claims if d.get("stage") == "size"
                 and (d.get("tier") is not None or d.get("aggregates") is not None)), None)
    if note is None:
        return ["no size note recorded — stage 10a produced nothing to check"]

    problems, tier = [], note.get("tier")
    if tier not in SIZE_TIERS:
        shown = (str(tier)[:60] + "…") if tier and len(str(tier)) > 60 else repr(tier)
        problems.append(f"tier is not one of {'/'.join(SIZE_TIERS)}: {shown}")

    pl, pf = note.get("production_lines"), note.get("production_files")
    tl = note.get("test_lines")
    if not isinstance(pl, int) or not isinstance(pf, int):
        problems.append("no top-level production_lines/production_files — the production "
                        "split is what the tier is supposed to be computed from")
        return problems

    mode, basis = run_mode(claims), note.get("tier_basis")
    if mode == "backfill" and basis != "test":
        problems.append(
            f"backfill ticket tiered from {basis!r}: production changes are forbidden in "
            f"this mode, so production_lines={pl} is definitionally 0 and EVERY backfill "
            f"ticket scores {band(pl, pf)!r}. Basis should be 'test' "
            f"(test_lines={tl if tl is not None else '?'}).")
    elif tier in SIZE_TIERS:
        expect = band(pl, pf)
        if tier != expect:
            problems.append(f"tier {tier!r} disagrees with its own numbers: "
                            f"{pl} lines / {pf} files falls in {expect!r}")
    return problems


def gaps(claims):
    """Split every interval between consecutive run.jsonl lines by whether a span accounts for it.

    `run-jsonl.md` already defines both halves of this and neither is new here: the
    `waiting_for_user` span (:216), and the rule that ALL unbracketed time counts while the 120s
    threshold decides only what gets itemised (:541-546).  What was missing is anything that
    looks.  `:design` and `:tickets` bracket every question they ask; `:run` does not, so its
    owner waits land as unnamed gaps between two stage lines and sit silently inside whatever
    stage happens to precede them.

    Measured on AATK-81: 6h40m across two intervals -- a tamper waiver and a salvage escalation,
    both correct stops -- none of it visible in the run's own timing log.

    Bracketed time is reported separately rather than ignored: a measured wait is the outcome
    this check exists to produce, so it must be distinguishable from an absent one.  That is the
    `run-jsonl.md:763` split -- a run with hours of gaps and zero waits is UNMEASURED, which is
    not the same claim as measured-zero, and the two must never print the same.
    """
    lines = sorted((d for d in claims if d.get("at")), key=lambda d: d["at"])
    open_spans, itemised, residue, residue_n, bracketed = set(), [], 0.0, 0, 0.0
    for prev, nxt in zip(lines, lines[1:]):
        # Track EVERY open span, not just waiting_for_user. An interval between a stage's
        # `started` and its `finished` is that worker running -- it is accounted for, and
        # counting it as a gap reports the whole run as unattributed. Only an interval with
        # nothing open is a gap.
        if prev.get("event") == "span":
            if prev.get("state") == "started":
                open_spans.add(prev.get("stage"))
            else:
                open_spans.discard(prev.get("stage"))
        d = seconds(prev["at"], nxt["at"]) or 0.0
        if open_spans:
            if open_spans == {"waiting_for_user"}:
                bracketed += d
            continue
        if d > GAP_THRESHOLD_S:
            itemised.append((d, prev["at"], nxt["at"], prev.get("stage", "?")))
        else:
            residue += d
            residue_n += 1
    return itemised, residue, residue_n, bracketed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticket")
    ap.add_argument("--repo", type=pathlib.Path,
                    help="the repo whose run this is; required unless --transcripts is given")
    ap.add_argument("--tracking", help="tracking dir (default: <repo>/.slopstop/ticket-*/<TICKET>)")
    # The default root is derived from --repo, so it cannot be checked into a fixture: the slug
    # is an absolute path and changes with the checkout. This names the root directly, which
    # also makes a saved transcript bundle derivable after ~/.claude/projects has been reclaimed.
    ap.add_argument("--transcripts", help="transcript root (default: ~/.claude/projects/<slug>)")
    ap.add_argument("--check", action="store_true", help="compare against run.jsonl, write nothing")
    ap.add_argument("--all", action="store_true",
                    help="every subagent in the repo, not just this run's window")
    ap.add_argument("--redo", action="store_true",
                    help="replace an existing run-derived.jsonl instead of leaving it alone")
    args = ap.parse_args()
    if not (args.repo or args.transcripts):
        ap.error("--repo is required unless --transcripts names the transcript root directly")

    track = pathlib.Path(args.tracking) if args.tracking else next(
        (p for p in args.repo.glob(f".slopstop/ticket-*/{args.ticket}") if p.is_dir())
        if args.repo else iter(()), None)
    lo, hi = (None, None) if args.all else window(track)
    rows = derive(args.repo, args.ticket, lo, hi, args.transcripts)
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
        # Lazy on purpose: an unwindowed derive re-reads every subagent the repo has ever run
        # (128 on server-v2), and only the excess case has any use for them.
        crosscheck(rows, track, lambda: attribute(
            derive(args.repo, args.ticket, root=args.transcripts), args.ticket)[0])
        return
    if not (track and track.is_dir()):
        print("\n  no tracking dir found — printed only, nothing written")
        return

    out = track / "run-derived.jsonl"
    existing = sum(1 for _ in _load(out)) if out.exists() else 0

    # IDEMPOTENCE (BILL-576).  This file is append-only like `run.jsonl`, and appending a
    # SECOND derivation of the same run is not an append -- it is silent corruption.  Every
    # total read from the file inflates linearly with the number of times the deriver ran:
    # measured on AATK-81, three runs gave 20 / 40 / 60 rows and 613k / 1.23M / 1.84M output
    # tokens.  Nothing downstream can detect it, because a doubled file is well-formed and
    # its rows are individually correct.
    #
    # Refusing (rather than appending, or silently overwriting) is what makes the deriver
    # safe to call from `:run`'s close stage, which can be entered more than once on a
    # resume.  Re-running is then a no-op that reports itself, which is the property an
    # automated caller needs -- and it exits 0, because the desired state already holds.
    if existing and not args.redo:
        print(f"\n  already derived — {out} has {existing} row(s), left alone.\n"
              f"  Re-derive with --redo (replaces the file). Appending a second copy would\n"
              f"  double every row, token and agent-hour read from it, undetectably.")
        return

    with out.open("w" if args.redo else "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"\n  {'replaced' if existing else 'wrote'} {out}")


TIER_LOSS = ("`tier` is unrecoverable for {n} of them: no hook will ever emit it and it has no "
             "second source (run-jsonl.md:105). `model` and `effort` are NOT lost — the "
             "transcript carries one and the hook record owns the other.")


def launch_note_check(claims, rows, later=lambda: []):
    """Diagnose the launch-note count instead of reporting it as one number (BILL-582).

    `notes != launches` is four different defects with four different remedies, and the single
    count pointed away from the cause on AATK-81: `21 notes; 20 launches` reads as *the
    orchestrator claimed a launch that never happened*, when the truth was the opposite. The
    21st worker RAN and the harness has its transcript; the run was interrupted with it in
    flight, so run.jsonl's last line is the launch note itself, and `window()` -- which ends at
    that line -- excluded a worker that started 14 seconds later. Chasing the message cost a
    full investigation that ended at a cause the message had pointed away from.

    The four cases:

      notes == launches   compliant. Returns nothing, so a healthy run keeps its one-line pass.
      notes == 0          invariant 7 never satisfied; five of nine runs measured 2026-08-12.
      0 < notes < n       partial -- the shortfall, not a total absence.
      notes > launches    interrupted in flight when the harness has the extra launch *after*
                          the window and no `run_closed` was written. Otherwise it really is a
                          claim with no record behind it, which is what the old message assumed
                          in every case.

    Only `tier` is named as lost, and that is the point of the message rather than a detail:
    it is the one field with no second source, and it is the one the tier-comparison programme
    is built on. Saying "the launch tuple is gone" would overstate three recoverable fields to
    make a point about one irreplaceable one.

    Widening `window()` is NOT the fix and is out of scope by ticket: the window is correct for
    healthy runs and is what stops a cross-check from swallowing a neighbouring ticket's
    launches (`attribute()` records that regression). `later()` looks past it for diagnosis
    only -- what it finds is named in the message, never counted into the totals.
    """
    notes = [d for d in claims if (d.get("launch") or {})]
    n_notes, n_rows = len(notes), len(rows)
    if n_notes == n_rows:
        return []

    if n_notes < n_rows:
        no_tier = n_rows - sum(1 for d in notes if (d["launch"] or {}).get("tier"))
        head = (f"no launch notes at all — invariant 7 unsatisfied for the whole run: "
                f"{n_rows} launches, not one of them recorded" if n_notes == 0 else
                f"partial launch notes — {n_notes} of {n_rows} launches carry one, "
                f"{n_rows - n_notes} do not (invariant 7)")
        return [f"{head}.\n            {TIER_LOSS.format(n=no_tier)}"]

    closed = any(d.get("stage") == "run_closed" for d in claims)
    last = max((d["at"] for d in claims if d.get("at")), default="")
    inflight = [] if closed else [r for r in later()
                                  if (r.get("started_at") or "")[:19] > last[:19]]
    if inflight:
        r = inflight[0]
        return [f"interrupted with a worker in flight — the extra note is NOT a "
                f"claimed-but-absent launch.\n            run.jsonl's last line is {last} and "
                f"no run_closed follows it; the harness has {str(r['stage'])!r} running "
                f"{r['started_at'][:19]} -> {str(r['finished_at'])[:19]}, which started "
                f"{human(seconds(last, r['started_at']))} after that line and so falls outside "
                f"the run's own window.\n            {n_notes} notes / {n_rows} in-window "
                f"launches / {len(inflight)} after the last line. The launch ran; the window is "
                f"right; the run was cut short."]

    return [f"{n_notes - n_rows} launch note(s) with no harness launch behind them: "
            f"{n_notes} notes, {n_rows} launches.\n            "
            + ("run.jsonl closed normally" if closed else
               "run.jsonl has no run_closed, but the harness recorded nothing after its last "
               "line either") +
            ", so this is a claim with no record behind it — not an interruption."]


def crosscheck(rows, track, later=lambda: []):
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
    problems += launch_note_check(claims, rows, later)
    print("\n  --- cross-check: harness vs orchestrator ---")
    for p in problems:
        print(f"  MISMATCH  {p}")
    if not problems:
        print("  the two records agree")

    # Gap accounting is reported as its OWN section and never folded into `problems`: the
    # cross-check above answers "do the two records agree", this answers "is the clock
    # accounted for". They fail independently and a run can pass one while failing the other.
    # Its own section, like gap accounting: "is the size label usable" fails independently
    # of "do the two records agree" and of "is the clock accounted for".
    size_problems = size_check(claims)
    print("\n  --- size note: is the tier readable, and is it the right one? ---")
    for p in size_problems:
        print(f"  SIZE  {p}")
    if not size_problems:
        print("  well-formed — tier is an enum, matches its own numbers, and suits the mode")

    itemised, residue, residue_n, bracketed = gaps(claims)
    n_waits = sum(1 for d in claims if d.get("stage") == "waiting_for_user"
                  and d.get("event") == "span" and d.get("state") == "started")
    print("\n  --- gap accounting: time no span accounts for ---")
    for d, a, b, stage in itemised:
        print(f"  UNBRACKETED  {human(d):>9}  {a} -> {b}  after '{stage}'")
    if residue_n:
        print(f"  residue: {residue_n} slice(s) at or under {GAP_THRESHOLD_S}s, "
              f"{human(residue)} total")
    if bracketed:
        print(f"  bracketed as waiting_for_user: {human(bracketed)} across {n_waits} wait(s) "
              f"— measured, not a gap")
    unbracketed = sum(d for d, *_ in itemised) + residue
    if not itemised and not residue_n:
        print("  none — every interval is inside a span")
    else:
        print(f"  total unbracketed: {human(unbracketed)}")
    if itemised and n_waits == 0:
        print(f"  UNMEASURED  {human(sum(d for d, *_ in itemised))} itemised over "
              f"{GAP_THRESHOLD_S}s with zero waiting_for_user spans. This is not "
              f"measured-zero (run-jsonl.md:763) — the time is unaccounted, not absent.")


if __name__ == "__main__":
    main()
