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
    # timing is populated as of BILL-385 (github_source.py is no longer a
    # stub); tokens/phases/signals remain stubs, owned by #386/#387/#388.
    result = run_collect(["BILL-282"])
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert set(record.keys()) == SCHEMA_KEYS
    assert record["schema"] == "slopstop.derived-metrics/1"
    assert record["ticket"] == "BILL-282"
    assert record["timing"]["span_seconds"] == 430
    # tokens is real as of BILL-386. BILL-282's directory isn't a worktree
    # (no ticket-suffixed dir under ~/.claude/projects/), so windowing
    # applies over record["timing"]'s real [started_at, completed_at] span
    # (real as of BILL-385). Windowing legitimately scans whatever
    # ~/.claude/projects/ transcripts overlap that wall-clock window --
    # "coarse timing is the accepted answer for interactive runs" (BILL-387's
    # own DoD language) means this is live, non-deterministic data, not a
    # fixed zero. Assert shape only, not exact counts.
    tokens = record["tokens"]
    assert set(tokens.keys()) == {
        "work",
        "context_tax",
        "messages",
        "transcript_dirs",
        "windowed",
        "session_position",
    }
    assert tokens["windowed"] is True
    assert set(tokens["work"].keys()) == {
        "input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
    }
    assert set(tokens["context_tax"].keys()) == {"cache_read_input_tokens"}
    # phases is real as of BILL-387 (markers.py); BILL-282 is an interactive
    # ticket with zero comments, so fleet is False and markers is empty.
    assert record["phases"] == {"markers": [], "fleet": False, "briefed_at": None}
    # BILL-282 carries no `## slopstop signals` comments (#388): all four keys
    # present and null, per that ticket's observable behavior 3 -- not the bare
    # `None` this assertion pinned back when signals.py was a no-op stub.
    assert record["signals"] == {
        "phase0_tests_red": None,
        "phase0_tests_pass_unexpected": None,
        "simplify_line_delta": None,
        "benchmark_overrides": None,
        "unparsed": [],
    }


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
    assert record["timing"]["span_seconds"] == 430
