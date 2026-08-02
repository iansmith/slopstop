"""
Phase 0 red tests for BILL-385 — GitHub-derived timing: coarse span and PR
sub-phases.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/385). Transcription, not
authorship: every assertion and every expected value below is pinned by the
ticket, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Fixtures are vendored `gh api` responses (issue object, events, timeline,
and cross-referenced PR objects) for issues 282 and 355, read 2026-08-02.
They are the oracle for the exact values below — not re-derived from the
implementation.

Test command:
    python3 -m pytest tests/test_bill385_behaviors.py -v
"""

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "metrics"

sys.path.insert(0, str(REPO_ROOT / "tools" / "metrics"))

import conventions  # noqa: E402
import github_source  # noqa: E402

REPO = "iansmith/slopstop"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


class FakeGhApi:
    """Routes `gh api <path>` calls to vendored fixture JSON by exact path."""

    def __init__(self, routes):
        self._routes = routes

    def __call__(self, path):
        if path not in self._routes:
            raise AssertionError(f"unexpected gh_api path: {path}")
        return self._routes[path]


CONV = conventions.Conventions(
    system="github",
    repo=REPO,
    prefix="BILL",
    status_labels={"in_progress": "status:in-progress"},
)


def _make_record(ticket):
    return {
        "schema": "slopstop.derived-metrics/1",
        "ticket": ticket,
        "system": "github",
        "repo": REPO,
        "generated_at": "2026-08-02T00:00:00Z",
        "timing": None,
        "tokens": None,
        "phases": None,
        "signals": None,
    }


def _ctx(routes):
    return {"conventions": CONV, "gh_api": FakeGhApi(routes)}


