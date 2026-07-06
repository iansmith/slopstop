# Plan: Monitor Loop Detail (Step 8 detail)

Run a background monitor using the `Monitor` tool with `persistent: true` and this polling script:

```bash
TICKET=$TICKET
STATE=$TRACKING_DIR/$TICKET/.agents.json
BASE_SHA=$BASE_SHA
HARD_STUCK_MIN=60     # minutes without commits AND repeating errors
TICK=900              # 15 min in seconds

while true; do
  now=$(date -u +%s)
  for agent_id in $(jq -r '.[] | select(.status=="running") | .id' "$STATE"); do
    worktree=$(jq -r --arg id "$agent_id" '.[] | select(.id==$id) | .worktree' "$STATE")
    branch=$(jq -r --arg id "$agent_id" '.[] | select(.id==$id) | .branch' "$STATE")
    task_id=$(jq -r --arg id "$agent_id" '.[] | select(.id==$id) | .task_id' "$STATE")
    started_at_epoch=$(date -u -d "$(jq -r --arg id "$agent_id" '.[] | select(.id==$id) | .started_at' "$STATE")" +%s 2>/dev/null || echo "$now")

    # Count commits the agent has made since fork point
    commits=$(git -C "$worktree" rev-list --count "$BASE_SHA..$branch" 2>/dev/null || echo 0)

    # Last commit timestamp (epoch); falls back to start time if no commits yet
    last_commit_epoch=$(git -C "$worktree" log -1 --format="%ct" "$branch" 2>/dev/null || echo "$started_at_epoch")
    minutes_since=$(( (now - last_commit_epoch) / 60 ))

    # Recent task output (last ~40 lines) via TaskOutput on the agent
    # The orchestrator should fetch this via the TaskOutput tool — outline only here
    # recent_output="<TaskOutput agent_id=$task_id lines=40>"

    # Detect repeating errors: same error line repeated >=3 times in the last 40 lines of output
    # repeating_errors=<count of repeated error pattern in recent_output>

    # Hard-stuck condition: BOTH must be true
    #   - minutes_since >= HARD_STUCK_MIN
    #   - repeating_errors >= 3
    # If either alone, surface a warning but DO NOT auto-stop.

    status_line="agent=$agent_id commits=$commits last_commit_min_ago=$minutes_since"

    if [ "$minutes_since" -ge "$HARD_STUCK_MIN" ]; then
      # Inspect recent_output for repeating errors before deciding to auto-stop
      # If hard-stuck: TaskStop on $task_id; update state; emit a clear notification
      status_line="$status_line [warn: no commits in ${minutes_since}min]"
    fi

    echo "$status_line"
  done

  sleep $TICK
done
```

## Auto-stop logic

Applied during each tick when evaluating a single agent:

- **Both conditions must hold:**
  1. The agent has gone 60+ minutes without a commit (`minutes_since_last_commit >= 60`).
  2. The agent's recent output (last ~40 lines) contains the same error message repeated 3+ times.
- If both true: call `TaskStop` on the agent's task_id. Update its state to `stopped` with `stop_reason: "auto-stop: <X>min no commits + repeating error '<excerpt>'"`. Emit a clear chat notification.
- If only one condition holds: emit a `[warn: ...]` flag in the status line but DO NOT auto-stop. Surface the warning so the user can intervene if they want.

## Completion detection

When the `Agent` tool emits its completion notification for a task (Claude Code does this automatically for background agents), the orchestrator updates that agent's state to `done` (or `errored` if the agent exited with an error) and stops monitoring it.

The monitor exits when all agents are in a terminal state (`done` | `stopped` | `errored`). Then continue to Step 9.
