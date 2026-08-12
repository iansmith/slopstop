#!/bin/sh
# The undecidable case: attribution drops the run's first launch because its label carries no
# ticket key, so `rows` is one short through no fault of the orchestrator. Before BILL-582's
# review this printed "a claim with no record behind it" about a worker whose transcript is
# right there — the same false accusation the interrupted case exists to prevent.
#
# Built here rather than committed as a fourth variant: the trigger lives in the SESSION
# transcript, not in run.jsonl, so a committed variant would have to duplicate every subagent
# file to change one label string.
set -eu
F=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
cp -R "$F/transcripts" "$T/transcripts"
cp -R "$F/tracking-phantom" "$T/tracking"
# strip the ticket key from the first launch's label, and close the run AFTER the archive
# worker so the window covers all three launches -- leaving the dropped launch as the only
# discrepancy
sed -i.bak 's/"Investigate AATK-81"/"Investigate the failing gate"/' "$T"/transcripts/*.jsonl
sed -i.bak 's/"stage": "run_closed", "at": "2026-08-12T11:20:30Z"/"stage": "run_closed", "at": "2026-08-12T11:30:00Z"/' "$T/tracking/run.jsonl"
python3 "$F/../../derive.py" AATK-81 --tracking "$T/tracking" --transcripts "$T/transcripts" --check