def test_bill282_timing_span_and_source():
    record = _make_record("BILL-282")
    routes = {
        "repos/iansmith/slopstop/issues/282": _load("issue_282.json"),
        "repos/iansmith/slopstop/issues/282/events": _load("events_282.json"),
        "repos/iansmith/slopstop/issues/282/timeline": _load("timeline_282.json"),
        "repos/iansmith/slopstop/pulls/377": _load("pr_377.json"),
        "repos/iansmith/slopstop/pulls/379": _load("pr_379.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["started_at"] == "2026-08-02T06:23:52Z"
    assert timing["completed_at"] == "2026-08-02T06:31:02Z"
    assert timing["span_seconds"] == 430


def test_bill282_completed_at_from_issue_not_closed_event():
    # The fixture's `closed` event reports 06:31:03Z while the issue object's
    # closed_at is 06:31:02Z. Using the event would yield 431, not 430.
    record = _make_record("BILL-282")
    events = _load("events_282.json")
    assert any(
        e["event"] == "closed" and e["created_at"] == "2026-08-02T06:31:03Z"
        for e in events
    )
    routes = {
        "repos/iansmith/slopstop/issues/282": _load("issue_282.json"),
        "repos/iansmith/slopstop/issues/282/events": events,
        "repos/iansmith/slopstop/issues/282/timeline": _load("timeline_282.json"),
        "repos/iansmith/slopstop/pulls/377": _load("pr_377.json"),
        "repos/iansmith/slopstop/pulls/379": _load("pr_379.json"),
    }
    github_source.collect(record, _ctx(routes))
    assert record["timing"]["completed_at"] == "2026-08-02T06:31:02Z"
    assert record["timing"]["span_seconds"] == 430


def test_bill355_timing_span():
    record = _make_record("BILL-355")
    routes = {
        "repos/iansmith/slopstop/issues/355": _load("issue_355.json"),
        "repos/iansmith/slopstop/issues/355/events": _load("events_355.json"),
        "repos/iansmith/slopstop/issues/355/timeline": _load("timeline_355.json"),
        "repos/iansmith/slopstop/pulls/357": _load("pr_357.json"),
        "repos/iansmith/slopstop/pulls/360": _load("pr_360.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["started_at"] == "2026-07-31T16:35:26Z"
    assert timing["completed_at"] == "2026-07-31T17:22:04Z"
    assert timing["span_seconds"] == 2798


def test_bill282_pr_resolution_picks_head_branch_match():
    record = _make_record("BILL-282")
    routes = {
        "repos/iansmith/slopstop/issues/282": _load("issue_282.json"),
        "repos/iansmith/slopstop/issues/282/events": _load("events_282.json"),
        "repos/iansmith/slopstop/issues/282/timeline": _load("timeline_282.json"),
        "repos/iansmith/slopstop/pulls/377": _load("pr_377.json"),
        "repos/iansmith/slopstop/pulls/379": _load("pr_379.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["pr"]["number"] == 377
    assert timing["pr"]["opened_at"] == "2026-08-02T06:29:01Z"
    assert timing["pr"]["merged_at"] == "2026-08-02T06:30:52Z"
    assert timing["sub_phases"]["start_to_pr_seconds"] == 309
    assert timing["sub_phases"]["pr_to_merge_seconds"] == 111


def test_bill355_pr_resolution_picks_head_branch_match():
    record = _make_record("BILL-355")
    routes = {
        "repos/iansmith/slopstop/issues/355": _load("issue_355.json"),
        "repos/iansmith/slopstop/issues/355/events": _load("events_355.json"),
        "repos/iansmith/slopstop/issues/355/timeline": _load("timeline_355.json"),
        "repos/iansmith/slopstop/pulls/357": _load("pr_357.json"),
        "repos/iansmith/slopstop/pulls/360": _load("pr_360.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["pr"]["number"] == 360
    assert timing["pr"]["opened_at"] == "2026-07-31T17:02:26Z"
    assert timing["pr"]["merged_at"] == "2026-07-31T17:21:58Z"
    assert timing["sub_phases"]["start_to_pr_seconds"] == 1620
    assert timing["sub_phases"]["pr_to_merge_seconds"] == 1172


def test_pr_unresolved_when_no_head_branch_matches():
    record = _make_record("BILL-9001")
    routes = {
        "repos/iansmith/slopstop/issues/9001": _load("issue_unresolved.json"),
        "repos/iansmith/slopstop/issues/9001/events": _load("events_unresolved.json"),
        "repos/iansmith/slopstop/issues/9001/timeline": _load("timeline_unresolved.json"),
        "repos/iansmith/slopstop/pulls/9099": _load("pr_9099.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["pr"] is None
    assert timing["pr_source"] == "unresolved"
    assert timing["sub_phases"]["start_to_pr_seconds"] is None
    assert timing["sub_phases"]["pr_to_merge_seconds"] is None


def test_started_at_falls_back_to_issue_created_when_no_label_event():
    record = _make_record("BILL-9002")
    routes = {
        "repos/iansmith/slopstop/issues/9002": _load("issue_nolabel.json"),
        "repos/iansmith/slopstop/issues/9002/events": _load("events_nolabel.json"),
        "repos/iansmith/slopstop/issues/9002/timeline": _load("timeline_nolabel.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["started_at"] == "2026-08-03T08:00:00Z"
    assert timing["started_at_source"] == "issue_created"


def test_open_issue_has_null_completed_fields_and_no_exception():
    record = _make_record("BILL-9003")
    routes = {
        "repos/iansmith/slopstop/issues/9003": _load("issue_open.json"),
        "repos/iansmith/slopstop/issues/9003/events": _load("events_open.json"),
        "repos/iansmith/slopstop/issues/9003/timeline": _load("timeline_open.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["completed_at"] is None
    assert timing["span_seconds"] is None


# --- Adversary gap tests (Step 0f, inline) ---
#
# [BOUNDARY / COVERAGE ASYMMETRY] Both bill282/bill355 fixtures exercise the
# single-match PR resolution path; nothing exercised the ticket's documented
# "more than one matches" branch (behavior 3: take earliest-merged, record the
# rest in pr_ambiguous).
def test_pr_ambiguous_when_multiple_head_branch_matches():
    record = _make_record("BILL-9004")
    routes = {
        "repos/iansmith/slopstop/issues/9004": _load("issue_ambiguous.json"),
        "repos/iansmith/slopstop/issues/9004/events": _load("events_ambiguous.json"),
        "repos/iansmith/slopstop/issues/9004/timeline": _load("timeline_ambiguous.json"),
        "repos/iansmith/slopstop/pulls/9200": _load("pr_9200.json"),
        "repos/iansmith/slopstop/pulls/9201": _load("pr_9201.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    # 9200 merged 10:30:00Z, 9201 merged 10:40:00Z -- earliest-merged (9200) wins.
    assert timing["pr"]["number"] == 9200
    assert timing["pr_ambiguous"] == [9201]


# [STATE INTERACTION] No fixture covered a PR that the head-branch rule
# resolves but that hasn't merged yet (merged_at is null) -- only the
# already-merged case was tested.
def test_pr_to_merge_seconds_null_when_pr_not_yet_merged():
    record = _make_record("BILL-9005")
    routes = {
        "repos/iansmith/slopstop/issues/9005": _load("issue_unmerged.json"),
        "repos/iansmith/slopstop/issues/9005/events": _load("events_unmerged.json"),
        "repos/iansmith/slopstop/issues/9005/timeline": _load("timeline_unmerged.json"),
        "repos/iansmith/slopstop/pulls/9301": _load("pr_9301.json"),
    }
    github_source.collect(record, _ctx(routes))
    timing = record["timing"]
    assert timing["pr"]["number"] == 9301
    assert timing["pr"]["merged_at"] is None
    assert timing["sub_phases"]["start_to_pr_seconds"] is not None
    assert timing["sub_phases"]["pr_to_merge_seconds"] is None
