"""
Phase 0 red tests for BILL-389 — USD spend from `prices.toml`, never
published without session position.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/389). Transcription, not
authorship: every pinned value below comes from the ticket's Definition of
Done, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

The hand-computed USD figures are `rate x counter` read from
`router/prices.toml`'s `claude-sonnet-5` row (input=2.00, output=10.00,
cache_write=2.50, cache_read=0.20 USD/MTok) at implementation time, written
here as literals per the ticket's own instruction not to duplicate the rate
table.

Test command:
    python3 -m pytest tests/test_bill389_behaviors.py -v
"""

import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools" / "metrics"))

import pricing  # noqa: E402
import tokens  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "metrics"

SONNET_5_RATES = {
    "input": 2.00,
    "output": 10.00,
    "cache_write": 2.50,
    "cache_read": 0.20,
}


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


def _walk_values(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_values(item)


def test_price_usage_single_message_against_prices_toml():
    usage = {
        "input_tokens": 500_000,
        "cache_creation_input_tokens": 200_000,
        "output_tokens": 100_000,
        "cache_read_input_tokens": 1_000_000,
    }
    prices = {"claude-sonnet-5": SONNET_5_RATES}

    usd = pricing.price_usage("claude-sonnet-5", usage, prices)

    expected = (
        500_000 * 2.00 + 200_000 * 2.50 + 100_000 * 10.00 + 1_000_000 * 0.20
    ) / 1_000_000
    assert round(usd, 6) == round(expected, 6) == 2.700000


def test_unpriced_model_contributes_nothing_but_is_named():
    prices = {"claude-sonnet-5": SONNET_5_RATES}
    entries = [
        {
            "model": "claude-sonnet-5",
            "usage": {
                "input_tokens": 500_000,
                "cache_creation_input_tokens": 200_000,
                "output_tokens": 100_000,
                "cache_read_input_tokens": 1_000_000,
            },
        },
        {
            "model": "claude-not-a-real-model",
            "usage": {
                "input_tokens": 999,
                "cache_creation_input_tokens": 999,
                "output_tokens": 999,
                "cache_read_input_tokens": 999,
            },
        },
    ]

    usd, unpriced_models = pricing.price_entries(entries, prices)

    assert round(usd, 6) == 2.700000
    assert unpriced_models == ["claude-not-a-real-model"]


def test_bill355_worktree_spend_matches_hand_computed_usd():
    record = make_record("BILL-355")
    ctx = make_ctx()
    tokens.collect(record, ctx)
    pricing.collect(record, ctx)

    spend = record["tokens"]["spend"]
    expected = (
        1666 * 2.00 + 1_019_920 * 2.50 + 270_640 * 10.00 + 118_523_401 * 0.20
    ) / 1_000_000
    assert spend["usd"] == pytest.approx(expected, abs=1e-6)
    assert spend["unpriced_models"] == []
    assert spend["session_position"] == record["tokens"]["session_position"]


def test_spend_absent_and_withheld_reason_present_when_session_position_null():
    record = make_record("BILL-282", timing=None)
    ctx = make_ctx()
    tokens.collect(record, ctx)
    assert record["tokens"]["session_position"] is None

    pricing.collect(record, ctx)

    assert "spend" not in record["tokens"]
    assert isinstance(record["tokens"]["spend_withheld"], str)
    assert record["tokens"]["spend_withheld"]


def test_no_spend_key_matches_basis_or_effective():
    record = make_record("BILL-355")
    ctx = make_ctx()
    tokens.collect(record, ctx)
    pricing.collect(record, ctx)

    spend = record["tokens"]["spend"]
    for key, _ in _walk_values(spend):
        assert not re.search(r"basis|effective", key, re.IGNORECASE), (
            f"forbidden key in spend object: {key!r}"
        )
