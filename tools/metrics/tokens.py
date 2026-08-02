"""Transcript-derived token counts -- attribution, windowing, and the
three-quantity split (#386).

Two attribution modes:

- Worktree attribution: a `~/.claude/projects/` directory whose name ends in
  the ticket key is attributed wholly to that ticket, no time filter.
- Interactive windowing: the ticket's **own** project directory -- the one
  named after `ctx["project_root"]` -- contributes only those messages whose
  timestamp falls within `record["timing"]`'s `[started_at, completed_at]`.

Scoping the windowed mode to one directory is what #400 fixed. It used to
source from every directory that was not some *other* ticket's worktree, so
any unrelated project active in the same minutes was folded into the ticket's
counts -- live, that inflated BILL-282 by a whole second project.

`work` (input/cache-creation/output -- what the model admitted and produced)
and `context_tax` (cache-read -- what was paid to re-read prior context) are
kept as two separate groups; nothing here sums across them (charter R9).
"""

import datetime
import json


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


def _project_dir_name(project_root):
    """Claude Code's transcript-directory name for a project path.

    The path is flattened by replacing every "/" **and every "."** with "-",
    so `/Users/iansmith/ticket-plugin` becomes `-Users-iansmith-ticket-plugin`
    and `~/mazzy/.claude/worktrees/x` becomes the doubled-dash
    `-Users-iansmith-mazzy--claude-worktrees-x`.

    The dot half matters because `collect.py` takes `--conf PATH` and so runs
    against any repo in the fleet, several of which keep worktrees under a
    dotted directory. Under exact-match selection a half-right encoder does not
    mismatch loudly -- it names a directory that exists nowhere, and the ticket
    silently reports zero tokens.
    """
    return str(project_root).replace("/", "-").replace(".", "-")


def collect(record, ctx):
    ticket = record["ticket"]
    root = ctx["transcript_root"]
    # Subscript, never .get(): a default would silently restore the unscoped scan.
    project_dir = _project_dir_name(ctx["project_root"])

    if not root.is_dir():
        record["tokens"] = None
        return

    worktree_suffix = f"-{ticket}"
    worktree_dirs = [
        child
        for child in sorted(root.iterdir())
        if child.is_dir() and child.name.endswith(worktree_suffix)
    ]

    # Exactly one directory can be the ticket's own project, so look it up
    # directly rather than filtering the whole listing down to a one-element
    # list. A project dir whose own name ends in `-<ticket>` is claimed by the
    # worktree arm above, which `or` then short-circuits -- same precedence the
    # single if/elif pass had.
    own_dir = root / project_dir
    windowed = not worktree_dirs
    source_dirs = worktree_dirs or ([own_dir] if own_dir.is_dir() else [])

    window = None
    if windowed:
        timing = record.get("timing")
        if timing and timing.get("started_at"):
            started = _parse_ts(timing["started_at"])
            completed_at = timing.get("completed_at") or timing["started_at"]
            window = (started, _parse_ts(completed_at))

    position_candidates = []  # (timestamp, turn_index, entry)
    transcript_dirs = []

    for d in source_dirs:
        contributed = False
        for jsonl_path in sorted(d.glob("*.jsonl")):
            full_entries = _usage_bearing_entries(jsonl_path)
            for idx, entry in enumerate(full_entries):
                ts = _parse_ts(entry["timestamp"])
                in_scope = not windowed or (
                    window is not None and window[0] <= ts <= window[1]
                )
                if not in_scope:
                    continue
                position_candidates.append((ts, idx, entry))
                contributed = True
        if contributed:
            transcript_dirs.append(d.name)

    counted_entries = [entry for _, _, entry in position_candidates]
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
        "transcript_dirs": transcript_dirs,
        "windowed": windowed,
        "session_position": session_position,
    }
