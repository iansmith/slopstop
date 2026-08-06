"""
Phase 0 red tests for BILL-406 — skill and tool spans in collect.py.

Transcribed from the ticket's observable behaviors and DoD
(https://github.com/iansmith/slopstop/issues/406).

The measurement that motivates it, from the ticket, on BILL-382 (span 2263 s):
Phase 0 -> implementation complete was 76 s (3%); review complete -> merged was
1549 s (68%) and entirely unattributed. Until that block has internal structure
there is nothing to optimise against.

**How a skill span is bounded, and why it is not the tool_result.** Probed
2026-08-05: a `Skill` tool_use's matching tool_result arrives in 0.02-4.43 s —
that is the skill text loading, not the skill running. The same trap as an
`Agent` spawn's 2.7 s launch latency. A skill's real span therefore runs from
its tool_use to the *next* skill's tool_use, and the last one to the ticket's
`completed_at`. That also makes the spans contiguous, which is what lets
behavior 3's sum-plus-remainder identity hold at all.

Test command:
    python3 -m pytest tests/test_bill406_behaviors.py -v
"""

import json
import subprocess
import sys

from conftest import REPO_ROOT

COLLECT = REPO_ROOT / "tools" / "metrics" / "collect.py"

# The ticket's DoD names BILL-382 and its 9 Skill invocations.
TICKET = "BILL-382"
MIN_SKILL_SPANS = 9

# Gate-identifying commands the ticket requires attributed (behavior 2).
REQUIRED_TOOL_KINDS = {"pytest", "lizard", "git-diff"}


