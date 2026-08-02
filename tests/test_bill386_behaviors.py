"""
Phase 0 red tests for BILL-386 — Transcript-derived token counts: attribution,
windowing, and the three-quantity split.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/386). Transcription, not
authorship: every pinned value below comes from the ticket's Definition of
Done, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Fixtures under tests/fixtures/metrics/ are vendored reduced transcript
fixtures, retaining only `type`, `timestamp`, and `message.model` /
`message.usage` per entry, per the ticket's Test expectations. The BILL-355
fixture directory holds two `.jsonl` files plus `.jsonl.wakatime` sidecars
(poisoned with out-of-range usage) to exercise the "match `*.jsonl` exactly"
requirement; its two files are named so that filename order ("969397ba...")
is the reverse of timestamp order ("c238319a..." holds the earlier session) --
this is the ticket's own stated real shape for BILL-355. The BILL-282 fixture
directory is not ticket-named (a plain interactive project directory) and
carries out-of-window filler before, inside, and after the window.

Test command:
    python3 -m pytest tests/test_bill386_behaviors.py -v
"""

import json
import pathlib
import sys

import pytest

from conftest import assert_no_forbidden_keys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools" / "metrics"))

import tokens  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "metrics"


class FakeConventions:
    def __init__(self, prefix):
        self.prefix = prefix


# Claude Code encodes a project path into a transcript-directory name by
# replacing "/" with "-", so this root's encoded form is the directory name
# `-Users-iansmith-ticket-plugin` -- which is what the vendored fixture
# directory is called, and what the synthetic BILL-400 fixtures below reuse.
PROJECT_ROOT = pathlib.Path("/Users/iansmith/ticket-plugin")
PROJECT_DIR = "-Users-iansmith-ticket-plugin"


def make_ctx(transcript_root=FIXTURES):
    return {
        "conventions": FakeConventions("BILL"),
        "transcript_root": transcript_root,
        "project_root": PROJECT_ROOT,
    }


def make_record(ticket, timing=None):
    return {
        "ticket": ticket,
        "timing": timing,
        "tokens": None,
    }


def test_bill355_worktree_attribution_no_window():
    record = make_record("BILL-355")
    tokens.collect(record, make_ctx())

    result = record["tokens"]
    assert result["work"]["input_tokens"] == 1666
    assert result["work"]["cache_creation_input_tokens"] == 1019920
    assert result["work"]["output_tokens"] == 270640
    assert result["context_tax"]["cache_read_input_tokens"] == 118523401
    assert result["messages"] == 542
    assert result["windowed"] is False


def test_bill282_interactive_windowing():
    record = make_record(
        "BILL-282",
        timing={
            "started_at": "2026-08-02T06:23:52Z",
            "completed_at": "2026-08-02T06:31:02Z",
        },
    )
    tokens.collect(record, make_ctx())

    result = record["tokens"]
    assert result["work"]["input_tokens"] == 113
    assert result["work"]["cache_creation_input_tokens"] == 90759
    assert result["work"]["output_tokens"] == 63286
    assert result["context_tax"]["cache_read_input_tokens"] == 10877358
    assert result["messages"] == 61
    assert result["windowed"] is True


def test_non_worktree_directory_with_no_timing_contributes_nothing():
    # Behavior 2: "When timing is null or has no started_at, non-worktree
    # directories contribute nothing." No ticket key in this record's suffix
    # maps to a worktree dir, and timing is null.
    record = make_record("BILL-282", timing=None)
    tokens.collect(record, make_ctx())

    result = record["tokens"]
    assert result["work"]["input_tokens"] == 0
    assert result["work"]["cache_creation_input_tokens"] == 0
    assert result["work"]["output_tokens"] == 0
    assert result["context_tax"]["cache_read_input_tokens"] == 0
    assert result["messages"] == 0
    assert result["windowed"] is True


def test_bill355_session_position():
    record = make_record("BILL-355")
    tokens.collect(record, make_ctx())

    position = record["tokens"]["session_position"]
    assert position == {"entry_context_tokens": 58233, "turn_index": 0}


def test_bill282_session_position():
    record = make_record(
        "BILL-282",
        timing={
            "started_at": "2026-08-02T06:23:52Z",
            "completed_at": "2026-08-02T06:31:02Z",
        },
    )
    tokens.collect(record, make_ctx())

    position = record["tokens"]["session_position"]
    assert position == {"entry_context_tokens": 161604, "turn_index": 92}


