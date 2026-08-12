#!/usr/bin/env python3
"""Pin the six states behind an unclosed span's reported end (BILL-586).

`harness says it ended unknown` was one word for three situations, and it contradicted the
launch diagnosis printed two lines below it on the very same run. Four of the six states below
have NO live case anywhere in the nine archived runs -- only SOP-262 (`pr`, launches nothing)
and PLTF-2563 (`implement`, in-window) occur at all -- so a sweep over real runs defends two
of six. BILL-582 was reviewed three times on exactly that mistake; this is the shape
that closed it.

    python3 tools/metrics/fixtures/interrupted-in-flight/check-unclosed-spans.py

Exits non-zero on any case whose verdict changed. Writes only to a temp dir. Every mutation is
asserted on both sides, so fixture drift aborts rather than silently running another case.
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
RUN_JSONL_MD = FIXTURE.parents[3] / "skills" / "run" / "references" / "run-jsonl.md"
CLOSED_AT = "2026-08-12T11:30:00Z"      # past the archive worker, so all three are in-window
LABELS = ("Investigate AATK-81", "Review round 1 AATK-81", "Archive AATK-81 record")


def drift(what):
    sys.exit(f"FIXTURE DRIFT: {what}\n"
             f"This script would have run a DIFFERENT case and reported it as this one. Fix it\n"
             f"against the current fixture rather than trusting the output.")


def load(path):
    return [json.loads(line) for line in path.open() if line.strip()]


def check_no_launch_list():
    """`NO_LAUNCH_STAGES` is a MIRROR of run-jsonl.md's invariant-7 scope. Assert they agree.

    Nothing in derive.py parses the doc, so the two can drift — and a stage added there and not
    there falls through to the label match and gets reported as "not found", which is the exact
    conflation BILL-586 removed. This assertion is the only thing standing between the mirror
    and that regression, which is why it lives in the checked-in check rather than in a comment
    promising the drift cannot happen. (It previously was such a comment, and it was false.)
    """
    if not RUN_JSONL_MD.exists():
        drift(f"{RUN_JSONL_MD} is gone — the no-launch list has nothing to be checked against")
    m = re.search(r"\*\*Scope it to `W` stages\.\*\*(.+?)launch nothing",
                  RUN_JSONL_MD.read_text(), re.S)
    if not m:
        drift("run-jsonl.md no longer has a \"Scope it to `W` stages … launch nothing\" sentence "
              "— NO_LAUNCH_STAGES has no source to be checked against")
    documented = frozenset(re.findall(r"`([a-z0-9-]+)`", m.group(1)))
    sys.path.insert(0, str(DERIVE.parent))
    import derive
    if documented != derive.NO_LAUNCH_STAGES:
        sys.exit(
            f"NO_LAUNCH_STAGES has drifted from run-jsonl.md's invariant-7 scope.\n"
            f"  only in run-jsonl.md: {sorted(documented - derive.NO_LAUNCH_STAGES) or '—'}\n"
            f"  only in derive.py:    {sorted(derive.NO_LAUNCH_STAGES - documented) or '—'}\n"
            f"A stage documented to launch nothing but missing from the set is reported as "
            f"'not found', which is the conflation BILL-586 removed.")
    print(f"  PASS  no-launch list matches run-jsonl.md ({len(documented)} stages)")


def check_transcripts():
    session = next(iter(sorted((FIXTURE / "transcripts").glob("*.jsonl"))), None)
    if session is None:
        drift("no session transcript in transcripts/")
    seen = {(c.get("input") or {}).get("description")
            for d in load(session) for c in (d.get("message") or {}).get("content") or []}
    for label in LABELS:
        if label not in seen:
            drift(f"no launch labelled {label!r} — the substring cases are pinned to these")


def open_span(tmp, name, stage, at):
    """The closed fixture run.jsonl, plus one span that opens at `at` and never closes."""
    ds = load(FIXTURE / "tracking-phantom" / "run.jsonl")
    if not (ds and ds[-1].get("stage") == "run_closed"):
        drift("tracking-phantom/run.jsonl no longer ends in a run_closed note")
    ds[-1]["at"] = CLOSED_AT
    ds.insert(len(ds) - 1, {"ticket": "AATK-81", "event": "span", "stage": stage,
                            "state": "started", "at": at})
    (tmp / name).mkdir(parents=True)
    (tmp / name / "run.jsonl").write_text("\n".join(json.dumps(d) for d in ds) + "\n")
    return tmp / name


def run(track, transcripts):
    out = subprocess.run(
        [sys.executable, str(DERIVE), "AATK-81", "--tracking", str(track),
         "--transcripts", str(transcripts), "--check"],
        capture_output=True, text=True).stdout
    return "\n".join(ln for ln in out.splitlines() if "UNCLOSED" in ln)


def main():
    check_no_launch_list()
    check_transcripts()
    tmp = pathlib.Path(tempfile.mkdtemp())
    transcripts = FIXTURE / "transcripts"
    try:
        # EXPECTED VALUES ARE DERIVED, NOT CAPTURED. An earlier version of this file pinned
        # `ended 07:45:08.608Z` for a span opened at 11:25:00Z -- an end three hours and forty
        # minutes BEFORE its own open -- because the string was copied from a run of the code
        # rather than argued from the fixture's own timings. It did not miss that defect; it
        # asserted the defect was correct, and went green. Every expectation below is stated
        # with the reason it must hold. (Found by a clean-context review of PR #587.)
        #
        # The fixture's three workers, from their transcripts:
        #   Investigate  00:35:31 -> 00:38:21.809     Review  07:41:29 -> 07:45:08.608
        #   Archive      11:20:44 -> 11:24:35.385
        cases = [
            # stage, span opens at, what it is, the claim that must survive
            ("pr", "2026-08-12T11:25:00Z", "stage launches nothing — never reaches a label",
             "this stage launches no worker"),
            ("review", "2026-08-12T07:40:00Z", "worker ran, in window, span opened before it",
             "harness says it ended 2026-08-12T07:45:08.608Z"),
            # The span opens 3h40m AFTER the review worker finished, so that worker cannot be
            # the one this span opened. Nothing may be reported as its end.
            ("review", "2026-08-12T11:25:00Z", "every match predates the span",
             "started BEFORE this span opened"),
            ("salvage", "2026-08-12T11:25:00Z", "no label contains it — 'not found'",
             "not found"),
            # Opened before all three, so all three survive the time filter and the earliest is
            # Investigate. One span per round makes several matches NORMAL: refusing here was a
            # regression against the code this replaced (AATK-81: adversary 6, handoff 5,
            # review 3). `aatk` is synthetic; the multi-match rule it pins is not.
            ("aatk", "2026-08-12T00:30:00Z", "3 match — reports the earliest, names the rest",
             "the first of 3 launches matching 'aatk'"),
        ]
        failures = 0
        for i, (stage, at, what, expected) in enumerate(cases):
            got = run(open_span(tmp, f"case-{i}-{stage}", stage, at), transcripts)
            ok = expected in got
            failures += not ok
            print(f"  {'PASS' if ok else 'FAIL'}  {stage:9s} {what}")
            if not ok:
                print(f"        expected to find: {expected}\n        got: {got or '(no UNCLOSED line)'}")

        # The interrupted case is the committed variant itself, not a constructed one: its whole
        # point is that run.jsonl ENDS at the launch note, which is what puts the worker outside
        # the window. It must also stop contradicting the launch diagnosis below it.
        got = run(FIXTURE / "tracking", transcripts)
        ok = ("2026-08-12T11:24:35.385Z" in got and "OUTSIDE the run's own window" in got)
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  archive   worker ran, outside the window "
              f"(interrupted)")
        if not ok:
            print(f"        expected its real end time and the outside-window note\n"
                  f"        got: {got or '(no UNCLOSED line)'}")

        if failures:
            sys.exit(f"\n{failures} of {len(cases) + 1} unclosed-span case(s) changed verdict.")
        print(f"\n  all {len(cases) + 1} unclosed-span cases hold")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
