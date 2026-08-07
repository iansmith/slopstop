#!/usr/bin/env python3
"""Append subagent facts to `.slopstop/metrics/hook-events.jsonl`. Deterministic recorder.

Wired to SubagentStart, SubagentStop and StopFailure. Reads the hook payload as JSON on stdin
and appends one line per event. It decides nothing and blocks nothing.

WHY A HOOK AND NOT PROSE (BILL-496).  BILL-494 had the orchestrator write these facts itself.
Anthropic's guidance is that a prompted rule "can fail to follow" under pressure or in a long
session, and PLTF-2563 is the proof: the `implement` span opened and never closed, so the run's
own verdict was "no timing numbers may be derived from this file". This runs in code, so there
is no instruction to skip.

WHY NOT PostToolUse -- MEASURED, NOT ASSUMED.  On PLTF-2563 the `tool_use`->`tool_result`
interval matched the real subagent duration for 6 of 8 launches within ~5s, and was wrong by
557s and 257s for the other two: `slop-check` and `complexity-check`, the parallel gates, which
return immediately with an agentId while the agent keeps running. Right 75% of the time and
wrong by 500x on a structural subset is worse than uniformly broken -- a naive total reports
every fan-out stage as free. SubagentStop fires when the subagent actually finishes.

WHAT THIS CANNOT SEE.  The model. No subagent hook carries it; only SessionStart has an
optional `model` field the docs call "not guaranteed to be present", and there is no
$CLAUDE_MODEL. That is why `derive.py` still reads the transcript -- these two are
complementary, not alternatives.

NEVER FAILS A RUN.  Configured `async: true`, and every path here exits 0. A recorder that can
break the thing it measures is worse than no recorder, so a bad payload, an unwritable
directory or an unexpected schema all end the same way: silently, exit 0.
"""

import datetime
import json
import os
import pathlib
import sys

# Fields worth keeping. `effort` and `agent_type` together are the fallback check: agent_type is
# the carrier that was requested (slopstop-effort-medium), effort is what actually applied, so a
# silent fall back to general-purpose shows up as a disagreement rather than as nothing.
KEEP = ("hook_event_name", "session_id", "prompt_id", "agent_id", "agent_type",
        "effort", "stop_reason", "error_type", "cwd", "permission_mode",
        # `agent_transcript_path` closes the one gap this recorder was said to have. The model
        # is not in any hook payload, but the child transcript IS -- and the payload hands over
        # its path, so derive.py can read the model directly instead of matching launches to
        # children by time. Found by recording `payload_keys` on the first real event rather
        # than by reading the docs, which do not list it.
        "agent_transcript_path", "transcript_path")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                      # unparseable stdin is not this script's problem

    cwd = pathlib.Path(payload.get("cwd") or os.getcwd())
    # Inert outside a slopstop project. The hook is installed once at user level and therefore
    # fires in EVERY project; the presence of .slopstop/ is what scopes it. Do not create the
    # directory -- creating state in an unrelated repo is exactly the surprise to avoid.
    root = next((p for p in (cwd, *cwd.parents) if (p / ".slopstop").is_dir()), None)
    if root is None:
        return 0

    rec = {k: payload[k] for k in KEEP if k in payload}
    # `effort` arrives as {"level": "..."} on some events and as a bare string on others.
    if isinstance(rec.get("effort"), dict):
        rec["effort"] = rec["effort"].get("level")
    rec["at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec["source"] = "hook"
    # The raw payload keys are kept so a field we did not anticipate is still recoverable from
    # the record rather than lost. Names only -- values could be large.
    rec["payload_keys"] = sorted(payload)

    try:
        out = root / ".slopstop" / "metrics"
        out.mkdir(parents=True, exist_ok=True)
        with (out / "hook-events.jsonl").open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        return 0                      # never let a recorder break a run
    return 0


if __name__ == "__main__":
    sys.exit(main())
