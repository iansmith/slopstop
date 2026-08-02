"""
Phase 0 red tests for BILL-390 -- validate the collector against BILL-282 and
BILL-355 with LIVE invocations (real GitHub API, real transcripts -- no
fixture substitution for these two tickets).

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/390). Transcription, not
authorship: every pinned value below comes from the ticket's Definition of
Done, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Oracle for the expected values: recorded 2026-08-02 before any collector
existed -- GitHub (`gh api` for issues 282/355, their events and comments)
and independent transcript summation.

Test command:
    python3 -m pytest tests/test_bill390_behaviors.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import assert_no_forbidden_keys

REPO_ROOT = Path(__file__).parent.parent
COLLECT = REPO_ROOT / "tools" / "metrics" / "collect.py"

SCHEMA_KEYS = {
    "schema",
    "ticket",
    "system",
    "repo",
    "generated_at",
    "timing",
    "tokens",
    "phases",
    "signals",
}

EXPECTED_SIGNALS_NULL = {
    "phase0_tests_red": None,
    "phase0_tests_pass_unexpected": None,
    "simplify_line_delta": None,
    "benchmark_overrides": None,
    "unparsed": [],
}


def run_collect(args, cwd=None):
    return subprocess.run(
        [sys.executable, str(COLLECT)] + args,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def bill282_record():
    result = run_collect(["BILL-282"])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def bill355_record():
    result = run_collect(["BILL-355"])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_bill282_live_record_matches_dod_pinned_values(bill282_record):
    record = bill282_record

    assert set(record.keys()) == SCHEMA_KEYS
    assert record["ticket"] == "BILL-282"

    assert record["timing"]["span_seconds"] == 430

    tok = record["tokens"]
    assert tok["messages"] == 61
    assert tok["work"]["output_tokens"] == 63286
    assert tok["context_tax"]["cache_read_input_tokens"] == 10877358
    assert tok["session_position"] == {
        "entry_context_tokens": 161604,
        "turn_index": 92,
    }

    assert record["phases"]["fleet"] is False

    assert record["signals"] == EXPECTED_SIGNALS_NULL

    forbidden_sum = (
        tok["work"]["input_tokens"]
        + tok["work"]["cache_creation_input_tokens"]
        + tok["work"]["output_tokens"]
        + tok["context_tax"]["cache_read_input_tokens"]
    )
    assert_no_forbidden_keys(record, forbidden_sum=forbidden_sum)


def test_bill355_live_record_matches_dod_pinned_values(bill355_record):
    record = bill355_record

    assert set(record.keys()) == SCHEMA_KEYS
    assert record["ticket"] == "BILL-355"

    assert record["timing"]["span_seconds"] == 2798

    tok = record["tokens"]
    assert tok["messages"] == 542
    assert tok["work"]["output_tokens"] == 270640
    assert tok["context_tax"]["cache_read_input_tokens"] == 118523401
    assert tok["session_position"] == {
        "entry_context_tokens": 58233,
        "turn_index": 0,
    }

    assert record["phases"]["fleet"] is True
    assert len(record["phases"]["markers"]) == 13

    forbidden_sum = (
        tok["work"]["input_tokens"]
        + tok["work"]["cache_creation_input_tokens"]
        + tok["work"]["output_tokens"]
        + tok["context_tax"]["cache_read_input_tokens"]
    )
    assert_no_forbidden_keys(record, forbidden_sum=forbidden_sum)


def test_both_tickets_spend_priced_with_no_unpriced_models(
    bill282_record, bill355_record
):
    for record in (bill282_record, bill355_record):
        spend = record["tokens"]["spend"]
        assert spend["unpriced_models"] == []
        assert spend["usd"] > 0
        assert "entry_context_tokens" in spend["session_position"]


def test_bill282_out_of_root_invocation_still_counts_the_owning_project():
    # BILL-400 adversary gap test. The out-of-root case below exercises
    # BILL-355, which is worktree-attributed and so survives a project_root
    # derived from cwd. BILL-282 is the windowed ticket: derive project_root
    # from cwd here and every count silently goes to zero, with no error.
    result = subprocess.run(
        [
            sys.executable,
            str(COLLECT.resolve()),
            "BILL-282",
            "--conf",
            "../.project-conf.toml",
        ],
        cwd=str(REPO_ROOT / "tests"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    tok = json.loads(result.stdout)["tokens"]
    assert tok["transcript_dirs"] == ["-Users-iansmith-ticket-plugin"]
    assert tok["messages"] == 61
    assert tok["work"]["output_tokens"] == 63286
    assert tok["context_tax"]["cache_read_input_tokens"] == 10877358


def test_bill355_entrypoint_exercised_out_of_root():
    result = subprocess.run(
        [
            sys.executable,
            str(COLLECT.resolve()),
            "BILL-355",
            "--conf",
            "../.project-conf.toml",
        ],
        cwd=str(REPO_ROOT / "tests"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert record["ticket"] == "BILL-355"
    assert record["timing"]["span_seconds"] == 2798
