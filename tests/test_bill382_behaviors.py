"""
Phase 0 red tests for BILL-382 — Collector skeleton: entrypoint, conventions
decoder, record schema.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/382). Transcription, not
authorship: every assertion and every expected value below is pinned by the
ticket, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Test command:
    python3 -m pytest tests/test_bill382_behaviors.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
COLLECT = REPO_ROOT / "tools" / "metrics" / "collect.py"
CONF = REPO_ROOT / ".project-conf.toml"

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


def run_collect(args, cwd=None):
    return subprocess.run(
        [sys.executable, str(COLLECT)] + args,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_record_shape_and_stub_nulls():
    result = run_collect(["BILL-282"])
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert set(record.keys()) == SCHEMA_KEYS
    assert record["schema"] == "slopstop.derived-metrics/1"
    assert record["ticket"] == "BILL-282"
    assert record["timing"] is None
    # tokens is real as of BILL-386. BILL-282's directory isn't a worktree
    # (no ticket-suffixed dir under ~/.claude/projects/), so windowing
    # applies; timing is null (github_source.py, #385, is still a stub), so
    # per BILL-386 behavior 2 the windowed directories contribute nothing.
    assert record["tokens"] == {
        "work": {
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 0,
        },
        "context_tax": {"cache_read_input_tokens": 0},
        "messages": 0,
        "transcript_dirs": [],
        "windowed": True,
        "session_position": None,
    }
    assert record["phases"] is None
    assert record["signals"] is None


def test_prefix_mismatch_exits_nonzero_with_exact_message():
    result = run_collect(["FOO-1"])
    assert result.returncode != 0
    assert (
        "FOO-1 does not match prefix 'BILL' in .project-conf.toml"
        in result.stderr
    )


def test_conventions_decodes_this_repo_conf():
    sys.path.insert(0, str(REPO_ROOT / "tools" / "metrics"))
    import conventions

    conv = conventions.load(CONF)
    assert conv.system == "github"
    assert conv.repo == "iansmith/slopstop"
    assert conv.prefix == "BILL"
    assert conv.status_labels["in_progress"] == "status:in-progress"


def test_entrypoint_exercised_out_of_root():
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
    record = json.loads(result.stdout)
    assert set(record.keys()) == SCHEMA_KEYS
    assert record["ticket"] == "BILL-282"
