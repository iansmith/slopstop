#!/usr/bin/env python3
"""Pin that one session holding two orchestrations derives one row per RUN, not per LAUNCH.

    python3 tools/metrics/fixtures/two-orchestrations/check-doubling.py

Exits non-zero on any assertion. Copies the fixture to a temp dir and writes only there.

WHAT IT CATCHES (BILL-599). `window()` scopes the *runs* to the orchestration being derived;
nothing scoped the *launches*, so every launch from an earlier orchestration in the same
session survived into the matching loop with no run left to match, and claimed a later run
through an unbounded `started_at >= requested_at` fallback. The true owner then re-claimed the
same run by exact `agent_id`, because that path never consulted `used`. Six rows for three
runs, every total 2x, and the stolen rows carrying the wrong stage label and the wrong model.

WHY EACH ASSERTION IS HERE, because the obvious one is not sufficient:

  row count       the visible symptom
  unique ids      the invariant. A doubled file is well-formed and its rows are individually
                  correct, so nothing else distinguishes it -- and it also catches the
                  append-doubling case derive.py's idempotence guard calls undetectable.
  exact labels    fixing only the `used` check yields the RIGHT COUNT with every row
                  mislabeled: attempt-1 labels land on attempt-2 runs. Count alone passes.
  model fidelity  the opus delta-check launch stole a sonnet run and was recorded as sonnet.
                  A model column that lies is worse than one that is missing.
  drop reported   a launch that matches nothing is a fact about the record. Silent `continue`
                  is how the four defects hid from every run that ever exercised them.
"""

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

FIXTURE = pathlib.Path(__file__).resolve().parent
DERIVE = FIXTURE.parent.parent / "derive.py"
TICKET = "AATK-99"

# The three runs inside the window, with the launch that actually owns each. Ownership is not
# a judgement call: each requested_at sits ~1.5-2s before its run's started_at, where every
# competing attempt-1 launch precedes it by more than an hour.
EXPECTED = {
    "a4444444444444444": ("investigate AATK-99 V2", "claude-sonnet-5"),
    "a5555555555555555": ("red-tests AATK-99 V2 new DoD items", "claude-sonnet-5"),
    "a6666666666666666": ("implement AATK-99", "claude-sonnet-5"),
    # SAME-SECOND SYNC LAUNCH. `seconds()` truncates to whole seconds, so this launch and its
    # run have a delta of 0.0. A `(seconds(...) or -1)` bound rejects that -- the falsy-zero
    # trap -- and so drops the ordinary case for the one path the fallback exists to serve.
    "a7777777777777777": ("mutation-check AATK-99", "claude-sonnet-5"),
}
# TWO KINDS OF NON-ROW, and conflating them is a bug in either direction.
#
# OUT OF WINDOW -- these launches belong to the earlier orchestrations in this same session.
# They are scoped out at the source, which is the fix for the root defect. They must produce
# no row, and they must NOT be announced: a session driving a dozen tickets would otherwise
# print a wall of "unmatched" for launches that were never in scope, and a report that cries
# wolf is one nobody reads when it is real.
OUT_OF_WINDOW_LABELS = {
    "investigate AATK-99",
    "red-tests AATK-99",
    "scope-subtraction delta check AATK-99 V2",
}
# IN WINDOW, MATCHED NOTHING -- a sync launch (no agentId) with no child at or after it. This
# one IS in scope, so its absence is a fact about the record: either the run is gone or the
# pairing is wrong. It must be reported, never silently skipped.
# ORPHANED ASYNC LAUNCH -- carries an agent_id whose transcript does not exist (they get
# deleted for size). It must land here, never in the time fallback: a launch that already
# named its run must not be allowed to guess at a different one. It sits 10s before a7777's
# run, so a fallback that accepted it would steal that run and strand its true owner.
UNMATCHED_LABELS = {"close AATK-99", "review AATK-99"}

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


with tempfile.TemporaryDirectory() as tmp:
    work = pathlib.Path(tmp) / "two-orchestrations"
    shutil.copytree(FIXTURE, work)
    out = work / "tracking" / "run-derived.jsonl"
    out.unlink(missing_ok=True)

    proc = subprocess.run(
        [sys.executable, str(DERIVE), TICKET,
         "--tracking", str(work / "tracking"),
         "--transcripts", str(work / "transcripts")],
        capture_output=True, text=True)
    stdout = proc.stdout + proc.stderr

    if not out.exists():
        print(stdout)
        sys.exit(f"FAIL: {out} was never written (deriver exited {proc.returncode})")

    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]

    # Parse the unmatched-launch report into exact labels. A substring test cannot be used
    # here: every attempt-1 label is a PREFIX of its attempt-2 counterpart ("investigate
    # AATK-99" inside "investigate AATK-99 V2"), so `in stdout` reports the earlier launch as
    # announced whenever the later one is merely listed in the table.
    reported = {m.group(1).strip() for m in
                (re.match(r"\s+\d{4}-\d\d-\d\dT[\d:.]+Z\s\s+(.+)$", l)
                 for l in stdout.splitlines()) if m}

    ids = [r["agent_id"] for r in rows]
    check(len(ids) == len(set(ids)),
          f"agent_id is not unique across rows: {len(ids)} rows, {len(set(ids))} distinct. "
          f"One row per subagent run is the invariant; duplicates mean every token and "
          f"agent-hour total read from this file is inflated.")
    check(len(rows) == len(EXPECTED),
          f"expected {len(EXPECTED)} rows (one per run inside the window), got {len(rows)}")

    for r in rows:
        aid = r["agent_id"]
        if aid not in EXPECTED:
            check(False, f"row for {aid} is outside the window and should not exist")
            continue
        label, model = EXPECTED[aid]
        check(r["stage"] == label,
              f"{aid}: stage is {r['stage']!r}, expected {label!r} — a launch from the "
              f"earlier orchestration claimed this run")
        check(r["model_observed"] == model,
              f"{aid}: model_observed is {r['model_observed']!r}, expected {model!r}")

    staged = {r["stage"] for r in rows}
    for label in UNMATCHED_LABELS:
        check(label not in staged,
              f"{label!r} has no run inside the window but produced a row")
        check(label in reported,
              f"{label!r} matched nothing and was dropped without being reported — "
              f"an unattributable launch is a fact about the record, not noise")
    for label in OUT_OF_WINDOW_LABELS:
        check(label not in staged,
              f"{label!r} is from an earlier orchestration and produced a row — its launch "
              f"reached the matching loop and claimed a run belonging to this one")
        check(label not in reported,
              f"{label!r} is out of window and was announced as unmatched — out-of-scope and "
              f"unattributable are different facts, and reporting the first as the second "
              f"buries the one that matters")

if fails:
    print(f"\n  {len(fails)} FAILURE(S)\n")
    for f in fails:
        print(f"  ✗ {f}")
    sys.exit(1)
print(f"  PASS — {len(EXPECTED)} rows, one per run, correctly labelled; "
      f"{len(UNMATCHED_LABELS)} unmatched launches reported")
