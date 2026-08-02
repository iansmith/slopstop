"""
Phase 0 red tests for BILL-388 — Relocate the four non-derivable signals to
comments.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/388). Transcription, not
authorship: every assertion and every expected value below is pinned by the
ticket, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Test command:
    python3 -m pytest tests/test_bill388_behaviors.py -v
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "metrics"))

import signals  # noqa: E402

NULL_SIGNALS = {
    "phase0_tests_red": None,
    "phase0_tests_pass_unexpected": None,
    "simplify_line_delta": None,
    "benchmark_overrides": None,
    "unparsed": [],
}


def _comment(comment_id, created_at, body):
    return {"id": comment_id, "created_at": created_at, "body": body}


def test_merge_signals_newest_wins_per_key():
    older = _comment(
        1001,
        "2026-08-01T00:00:00Z",
        '## slopstop signals\n\n```json\n{"phase0_tests_red": 3}\n```\n',
    )
    newer = _comment(
        1002,
        "2026-08-02T00:00:00Z",
        '## slopstop signals\n\n```json\n{"phase0_tests_red": 5}\n```\n',
    )
    result = signals.merge_signals([older, newer])
    expected = dict(NULL_SIGNALS, phase0_tests_red=5)
    assert result == expected


def test_merge_signals_empty_fixture_yields_four_null_keys():
    result = signals.merge_signals([])
    assert result == NULL_SIGNALS


def test_merge_signals_malformed_fence_recorded_unparsed_collector_exits_0():
    malformed = _comment(
        2001, "2026-08-02T00:00:00Z", "## slopstop signals\n\n```json\n{not json\n```\n"
    )
    result = signals.merge_signals([malformed])
    assert result["unparsed"] == [2001]

    # "the collector still exits 0" -- signals.collect() must complete without
    # raising even when a fetched comment's fence is malformed, since an
    # uncaught exception here is what would make the real collect.py process
    # exit non-zero.
    record = {"ticket": "BILL-282", "signals": None}
    ctx = {
        "conventions": type("Conv", (), {"repo": "iansmith/slopstop"})(),
        "gh_api": lambda path: [malformed],
    }
    signals.collect(record, ctx)
    assert record["signals"]["unparsed"] == [2001]


def test_merge_signals_newest_wins_is_per_key_not_per_comment():
    # A comment that only carries one key must not blank out a key set by an
    # older comment -- "newest-wins per key" means per-key precedence, not
    # "the single newest comment wins outright".
    older = _comment(
        3001,
        "2026-08-01T00:00:00Z",
        '## slopstop signals\n\n```json\n{"simplify_line_delta": 12}\n```\n',
    )
    newer = _comment(
        3002,
        "2026-08-02T00:00:00Z",
        '## slopstop signals\n\n```json\n{"phase0_tests_red": 1}\n```\n',
    )
    result = signals.merge_signals([older, newer])
    expected = dict(NULL_SIGNALS, simplify_line_delta=12, phase0_tests_red=1)
    assert result == expected


def test_merge_signals_ignores_comments_without_signals_block():
    unrelated = _comment(4001, "2026-08-01T00:00:00Z", "Looks good to me!")
    header_no_fence = _comment(
        4002, "2026-08-02T00:00:00Z", "## slopstop signals\n\nforgot the fence"
    )
    result = signals.merge_signals([unrelated, header_no_fence])
    assert result == NULL_SIGNALS
