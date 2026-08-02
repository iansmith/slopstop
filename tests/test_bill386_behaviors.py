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

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools" / "metrics"))

import tokens  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "metrics"


class FakeConventions:
    def __init__(self, prefix):
        self.prefix = prefix


def make_ctx():
    return {
        "conventions": FakeConventions("BILL"),
        "transcript_root": FIXTURES,
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


def _walk_values(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_values(item)


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

    for key, value in _walk_values(result):
        assert "total" not in key.lower(), f"forbidden 'total' key: {key}"
        if isinstance(value, int) and not isinstance(value, bool):
            assert value != forbidden_sum, (
                f"key {key!r} equals the sum of work + context_tax"
            )
