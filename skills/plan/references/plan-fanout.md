# Plan: Fanout Preconditions, Confirm, and Launch (Steps 4, 6, 7 detail)

Everything between "the plan says parallel" and "agents are running". Step 5's prompt
template is separate (`plan-agent-prompt.md`), as is the monitor loop
(`plan-monitor-loop.md`).

## Step 4 — Pre-conditions for parallel fanout

Three hard gates before anything creates a worktree.

### 4a. Clean working tree

`git status --porcelain`. If non-empty, offer three choices:

- `commit` — create a WIP checkpoint commit, **re-capture `$BASE_SHA`**, continue.
  (Re-capturing matters: the recorded fork point must be the commit the agents
  actually branch from, or every later diff is computed against a base that never
  existed in their worktrees.)
- `stash` — `git stash push --include-untracked -m "$TICKET pre-fanout"`, and remind
  the user to pop it after. **`--include-untracked` is required, not optional:** the
  4a gate is `git status --porcelain`, which reports untracked files as `??`, but a
  bare `git stash push` does not stash them — so the gate would fire, the stash would
  "succeed", and the tree would still be dirty. Re-run `git status --porcelain` after
  stashing and only proceed when it is empty; if entries remain, abort rather than
  fanning out.
- `abort` — stop. The plan is already saved.

If the commit fails, print the hook output and abort the fanout. Never `--no-verify`.

### 4b. Confirm the fork point

Ask: `"Agents will fork from $BRANCH @ $BASE_SHA in isolated worktrees. Is this the
right base? (yes / abort)"` On `abort`: stop.

### 4c. Agent count cap

If the plan recommends more than 4 parallel agents, offer: `merge` (combine items into
≤4 units), `proceed` (run all K), or `abort`.

## Step 6 — Confirm and launch

**Step 5 runs between 4c and here** — this file covers 4, 6 and 7, but not 5, and Step 7
cannot launch anything without the per-agent prompts Step 5 drafts
(`plan-agent-prompt.md`). If you arrived here straight from Step 4, go draft them first.

Present the full plan plus the per-agent decomposition: ticket, item count, per-agent
name / files / done-when summary, and the fork point. **One confirmation for the entire
fanout:**

- `yes` — create worktrees, launch agents, monitor. Continue to Step 7.
- `save-only` — plan saved; the user executes manually. Stop.
- `abort` — stop. The plan is still saved.

## Step 7 — Launch agents

For each parallel item, spawn a background worktree agent:

```
Agent(subagent_type: "general-purpose", isolation: "worktree", run_in_background: true,
      description: "Agent <id> on $TICKET", prompt: <per-agent prompt from Step 5>)
```

`isolation: "worktree"` is the **enforcement mechanism**, not a description of intent —
without it the agents share one checkout and overwrite each other.

Capture each agent's task ID and resolved worktree path. Record state in
`$TRACKING_DIR/$TICKET/.agents.json` with fields: `id`, `task_id`, `worktree`,
`branch`, `items`, `status` (`running`), `started_at`, `last_check_at`,
`last_commit_at`, `commits`, `stop_reason`.

Print the launch confirmation with each agent's worktree path, branch, and task ID.

If a launch fails: stop, and mark already-spawned agents as `orphan` in the state file
— an unrecorded running agent is one nobody will ever collect or kill.
