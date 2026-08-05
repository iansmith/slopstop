"""Skill and tool spans derived from the session transcript (BILL-406).

`timing` resolves a ticket to one number and `phases` to marker granularity, which is
per slopstop *command*, not per gate. That leaves the expensive part of a ticket as one
opaque block: measured on BILL-382, writing the code was 76 s of a 2263 s span (3%) while
a single unattributed stretch was 1549 s (68%).

This is a collector change, not a process change -- it adds no instruction an agent could
skip, so charter R1 (no skill emits a metrics record) is untouched.

## How a span is bounded

A `Skill` tool_use's matching tool_result arrives in well under 5 s: that is the skill
*text loading*, not the skill running. (Probed 2026-08-05 -- 0.02-4.43 s across a real
session. The same trap as an `Agent` spawn, whose tool_result is a 2.7 s launch
acknowledgement for work that ran 82 s.) So a skill's span runs from its own tool_use to
the **next** skill's tool_use, and the last one to the ticket's `completed_at`.

That choice is what makes the spans contiguous, and contiguity is what lets the
sum-plus-remainder identity exist: every second inside the ticket window is either
attributed to a skill or reported as remainder. A remainder that is *reported* is data
("68% is in a block we cannot name yet"); one that is silently dropped would make the
attributed slice look like the whole ticket.

Spans are selected by **interval overlap**, not by containment, and then clipped to the
window. That is not a nicety: `timing.started_at` derives from the `status:in-progress`
label event, and `:start` applies that label *during its own run* -- so the skill that
opens a ticket always begins a few seconds before the window it creates. Measured on
BILL-382: `slopstop-start` fired at 08:11:54 against a window opening at 08:12:19, and a
containment filter dropped it. Every ticket has this blind spot, and it always hides the
same skill. Taking the last skill still running at window-open, clipped, fixes it without
inflating the total.

Tool calls are attributed to whichever span contains them, by timestamp.

## What a duration is, and is not

Every duration here is **wall-clock**, and wall-clock includes the human. Measured on
BILL-434: a single `slopstop-plan` span runs 20:57 -> 09:41 and reports 45843 s (92% of
the ticket) -- someone went to bed. The number is not wrong, but it is trivially misread
as "planning took twelve hours", so the block carries `"basis": "wall-clock"` rather than
leaving the reader to infer it. Decomposing a span into human-idle / tool-execution /
model-inference is BILL-452's job, and #410's binding AMENDMENT 1 already measured one
interactive ticket at 92% human idle.

`unattributed_seconds` is **structurally 0 whenever a skill straddles window-open**, which
is the common case: `:start` always does, so its span is clipped to `window[0]` and the
tiling covers everything. It is non-zero only when the first skill of a ticket begins
*after* the label event -- a ticket sat on before work started. Reported anyway, because a
remainder that exists and is hidden is the failure this module is trying to avoid; but do
not read a 0 as "fully explained".
"""

import json

import tokens

# Bash commands worth naming individually. These are the gates: the test runs (`:plan`
# 0b, `:pr` Steps 2/2f), the complexity gate (0c) and the tamper diff (2d). Ordered --
# first match wins, so a more specific pattern must precede a more general one.
TOOL_KINDS = (
    ("pytest", ("pytest", "go test", "npm test")),
    ("lizard", ("lizard",)),
    ("git-diff", ("git diff", "git show", "git log")),
)


def _classify(command):
    """The gate a Bash command belongs to, or None if it is not a gate."""
    if not command:
        return None
    for kind, needles in TOOL_KINDS:
        if any(needle in command for needle in needles):
            return kind
    return None


def _tool_uses(path):
    """`(timestamp, name, input)` for every tool_use entry in one transcript."""
    out = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            stamp = entry.get("timestamp")
            content = (entry.get("message") or {}).get("content")
            if not stamp or not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") == "tool_use":
                    out.append((stamp, block.get("name"), block.get("input") or {}))
    return out


def _moment(stamp):
    """`stamp` as a datetime, or None if it is not a parseable timestamp.

    `tokens._parse_ts` raises rather than returning None, so calling it bare made the
    `is None` check below dead code: one unparseable timestamp anywhere in the scanned
    transcripts aborted the whole record with a traceback instead of skipping the entry.
    `_tool_uses` already skips lines that fail to parse as JSON; this is the same posture
    one field down.
    """
    try:
        return tokens._parse_ts(stamp)
    except (AttributeError, TypeError, ValueError):
        return None


