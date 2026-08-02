"""USD spend from `router/prices.toml` (runs after tokens.py, prices what it
counted), owned by #389.

Prices each in-scope message at its own `model`'s rate; a model absent from
`prices.toml` contributes $0 and is named in `unpriced_models` rather than
silently vanishing. Never emits a `spend` figure without the session position
#386 recorded on the record -- charter R10, enforced here rather than left to
callers to remember.
"""

import pathlib
import tomllib

import tokens

PRICES_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.parent / "router" / "prices.toml"
)

_RATE_FIELDS = {
    "input_tokens": "input",
    "cache_creation_input_tokens": "cache_write",
    "output_tokens": "output",
    "cache_read_input_tokens": "cache_read",
}


def _load_prices():
    with PRICES_PATH.open("rb") as f:
        data = tomllib.load(f)
    return data.get("models", {})


def price_usage(model, usage, prices):
    row = prices.get(model)
    if row is None:
        return 0.0
    return sum(
        usage.get(field, 0) * row[rate_key] / 1_000_000
        for field, rate_key in _RATE_FIELDS.items()
    )


def price_entries(entries, prices):
    """Price `{"model", "usage"}` entries. Returns `(usd, unpriced_models)`."""
    usd = 0.0
    unpriced = set()
    for entry in entries:
        model = entry["model"]
        if model not in prices:
            unpriced.add(model)
            continue
        usd += price_usage(model, entry["usage"], prices)
    return usd, sorted(unpriced)


def _in_scope_model_usages(record, ctx):
    """Re-walk the messages #386 already counted, keeping each one's model.

    `record["tokens"]["transcript_dirs"]` and `["windowed"]` are #386's own
    scope decision; this only re-reads those same directories to recover the
    per-message model that the aggregate counters don't retain.
    """
    tok = record["tokens"]
    window = None
    if tok["windowed"]:
        timing = record.get("timing")
        if timing and timing.get("started_at"):
            started = tokens._parse_ts(timing["started_at"])
            completed_at = timing.get("completed_at") or timing["started_at"]
            window = (started, tokens._parse_ts(completed_at))

    root = ctx["transcript_root"]
    result = []
    for dir_name in tok["transcript_dirs"]:
        for jsonl_path in sorted((root / dir_name).glob("*.jsonl")):
            for entry in tokens._usage_bearing_entries(jsonl_path):
                if tok["windowed"]:
                    if window is None:
                        continue
                    ts = tokens._parse_ts(entry["timestamp"])
                    if not (window[0] <= ts <= window[1]):
                        continue
                result.append(
                    {
                        "model": entry["message"]["model"],
                        "usage": entry["message"]["usage"],
                    }
                )
    return result


def collect(record, ctx):
    tok = record.get("tokens")
    if tok is None:
        return

    session_position = tok.get("session_position")
    if session_position is None:
        tok["spend_withheld"] = (
            "no session_position on record -- charter R10 forbids publishing "
            "spend without the context size it was measured at"
        )
        return

    prices = _load_prices()
    entries = _in_scope_model_usages(record, ctx)
    usd, unpriced_models = price_entries(entries, prices)

    tok["spend"] = {
        "usd": usd,
        "unpriced_models": unpriced_models,
        "session_position": session_position,
    }
