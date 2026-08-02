"""Transcript-derived token counts -- attribution, windowing, and the
three-quantity split (#386).

Two attribution modes:

- Worktree attribution: a `~/.claude/projects/` directory whose name ends in
  the ticket key is attributed wholly to that ticket, no time filter.
- Interactive windowing: for every other directory (excluding any directory
  that belongs to a *different* ticket's worktree), only messages whose
  timestamp falls within `record["timing"]`'s `[started_at, completed_at]`
  are counted.

`work` (input/cache-creation/output -- what the model admitted and produced)
and `context_tax` (cache-read -- what was paid to re-read prior context) are
kept as two separate groups; nothing here sums across them (charter R9).
"""

import datetime
import json
import re


def _parse_ts(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _usage_bearing_entries(path):
    entries = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("type") != "assistant":
                continue
            usage = entry.get("message", {}).get("usage")
            if usage is None:
                continue
            entries.append(entry)
    return entries


def _sum_usage(entries):
    input_tokens = cache_creation = output_tokens = cache_read = 0
    for entry in entries:
        usage = entry["message"]["usage"]
        input_tokens += usage.get("input_tokens", 0)
        cache_creation += usage.get("cache_creation_input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        cache_read += usage.get("cache_read_input_tokens", 0)
    return input_tokens, cache_creation, output_tokens, cache_read


def _entry_context_tokens(entry):
    usage = entry["message"]["usage"]
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


def collect(record, ctx):
    ticket = record["ticket"]
    conv = ctx["conventions"]
    root = ctx["transcript_root"]

    if not root.is_dir():
        record["tokens"] = None
        return

    worktree_suffix = f"-{ticket}"
    other_ticket_re = re.compile(rf"-{re.escape(conv.prefix)}-\d+$")

    worktree_dirs = []
    other_dirs = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.endswith(worktree_suffix):
            worktree_dirs.append(child)
        elif not other_ticket_re.search(child.name):
            other_dirs.append(child)

    windowed = not worktree_dirs
    source_dirs = worktree_dirs if worktree_dirs else other_dirs

    window = None
    if windowed:
        timing = record.get("timing")
        if timing and timing.get("started_at"):
            started = _parse_ts(timing["started_at"])
            completed_at = timing.get("completed_at") or timing["started_at"]
            window = (started, _parse_ts(completed_at))

    counted_entries = []
    position_candidates = []  # (timestamp, turn_index, entry)
    transcript_dirs = []

    for d in source_dirs:
        contributed = False
        for jsonl_path in sorted(d.glob("*.jsonl")):
            full_entries = _usage_bearing_entries(jsonl_path)
            for idx, entry in enumerate(full_entries):
                ts = _parse_ts(entry["timestamp"])
                if windowed:
                    in_scope = window is not None and window[0] <= ts <= window[1]
                else:
                    in_scope = True
                if not in_scope:
                    continue
                counted_entries.append(entry)
                position_candidates.append((ts, idx, entry))
                contributed = True
        if contributed:
            transcript_dirs.append(d.name)

    input_tokens, cache_creation, output_tokens, cache_read = _sum_usage(
        counted_entries
    )

    session_position = None
    if position_candidates:
        _, turn_index, earliest_entry = min(position_candidates, key=lambda c: c[0])
        session_position = {
            "entry_context_tokens": _entry_context_tokens(earliest_entry),
            "turn_index": turn_index,
        }

    record["tokens"] = {
        "work": {
            "input_tokens": input_tokens,
            "cache_creation_input_tokens": cache_creation,
            "output_tokens": output_tokens,
        },
        "context_tax": {
            "cache_read_input_tokens": cache_read,
        },
        "messages": len(counted_entries),
        "transcript_dirs": sorted(transcript_dirs),
        "windowed": windowed,
        "session_position": session_position,
    }