def test_entry_context_tokens_uses_timestamp_not_filename_order():
    # BILL-355's directory sorts "969397ba..." first by filename but
    # "c238319a..." holds the earlier session -- session_position must be
    # derived from the earlier *timestamp*, not from file iteration order.
    record = make_record("BILL-355")
    tokens.collect(record, make_ctx())

    position = record["tokens"]["session_position"]
    assert position["entry_context_tokens"] == 58233
    assert position["turn_index"] == 0


# --------------------------------------------------------------------------
# BILL-400 -- interactive windowing must be scoped to the ticket's own project
# directory. Transcribed from the ticket's Test expectations
# (https://github.com/iansmith/slopstop/issues/400). Transcription, not
# authorship: if a pinned value below is wrong, the sanctioned exit is the
# TICKET UNDERSPECIFIED halt (TD-4a), not an edit to this file.
#
# Before the fix, `collect` sourced from *every* project directory that is not
# some other ticket's worktree, so unrelated concurrent work in a different
# project landed in the ticket's counts.
# --------------------------------------------------------------------------

FOREIGN_DIR = "-Users-iansmith-elsewhere"

CROSS_PROJECT_WINDOW = {
    "started_at": "2026-08-02T06:00:00Z",
    "completed_at": "2026-08-02T07:00:00Z",
}


def make_entry(ts, input_tokens, cache_creation, output_tokens, cache_read):
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "model": "claude-sonnet-5",
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
            },
        },
    }


