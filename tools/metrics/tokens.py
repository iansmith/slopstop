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

    Every "/" **and every "."** is replaced with "-", so
    `/Users/iansmith/ticket-plugin` becomes `-Users-iansmith-ticket-plugin`
    and `~/mazzy/.claude/worktrees/x` becomes the doubled-dash
    `-Users-iansmith-mazzy--claude-worktrees-x`. The dot half matters because
    several repos in the fleet keep worktrees under a dotted directory, and a
    half-right encoder fails quietly rather than loudly: it names a directory
    that exists nowhere, so the ticket reports zero tokens.
    """
    return str(project_root).replace("/", "-").replace(".", "-")


def _worktree_dirs(root, ticket):
    suffix = f"-{ticket}"
    return [
        child
        for child in sorted(root.iterdir())
        if child.is_dir() and child.name.endswith(suffix)
    ]


def _select_source_dirs(root, ticket, project_dir):
    """The directories to read, and whether they need the time filter.

    Worktree dirs win outright and are attributed whole (no window); a project
    dir whose own name ends in `-<ticket>` is claimed by that arm. Failing
    those, exactly one directory can be the ticket's own project, so it is
    looked up by exact name -- a prefix match would also swallow a sibling
    project whose path extends this one's.
    """
    worktree_dirs = _worktree_dirs(root, ticket)
    if worktree_dirs:
        return worktree_dirs, False
    own_dir = root / project_dir
    return ([own_dir] if own_dir.is_dir() else []), True


def _window(record):
    """The `[started_at, completed_at]` bounds, or None if the record has none.

    Called only on the windowed arm, so a record with an unparseable
    `started_at` still survives worktree attribution untouched.
    """
    timing = record.get("timing")
    if not (timing and timing.get("started_at")):
        return None
    started = timing["started_at"]
    return _parse_ts(started), _parse_ts(timing.get("completed_at") or started)


def _in_scope(ts, windowed, window):
    if not windowed:
        return True
    return window is not None and window[0] <= ts <= window[1]


def _scan_dir(d, windowed, window):
    """`(timestamp, turn_index, entry)` for one dir's in-scope entries."""
    found = []
    for jsonl_path in sorted(d.glob("*.jsonl")):
        for idx, entry in enumerate(_usage_bearing_entries(jsonl_path)):
            ts = _parse_ts(entry["timestamp"])
            if _in_scope(ts, windowed, window):
                found.append((ts, idx, entry))
    return found


def _scan(source_dirs, windowed, window):
    """Candidates across every source dir, plus the dirs that contributed one.

    A dir earns its place in `transcript_dirs` by contributing at least one
    in-scope entry, not by merely being selected.
    """
    candidates = []
    transcript_dirs = []
    for d in source_dirs:
        found = _scan_dir(d, windowed, window)
        if found:
            candidates.extend(found)
            transcript_dirs.append(d.name)
    return candidates, transcript_dirs


def _session_position(candidates):
    if not candidates:
        return None
    _, turn_index, earliest_entry = min(candidates, key=lambda c: c[0])
    return {
        "entry_context_tokens": _entry_context_tokens(earliest_entry),
        "turn_index": turn_index,
    }


def collect(record, ctx):
    root = ctx["transcript_root"]
    # Subscript, never .get(): a default would silently restore the unscoped scan.
    project_dir = _project_dir_name(ctx["project_root"])

    if not root.is_dir():
        record["tokens"] = None
        return

    source_dirs, windowed = _select_source_dirs(root, record["ticket"], project_dir)
    window = _window(record) if windowed else None
    candidates, transcript_dirs = _scan(source_dirs, windowed, window)

    counted_entries = [entry for _, _, entry in candidates]
    input_tokens, cache_creation, output_tokens, cache_read = _sum_usage(
        counted_entries
    )

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
        "session_position": _session_position(candidates),
    }
