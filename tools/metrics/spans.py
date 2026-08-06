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

That premise holds only while `timing.started_at_source` is `label`. When it is
`issue_created` -- the fallback for a ticket that never carried the label -- window-open
is a filing time, not a work marker, so nothing is presumed to be running across it and
the carry-in is refused. See `collect()`.

Tool calls are attributed to whichever span contains them, by timestamp.

## What a duration is, and is not

Every duration here is **wall-clock**, and wall-clock includes the human. Measured on
BILL-434: a single `slopstop-plan` span runs 20:57 -> 09:41 and reports 45843 s (92% of
the ticket) -- someone went to bed. The number is not wrong, but it is trivially misread
as "planning took twelve hours", so the block carries `"measured_as": "wall-clock"`
rather than leaving the reader to infer it. Decomposing a span into human-idle / tool-execution /
model-inference is BILL-452's job, and #410's binding AMENDMENT 1 already measured one
interactive ticket at 92% human idle.

`unattributed_seconds` is **structurally 0 whenever a skill straddles window-open**, which
is the common case: `:start` always does, so its span is clipped to `window[0]` and the
tiling covers everything. It is non-zero when the first skill of a ticket begins *after*
the label event -- a ticket sat on before work started -- and on any ticket whose
`started_at_source` is `issue_created`, where no carry-in is admitted at all. Reported
anyway, because a remainder that exists and is hidden is the failure this module is
trying to avoid; but do not read a 0 as "fully explained".
"""

import json
import re

import tokens

# Bash commands worth naming individually. These are the gates: the test runs (`:plan`
# 0b, `:pr` Steps 2/2f), the complexity gate (0c) and the tamper diff (2d). Ordered --
# first match wins, so a more specific pattern must precede a more general one.
TOOL_KINDS = (
    ("pytest", ("pytest", "go test", "npm test")),
    ("lizard", ("lizard",)),
    ("git-diff", ("git diff", "git show", "git log")),
)

# A needle only counts where a command could actually start: beginning of the string,
# after a shell separator (`;`, `&&`, `||`, `|`, newline, `(`), or after `-m` -- with an
# optional path in front, so `/Users/x/.local/bin/lizard --csv` still matches, and an
# optional `<tool> run` in front, so the fleet's non-Python repos keep their
# `poetry run pytest` / `uv run pytest` form. `run` is spelled out rather than allowing
# any leading word, because that is what keeps `pip install lizard`, `command -v lizard`
# and `python3 -c "import lizard"` out.
#
# Bare `needle in command` fabricated gates. A slopstop Bash call is routinely a compound
# one-liner carrying a heredoc, so the needle lands in *content* as often as in a command:
# measured across 16 tickets, 40 of 460 attributed calls (8.7%) matched text that never
# ran -- a 40.6 s `pytest` for `re.split(r"\n(?=def test_|@pytest)")` that edited a file,
# a 4.8 s `git-diff` for a DoD checklist line writing "`git diff` touches no repo other
# than this one" into a document, seven `lizard` gates that were `pip install lizard`.
# The duration attached is the whole compound command's wall time, so a fabricated call
# carries a fabricated measurement -- the failure this module refuses everywhere else.
_COMMAND_POSITION = re.compile(
    r"(?:^|[\n;&|(]|\s-m)\s*(?:[\w./~-]+\s+run\s+)?[\w./~-]*$"
)


def _at_command_position(command, needle):
    """Does `needle` appear in `command` somewhere a command could begin?"""
    return any(
        _COMMAND_POSITION.search(command[: match.start()])
        for match in re.finditer(re.escape(needle), command)
    )


def _classify(command):
    """The gate a Bash command belongs to, or None if it is not a gate."""
    if not command:
        return None
    for kind, needles in TOOL_KINDS:
        if any(_at_command_position(command, needle) for needle in needles):
            return kind
    return None


def _tool_uses(path):
    """`(timestamp, name, input, result_timestamp)` per tool_use in one transcript.

    A tool_result block carries the `tool_use_id` of the call it answers, so the entry
    timestamp of the message holding it is when that call returned. Both halves live in
    the same session file, so one pass over the file pairs them. `result_timestamp` is
    None when the transcript holds no result for a call -- a session that ended while
    the tool was still running, or an interrupted call.
    """
    out = []
    results = {}
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
                kind = block.get("type")
                if kind == "tool_use":
                    out.append(
                        (stamp, block.get("name"), block.get("input") or {}, block.get("id"))
                    )
                elif kind == "tool_result":
                    # First result wins: a retried/duplicated result block would
                    # otherwise stretch the call to whenever the last copy was written.
                    results.setdefault(block.get("tool_use_id"), stamp)
    return [(stamp, name, payload, results.get(uid)) for stamp, name, payload, uid in out]


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


def _elapsed(started, result_stamp):
    """Seconds from a tool_use to its tool_result, or 0.0 when that is not derivable.

    0.0 stands for "no result recorded for this call", not for a measured zero. It is
    used rather than None because a null here would propagate into arithmetic downstream
    (#452 decomposes these), and because a call with no result has no honest duration to
    report. A result timestamp that precedes its own call means the clock disagreed with
    itself; clamped for the same reason `unattributed_seconds` is.
    """
    finished = _moment(result_stamp) if result_stamp else None
    if finished is None:
        return 0.0
    return max(0.0, round((finished - started).total_seconds(), 3))


def _collect_events(source_dirs, window):
    """Skill invocations and gate tool calls inside `window`, each sorted by time."""
    skills, tools = [], []
    for directory in source_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            for stamp, name, payload, result_stamp in _tool_uses(path):
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
                        tools.append(
                            (
                                moment,
                                kind,
                                payload.get("command"),
                                _elapsed(moment, result_stamp),
                            )
                        )
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

    for moment, kind, command, elapsed in tools:
        for span in built:
            if span["_start"] <= moment <= span["_end"]:
                span["tools"].append(
                    {
                        "kind": kind,
                        "started_at": _iso(moment),
                        "duration_seconds": elapsed,
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
    # The carry-in has one stated premise, and it is conditional: `:start` applies the
    # `status:in-progress` label *during its own run*, so the skill that opens the ticket
    # begins seconds before the window it creates. When `started_at_source` is
    # `issue_created` -- no such label event ever fired -- that premise is simply absent.
    # window[0] is then when somebody *filed* the ticket, which makes no claim that any
    # skill was running, and the last skill before it can be arbitrarily old and
    # unrelated. Live on BILL-435 (window opens 10:40:29 on 2026-08-05, source
    # `issue_created`): the carried-in invocation was `forkprobe`, last seen 09:41:46 --
    # 58 minutes earlier -- and it was handed the 257 s up to the ticket's real first
    # skill, with `unattributed_seconds: 0`. Same fabrication the BILL-433 guard below
    # rejects, just partial rather than total, and unbounded in general: a ticket filed
    # days before work starts hands those days to a skill from before it existed.
    if timing.get("started_at_source") != "label":
        skills = [item for item in skills if item[0] >= window[0]]
    # `skills` is otherwise unfiltered so _build() can carry in the invocation that
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
        # Named `measured_as` rather than `basis`: charter R5 bans a `basis` key outright
        # (it exists to stop a `usd_basis` caveat reappearing on pricing) and
        # conftest.FORBIDDEN_KEY_PATTERN enforces it across the whole record. The ban is
        # blunt by design and it caught this on the first run.
        "measured_as": "wall-clock",
        "skills": built,
        "attributed_seconds": round(attributed, 3),
        "unattributed_seconds": remainder,
    }
