#!/usr/bin/env python3
"""Pin what `dropped` does to all three branches of `launch_note_check` (BILL-582 review).

`dropped` is `attribute()`'s count of launches the harness recorded that could not be placed
on any ticket, because they precede the first label carrying a ticket key. It makes this
ticket's launch count a RANGE, and three review rounds in a row found a branch that ignored
it -- each time producing a confident claim the data did not support, and the third time
producing a silent PASS. None of the nine real runs reaches these branches (every one of them
has `dropped == 0` where it matters), so an assertion here is the only thing that stops the
next change regressing them unnoticed.

    python3 tools/metrics/fixtures/interrupted-in-flight/check-dropped-cases.py

Exits non-zero on any case whose verdict changed. Writes only to a temp dir.

WHY BUILT, NOT COMMITTED. The trigger lives in the SESSION transcript -- one launch label --
so committing these as fixture variants would duplicate every subagent file three times to
change one string. Everything mutated here is asserted on both sides: a silently-skipped
mutation would run a DIFFERENT case and report it as this one, which is the failure this
script's predecessor actually had.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

FIXTURE = pathlib.Path(__file__).resolve().parent
DERIVE = FIXTURE.parent.parent / "derive.py"
LABEL = "Investigate AATK-81"
UNLABELLED = "Investigate the failing gate"
CLOSED_AT = "2026-08-12T11:30:00Z"          # after the archive worker, so the window covers all 3


def drift(what):
    sys.exit(f"FIXTURE DRIFT: {what}\n"
             f"This script would have run a DIFFERENT case and reported it as this one. Fix it\n"
             f"against the current fixture rather than trusting the output.")


def load(path):
    return [json.loads(line) for line in path.open() if line.strip()]


def build_transcripts(tmp):
    """Copy the fixture transcripts, stripping the ticket key from the FIRST launch's label.

    That is the whole trigger: `attribute()` drops every launch before the first labelled one,
    so this run has 3 launches, 2 attributable and 1 dropped.
    """
    dst = tmp / "transcripts"
    shutil.copytree(FIXTURE / "transcripts", dst)
    session = next(iter(sorted(dst.glob("*.jsonl"))), None)
    if session is None:
        drift("no session transcript in transcripts/")
    lines, hits = [], 0
    for d in load(session):
        for c in (d.get("message") or {}).get("content") or []:
            if (c.get("input") or {}).get("description") == LABEL:
                c["input"]["description"] = UNLABELLED
                hits += 1
        lines.append(json.dumps(d))
    if hits != 1:
        drift(f"expected exactly one launch labelled {LABEL!r}, found {hits}")
    session.write_text("\n".join(lines) + "\n")
    return dst


def build_run_jsonl(path, keep_notes):
    """The committed phantom variant, closed after the archive worker, keeping `keep_notes`.

    Varying only the number of surviving launch notes walks the three branches: fewer notes
    than attributed launches, equal, and more.
    """
    ds = load(FIXTURE / "tracking-phantom" / "run.jsonl")
    if not (ds and ds[-1].get("stage") == "run_closed"):
        drift("tracking-phantom/run.jsonl no longer ends in a run_closed note")
    ds[-1]["at"] = CLOSED_AT
    notes = [d for d in ds if d.get("launch")]
    if len(notes) != 3:
        drift(f"expected 3 launch notes in tracking-phantom/run.jsonl, found {len(notes)}")
    drop = {id(d) for d in notes[:len(notes) - keep_notes]}
    path.mkdir(parents=True)
    (path / "run.jsonl").write_text(
        "\n".join(json.dumps(d) for d in ds if id(d) not in drop) + "\n")


CASES = [
    # keep_notes, branch, the claim that must survive
    (1, "shortfall + dropped", "`tier` is unrecoverable for 1–2 of them"),
    (2, "equal counts + dropped", "undecidable — 2 notes match the 2 attributed launches"),
    (3, "excess covered by dropped", "undecidable — 3 notes against 2 attributed launches"),
]


def main():
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        transcripts = build_transcripts(tmp)
        failures = 0
        for keep, branch, expected in CASES:
            track = tmp / f"case-{keep}"
            build_run_jsonl(track, keep)
            out = subprocess.run(
                [sys.executable, str(DERIVE), "AATK-81", "--tracking", str(track),
                 "--transcripts", str(transcripts), "--check"],
                capture_output=True, text=True).stdout
            if "unattributable, dropped" not in out:
                drift(f"{branch}: attribute() did not drop the unlabelled launch")
            ok = expected in out
            failures += not ok
            print(f"  {'PASS' if ok else 'FAIL'}  {branch}")
            if not ok:
                print(f"        expected to find: {expected}")
                print("        got:\n" + "\n".join(
                    f"        | {ln}" for ln in out.splitlines()
                    if "MISMATCH" in ln or "records agree" in ln or ln.startswith("     ")))
        if failures:
            sys.exit(f"\n{failures} of {len(CASES)} dropped-launch case(s) changed verdict.")
        print(f"\n  all {len(CASES)} dropped-launch cases hold")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
