"""
Phase 0 red tests for BILL-387 — Fleet marker-derived phase timing.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/387). Transcription, not
authorship: every assertion and every expected value below is pinned by the
ticket, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Oracle for the expected values (per the ticket):
`gh api repos/iansmith/slopstop/issues/355/comments --paginate`, read
2026-08-02 — 13 comments, first `2026-07-31T16:34:26Z` (the fleet briefing
marker comment), last `2026-07-31T17:23:20Z`. Vendored at
tests/fixtures/bill355_comments.json (BILL-355, fleet ticket) and
tests/fixtures/bill282_comments.json (BILL-282, interactive ticket, zero
comments).

Test command:
    python3 -m pytest tests/test_bill387_behaviors.py -v
"""

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "metrics"))

import markers  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _load_fixture(name):
    with (FIXTURES / name).open() as f:
        return json.load(f)


def _ctx_for(comments):
    return {"gh_api": lambda path: comments}


def test_bill355_fleet_markers_derived_from_comments():
    comments = _load_fixture("bill355_comments.json")
    record = {"ticket": "BILL-355", "repo": "iansmith/slopstop", "timing": None}
    markers.collect(record, _ctx_for(comments))

    phases = record["phases"]
    assert phases["fleet"] is True
    assert len(phases["markers"]) == 13
    assert phases["markers"][0]["at"] == "2026-07-31T16:34:26Z"
    assert phases["markers"][-1]["at"] == "2026-07-31T17:23:20Z"


def test_bill282_interactive_ticket_zero_comments():
    comments = _load_fixture("bill282_comments.json")
    record = {"ticket": "BILL-282", "repo": "iansmith/slopstop", "timing": None}
    markers.collect(record, _ctx_for(comments))

    phases = record["phases"]
    assert phases["fleet"] is False
    assert phases["markers"] == []


def test_briefed_at_emitted_unchanged_even_though_it_precedes_started_at():
    comments = _load_fixture("bill355_comments.json")
    record = {
        "ticket": "BILL-355",
        "repo": "iansmith/slopstop",
        # On BILL-355 the real timing.started_at is 60s after briefed_at
        # (2026-07-31T16:35:26Z vs 2026-07-31T16:34:26Z). The collector must
        # not clamp or reorder briefed_at to match — it records both as-is.
        "timing": {"started_at": "2026-07-31T16:35:26Z"},
    }
    markers.collect(record, _ctx_for(comments))

    phases = record["phases"]
    assert phases["briefed_at"] == "2026-07-31T16:34:26Z"
    assert phases["briefed_at"] < record["timing"]["started_at"]