def run_collect(ticket):
    r = subprocess.run(
        [sys.executable, str(COLLECT), ticket],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_spans_block_has_one_entry_per_skill_invocation():
    """Behavior 1 — name, started_at, ended_at, duration_seconds per Skill call."""
    record = run_collect(TICKET)
    spans = record["spans"]
    assert spans is not None, "spans is still null — nothing was derived"
    skills = spans["skills"]
    assert len(skills) >= MIN_SKILL_SPANS, (
        f"expected at least {MIN_SKILL_SPANS} skill spans for {TICKET}, got {len(skills)}"
    )
    for s in skills:
        assert set(s) >= {"name", "started_at", "ended_at", "duration_seconds"}, (
            f"span missing required fields: {sorted(s)}"
        )
        assert isinstance(s["duration_seconds"], (int, float))
        assert s["duration_seconds"] >= 0, f"negative duration: {s}"
        assert s["name"], "span has no skill name"


def test_gate_tool_calls_are_attributed_inside_their_span():
    """Behavior 2 — pytest, lizard and the git diff family, each with its own duration.

    These are the gates. Without them a skill span is one opaque block again, just a
    smaller one.
    """
    record = run_collect(TICKET)
    spans = record["spans"]
    assert spans is not None
    kinds = {t["kind"] for s in spans["skills"] for t in s.get("tools", [])}
    missing = REQUIRED_TOOL_KINDS - kinds
    assert not missing, f"no {sorted(missing)} calls attributed; saw {sorted(kinds)}"
    for s in spans["skills"]:
        for t in s.get("tools", []):
            assert {"kind", "started_at", "duration_seconds"} <= set(t), sorted(t)
            assert t["duration_seconds"] >= 0


def test_spans_plus_remainder_account_for_the_whole_ticket():
    """Behavior 3 — no time is silently lost.

    The identity is the point: an unattributed remainder that is *reported* is data
    ("68% is in a block we cannot name yet"); one that is silently dropped makes the
    attributed slice look like the whole ticket.
    """
    record = run_collect(TICKET)
    spans, timing = record["spans"], record["timing"]
    assert spans is not None
    total = sum(s["duration_seconds"] for s in spans["skills"])
    remainder = spans["unattributed_seconds"]
    assert remainder >= 0, f"negative remainder: {remainder}"
    assert abs(total + remainder - timing["span_seconds"]) <= 1, (
        f"spans {total} + remainder {remainder} != span_seconds "
        f"{timing['span_seconds']}"
    )
def test_ticket_with_no_recognisable_spans_returns_null_not_an_error():
    """Behavior 4 — degrade gracefully, the same posture as the rest of the collector.

    BILL-140 has never been closed, so `timing.completed_at` is null and the window
    degenerates to a single instant. Its one `slopstop-archive` invocation lands exactly
    on that boundary and produced a **0-second span** before this was guarded — worse
    than silence, because a zero duration reads as a measurement rather than an absence.

    The exemplar changed during implementation: this test was written expecting BILL-140
    to have no transcript at all, which was wrong. It was deliberately held out of the
    Phase 0 commit (vacuously green against the stub), so correcting it here is a fixture
    fix, not an edit to a frozen expectation.
    """
    record = run_collect("BILL-140")
    assert record["spans"] is None, (
        f"expected null spans for a ticket with no transcript, got {record['spans']!r}"
    )


def test_each_duration_matches_its_own_timestamps():
    """Added by the Step 0f adversary pass. Closes a hole the sum identity hides.

    Mutation that passed the frozen suite: report every span with
    `duration_seconds: 0`. Behavior 1 only asserts `>= 0`, and behavior 3 still holds
    because the remainder is `max(0, span_seconds - attributed)` — so it silently
    absorbs the entire error and the identity balances against nothing.

    Deriving the duration from the span's own reported timestamps is the independent
    check the identity cannot provide.
    """
    from datetime import datetime

    def parse(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    record = run_collect(TICKET)
    spans = record["spans"]
    assert spans is not None
    total = 0.0
    for s in spans["skills"]:
        expected = (parse(s["ended_at"]) - parse(s["started_at"])).total_seconds()
        assert abs(s["duration_seconds"] - expected) < 0.01, (
            f"{s['name']}: duration_seconds {s['duration_seconds']} disagrees with its "
            f"own timestamps ({expected})"
        )
        total += expected
    assert total > 0, "every span reports zero elapsed time"
    assert abs(spans["attributed_seconds"] - total) < 0.05, (
        f"attributed_seconds {spans['attributed_seconds']} != sum of spans {total}"
    )


def test_each_tool_call_falls_inside_the_span_it_is_attributed_to():
    """Added by the Step 0f adversary pass. Closes the second hole.

    Mutation that passed the frozen suite: attribute every tool call to the first span
    regardless of timestamp. Behavior 2 only checks that each required kind appears
    *somewhere*, so a completely wrong assignment reads as success — and "which gate ran
    inside which skill" is the entire product here.
    """
    from datetime import datetime

    def parse(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    record = run_collect(TICKET)
    spans = record["spans"]
    assert spans is not None
    seen = 0
    for s in spans["skills"]:
        start, end = parse(s["started_at"]), parse(s["ended_at"])
        for t in s.get("tools", []):
            at = parse(t["started_at"])
            assert start <= at <= end, (
                f"{t['kind']} at {t['started_at']} is attributed to {s['name']} "
                f"({s['started_at']} .. {s['ended_at']}), which does not contain it"
            )
            seen += 1
    assert seen > 0, "no tool calls attributed at all"


def test_gate_needles_only_match_at_a_command_position():
    """Added after review round 5, which found substring matching fabricating gates.

    Measured across 16 real tickets before the fix: 40 of 460 attributed gate calls
    (8.7%) were not gate runs at all — a 40.6 s `pytest` for a Python regex containing
    the literal `@pytest`, a 4.8 s `git-diff` for a DoD checklist line mentioning
    `git diff`, and seven `lizard` gates in BILL-387 that were `pip install lizard` and
    `command -v lizard`. Each carried the whole compound command's wall time, so the
    number read as a measurement.

    The review flagged that its own fix shipped without a test, since the only spans
    test file is this frozen one. Adding a test is permitted — the freeze forbids
    changing an expected value, loosening an assertion, or deleting one.
    """
    sys.path.insert(0, str(REPO_ROOT / "tools" / "metrics"))
    import spans

    # Real strings from the transcripts that were misclassified before the fix.
    for command in (
        'python3 -c \'re.split(r"\\n(?=def test_|@pytest)", src)\'',
        'echo "- [ ] `git diff` touches no repo other than this one" >> dod.md',
        "pip install lizard",
        "command -v lizard",
        'python3 -c "import lizard"',
    ):
        assert spans._classify(command) is None, (
            f"{command!r} is not a gate run, but was classified as "
            f"{spans._classify(command)!r}"
        )

    # Genuine invocations, including the shapes non-Python repos use.
    for command, kind in (
        ("python3 -m pytest tests/ -q", "pytest"),
        ("pytest tests/test_x.py -v", "pytest"),
        ("poetry run pytest", "pytest"),
        ("lizard --csv tools/", "lizard"),
        ("/opt/homebrew/bin/lizard --csv x.py", "lizard"),
        ("git diff --stat origin/master...HEAD", "git-diff"),
        ("cd /tmp && git diff HEAD", "git-diff"),
    ):
        assert spans._classify(command) == kind, (
            f"{command!r} should classify as {kind!r}, got {spans._classify(command)!r}"
        )