def write_session(d, entries, name="session1.jsonl"):
    """One transcript file of `entries` in directory `d`, creating it if needed."""
    d.mkdir(exist_ok=True)
    with (d / name).open("w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def write_cross_project_root(tmp_path):
    """Two project directories whose activity overlaps the same window.

    Neither is a worktree directory, so both reach the windowing branch. The
    foreign directory's first entry is deliberately *earlier* than the owning
    directory's first entry, so a cross-directory `session_position` shows up
    as a wrong value rather than as a coincidentally-equal one.

    Writes into `tmp_path` in place; the caller already holds that path.
    """
    layout = {
        PROJECT_DIR: [
            make_entry("2026-08-02T06:10:00.000Z", 10, 20, 100, 1000),
            make_entry("2026-08-02T06:20:00.000Z", 1, 2, 50, 500),
        ],
        FOREIGN_DIR: [
            make_entry("2026-08-02T06:05:00.000Z", 7, 3, 999, 9999),
            make_entry("2026-08-02T06:30:00.000Z", 5, 5, 888, 8888),
        ],
    }
    for name, entries in layout.items():
        write_session(tmp_path / name, entries)


def test_windowing_counts_only_the_ticket_owning_project_directory(tmp_path):
    # DoD item 2: two project directories with overlapping timestamps; only
    # the ticket-owning directory's usage is counted.
    write_cross_project_root(tmp_path)
    record = make_record("BILL-282", timing=CROSS_PROJECT_WINDOW)
    tokens.collect(record, make_ctx(transcript_root=tmp_path))

    result = record["tokens"]
    assert result["windowed"] is True
    assert result["transcript_dirs"] == [PROJECT_DIR]
    assert result["messages"] == 2
    assert result["work"]["input_tokens"] == 11
    assert result["work"]["cache_creation_input_tokens"] == 22
    assert result["work"]["output_tokens"] == 150
    assert result["context_tax"]["cache_read_input_tokens"] == 1500


def test_session_position_ignores_foreign_project_directories(tmp_path):
    # DoD item 3: session_position stays correct -- derived from the earliest
    # entry of the ticket's OWN directory, never from an earlier entry that
    # happens to sit in an unrelated project's transcript.
    write_cross_project_root(tmp_path)
    record = make_record("BILL-282", timing=CROSS_PROJECT_WINDOW)
    tokens.collect(record, make_ctx(transcript_root=tmp_path))

    # 10 + 20 + 1000 -- the owning directory's 06:10 entry, not the foreign
    # directory's earlier 06:05 entry (which would give 7 + 3 + 9999).
    assert record["tokens"]["session_position"] == {
        "entry_context_tokens": 1030,
        "turn_index": 0,
    }


# --- Step 0f adversary gap tests ------------------------------------------
# The two tests above pass under a *lossy* scoping rule and under no time
# filter at all -- both proven by patching a scratch copy of tokens.py. These
# close those holes.

# A real sibling directory on this machine: `~/ticket-plugin/router` encodes to
# the owning project's name plus "-router". Any rule that selects directories
# by name prefix rather than exactly swallows it.
SIBLING_DIR = "-Users-iansmith-ticket-plugin-router"
SIBLING_PROJECT_ROOT = pathlib.Path("/Users/iansmith/ticket-plugin-router")


def write_sibling_prefixed_root(tmp_path):
    """`write_cross_project_root` plus a directory whose name has the owning
    project's encoded name as a strict prefix."""
    write_cross_project_root(tmp_path)
    write_session(
        tmp_path / SIBLING_DIR,
        [make_entry("2026-08-02T06:15:00.000Z", 3, 4, 777, 7777)],
    )


def test_sibling_project_sharing_the_root_name_prefix_is_excluded(tmp_path):
    write_sibling_prefixed_root(tmp_path)
    record = make_record("BILL-282", timing=CROSS_PROJECT_WINDOW)
    tokens.collect(record, make_ctx(transcript_root=tmp_path))

    result = record["tokens"]
    assert result["transcript_dirs"] == [PROJECT_DIR]
    assert result["messages"] == 2
    assert result["work"]["output_tokens"] == 150


def test_sibling_prefixed_project_selected_exactly_when_it_owns_the_ticket(tmp_path):
    # The reverse direction: selecting the longer-named sibling must not drag
    # in its shorter-named neighbour.
    write_sibling_prefixed_root(tmp_path)
    ctx = make_ctx(transcript_root=tmp_path)
    ctx["project_root"] = SIBLING_PROJECT_ROOT
    record = make_record("BILL-282", timing=CROSS_PROJECT_WINDOW)
    tokens.collect(record, ctx)

    result = record["tokens"]
    assert result["transcript_dirs"] == [SIBLING_DIR]
    assert result["messages"] == 1
    assert result["work"]["output_tokens"] == 777


def test_windowing_still_filters_inside_the_owning_project_directory(tmp_path):
    # Scoping must not replace the time filter. Two of these five entries sit
    # outside the window, and two sit exactly on its inclusive boundaries.
    write_cross_project_root(tmp_path)
    entries = [
        make_entry("2026-08-02T05:59:59.000Z", 100, 200, 9000, 90000),  # before
        make_entry("2026-08-02T06:00:00.000Z", 1, 0, 1, 0),  # == started_at
        make_entry("2026-08-02T06:10:00.000Z", 10, 20, 100, 1000),
        make_entry("2026-08-02T07:00:00.000Z", 0, 0, 2, 0),  # == completed_at
        make_entry("2026-08-02T07:00:01.000Z", 500, 0, 8000, 0),  # after
    ]
    write_session(tmp_path / PROJECT_DIR, entries, "session2.jsonl")

    record = make_record("BILL-282", timing=CROSS_PROJECT_WINDOW)
    tokens.collect(record, make_ctx(transcript_root=tmp_path))

    result = record["tokens"]
    assert result["messages"] == 5  # 2 from session1 + 3 in-window from session2
    assert result["work"]["output_tokens"] == 253  # 150 + 1 + 100 + 2
    # The earliest in-window entry is session2's 06:00:00 -- and its turn_index
    # is its index in the FULL file (1), not in the filtered list (0).
    assert result["session_position"] == {"entry_context_tokens": 1, "turn_index": 1}


def test_tokens_collect_rejects_a_ctx_without_project_root(tmp_path):
    # Fail loud. A `.get()` fallback that quietly reverts to the unscoped scan
    # would let any future caller reintroduce this bug invisibly.
    write_cross_project_root(tmp_path)
    ctx = make_ctx(transcript_root=tmp_path)
    del ctx["project_root"]
    record = make_record("BILL-282", timing=CROSS_PROJECT_WINDOW)

    with pytest.raises(KeyError):
        tokens.collect(record, ctx)


def test_no_total_field_or_value_anywhere_in_tokens():
    record = make_record("BILL-355")
    tokens.collect(record, make_ctx())

    result = record["tokens"]
    forbidden_sum = (
        result["work"]["input_tokens"]
        + result["work"]["cache_creation_input_tokens"]
        + result["work"]["output_tokens"]
        + result["context_tax"]["cache_read_input_tokens"]
    )

    assert_no_forbidden_keys(result, forbidden_sum=forbidden_sum)
