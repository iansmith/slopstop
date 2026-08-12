#!/bin/sh
# The undecidable case: attribution drops the run's first launch because its label carries no
# ticket key, so `rows` is one short through no fault of the orchestrator. Before BILL-582's
# review this printed "a claim with no record behind it" about a worker whose transcript is
# right there — the same false accusation the interrupted case exists to prevent.
#
# Built here rather than committed as a fourth variant: the trigger lives in the SESSION
# transcript, not in run.jsonl, so a committed variant would have to duplicate every subagent
# file to change one label string.
#
# EVERY SUBSTITUTION IS ASSERTED, because `sed` exits 0 when its pattern matches nothing. With
# the second one silently skipped this script still exits 0 and prints "a claim with no record
# behind it — not an interruption" — the exact verdict it exists to prove absent, reported as a
# pass. A check that reports the wrong thing because its command matched nothing is the failure
# mode CLAUDE.md names; fixture drift must stop the script, not redirect it.
set -eu
F=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

drift() {
    printf 'FIXTURE DRIFT: %s\n' "$1" >&2
    printf 'This script would have run a DIFFERENT case and reported it as this one. Fix the\n' >&2
    printf 'pattern below against the current fixture rather than trusting the output.\n' >&2
    exit 1
}

cp -R "$F/transcripts" "$T/transcripts"
cp -R "$F/tracking-phantom" "$T/tracking"

# 1. strip the ticket key from the first launch's label, so attribute() drops that launch
grep -q '"Investigate AATK-81"' "$T"/transcripts/*.jsonl \
    || drift 'no launch labelled "Investigate AATK-81" in the session transcript'
sed -i.bak 's/"Investigate AATK-81"/"Investigate the failing gate"/' "$T"/transcripts/*.jsonl
grep -q '"Investigate the failing gate"' "$T"/transcripts/*.jsonl \
    || drift 'the first-launch label was not rewritten'

# 2. close the run AFTER the archive worker, so the window covers all three launches and the
#    dropped one is the ONLY discrepancy left
grep -q '"stage": "run_closed", "at": "2026-08-12T11:20:30Z"' "$T/tracking/run.jsonl" \
    || drift 'tracking-phantom/run.jsonl no longer ends in a run_closed at 11:20:30Z'
sed -i.bak 's/"stage": "run_closed", "at": "2026-08-12T11:20:30Z"/"stage": "run_closed", "at": "2026-08-12T11:30:00Z"/' \
    "$T/tracking/run.jsonl"
grep -q '"at": "2026-08-12T11:30:00Z"' "$T/tracking/run.jsonl" \
    || drift 'the run_closed timestamp was not moved past the archive worker'

python3 "$F/../../derive.py" AATK-81 --tracking "$T/tracking" --transcripts "$T/transcripts" --check
