#!/usr/bin/env python3
"""Stop hook: append one cost/token-usage row per invocation.

Reads the Stop hook payload from stdin, resolves the transcript it names
**relative to the payload's own `cwd` field** (not the process's working
directory — the hook can run with a cwd that differs from the session's),
sums the transcript's per-assistant-message `usage` blocks, and appends one
JSON row to `<payload cwd>/.slopstop/metrics/costs.jsonl`.

Never blocks a stage: exits 0 on every input, including malformed stdin and
a missing transcript file. Telemetry observes; it does not participate
(BILL-351 C15).
"""

import json
import os
import sys
from datetime import datetime, timezone

METRICS_RELATIVE_PATH = os.path.join(".slopstop", "metrics", "costs.jsonl")
ALL_ZERO_WARNING = "all-zero token rate"
WINDOW_SIZE = 50
WINDOW_MIN_ROWS = 10
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def sum_usage(transcript_path):
    totals = {k: 0 for k in USAGE_KEYS}
    with open(transcript_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message") or {}
            usage = message.get("usage")
            if not usage:
                continue
            for key in USAGE_KEYS:
                totals[key] += usage.get(key, 0) or 0
    return totals


def is_all_zero(row):
    return all(row.get(key, 0) == 0 for key in USAGE_KEYS)


def read_existing_rows(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def all_zero_window_active(existing_rows):
    window = existing_rows[-WINDOW_SIZE:]
    if len(window) < WINDOW_MIN_ROWS:
        return False
    return all(is_all_zero(row) for row in window)


def build_row(payload, usage_totals, payload_cwd):
    row = {
        "session_id": payload.get("session_id"),
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": payload_cwd,
        "model": payload.get("model"),
    }
    row.update(usage_totals)
    return row


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return 0

    if not isinstance(payload, dict):
        return 0

    payload_cwd = payload.get("cwd") or os.getcwd()
    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0
    if not os.path.isabs(transcript_path):
        transcript_path = os.path.join(payload_cwd, transcript_path)

    if not os.path.isfile(transcript_path):
        return 0

    try:
        usage_totals = sum_usage(transcript_path)
    except Exception:
        return 0

    if not payload.get("model"):
        try:
            payload["model"] = last_assistant_model(transcript_path)
        except Exception:
            pass

    out_path = os.path.join(payload_cwd, METRICS_RELATIVE_PATH)

    try:
        existing_rows = read_existing_rows(out_path)
        new_row = build_row(payload, usage_totals, payload_cwd)

        if is_all_zero(new_row) and all_zero_window_active(existing_rows):
            sys.stderr.write(
                f"cost-tracker: {ALL_ZERO_WARNING} over the last "
                f"{min(len(existing_rows), WINDOW_SIZE)} rows — suppressing "
                "this all-zero row (metering may be broken upstream)\n"
            )
            return 0

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "a") as f:
            f.write(json.dumps(new_row) + "\n")
    except Exception:
        return 0

    return 0


def last_assistant_model(transcript_path):
    model = None
    with open(transcript_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message") or {}
            if message.get("model"):
                model = message["model"]
    return model


if __name__ == "__main__":
    sys.exit(main())
