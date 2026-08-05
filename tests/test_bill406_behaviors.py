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