def _collect_events(source_dirs, window):
    """Skill invocations and gate tool calls inside `window`, each sorted by time."""
    skills, tools = [], []
    for directory in source_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            for stamp, name, payload in _tool_uses(path):
                moment = _moment(stamp)
                if moment is None:
                    continue
                if name == "Skill":
                    # Deliberately unfiltered here -- selection is by overlap in
                    # _build(), which needs the invocation that preceded the window.
                    skill = payload.get("skill")
                    if skill:
                        skills.append((moment, skill))
                    continue
                if not (window[0] <= moment <= window[1]):
                    continue
                if name == "Bash":
                    kind = _classify(payload.get("command"))
                    if kind:
                        tools.append((moment, kind, payload.get("command")))
    skills.sort(key=lambda item: item[0])
    tools.sort(key=lambda item: item[0])
    return skills, tools


def _iso(moment):
    return moment.isoformat().replace("+00:00", "Z")


def _build(skills, tools, window):
    """Contiguous skill spans, each carrying the gate calls that fall inside it."""
    built = []
    for index, (started, name) in enumerate(skills):
        ended = skills[index + 1][0] if index + 1 < len(skills) else window[1]
        if ended < started:
            ended = started
        # Overlap, then clip. A span wholly outside the window contributes nothing; one
        # straddling window-open contributes only its in-window seconds, so the tiling
        # stays exact and the sum identity holds.
        if ended < window[0] or started > window[1]:
            continue
        started = max(started, window[0])
        ended = min(ended, window[1])
        built.append(
            {
                "name": name,
                "started_at": _iso(started),
                "ended_at": _iso(ended),
                "duration_seconds": round((ended - started).total_seconds(), 3),
                "_start": started,
                "_end": ended,
                "tools": [],
            }
        )

    for moment, kind, command in tools:
        for span in built:
            if span["_start"] <= moment <= span["_end"]:
                span["tools"].append(
                    {
                        "kind": kind,
                        "started_at": _iso(moment),
                        # A Bash tool_result is not reliably paired to its tool_use in
                        # this scan, so a call's own duration is not derivable yet; 0 is
                        # the honest placeholder rather than a guess. Its *position* is
                        # the useful part today -- which gate ran, inside which skill.
                        "duration_seconds": 0,
                        "command": (command or "")[:120],
                    }
                )
                break

    for span in built:
        del span["_start"]
        del span["_end"]
    return built


def collect(record, ctx):
    timing = record.get("timing")
    if not timing or not timing.get("started_at"):
        record["spans"] = None
        return

    # An unclosed ticket has no `completed_at`, so `_window` degenerates to a single
    # instant. Attributing against that yields a zero-duration span for work still in
    # flight -- worse than silence, because a 0 s span reads as a measurement. Found on
    # BILL-140, whose one archive invocation landed exactly on the boundary.
    if timing.get("span_seconds") is None:
        record["spans"] = None
        return

    window = tokens._window(record)
    if window is None:
        record["spans"] = None
        return

    root = ctx["transcript_root"]
    # The same guard `tokens.collect` opens with, and for the same reason:
    # `_select_source_dirs` calls `root.iterdir()`, which raises FileNotFoundError on a
    # HOME that has no `~/.claude/projects` (a fresh machine, a CI runner, a service
    # account). `collect.py` wraps no collector in a try, so that traceback aborts the
    # whole record -- spawns, active, markers and signals never run and nothing is
    # printed -- while `tokens` next door degrades to null on the identical input.
    # Behavior 4 asks for the absence, not the crash.
    if not root.is_dir():
        record["spans"] = None
        return

    project_dir = tokens._project_dir_name(ctx["project_root"])
    source_dirs, _ = tokens._select_source_dirs(root, record["ticket"], project_dir)

    skills, tools = _collect_events(source_dirs, window)
    # `skills` is deliberately unfiltered so _build() can carry in the invocation that
    # straddles window-open -- but a carried-in skill is evidence of work only when some
    # skill actually ran *inside* the window. Without this check the contiguity rule
    # charges an entire inter-session gap to whichever skill last ran before it: BILL-433
    # (window 13:48:47-14:08:44 on 2026-08-05, no Skill call inside it) reported its full
    # 1197 s as one `slopstop-merge` span that had in fact ended two hours earlier, with
    # `unattributed_seconds: 0`. Testing the unfiltered list could not see that, and a
    # fabricated 100% reads as a measurement -- the same failure behavior 4 rejects for
    # a zero-second span.
    if not any(window[0] <= moment <= window[1] for moment, _ in skills):
        record["spans"] = None
        return

    built = _build(skills, tools, window)
    attributed = sum(span["duration_seconds"] for span in built)
    total = timing.get("span_seconds") or 0
    # Time before the first skill invocation, plus any drift. Clamped at zero: a window
    # shorter than its own spans would mean the clock disagreed with itself, and a
    # negative remainder reads as "we found more time than existed".
    remainder = max(0.0, round(total - attributed, 3))

    record["spans"] = {
        # Durations include human idle -- see the module docstring. #452 decomposes.
        "basis": "wall-clock",
        "skills": built,
        "attributed_seconds": round(attributed, 3),
        "unattributed_seconds": remainder,
    }
