# merge-autonomous.md — Autonomous behavior and [workflow] non-autonomous config

Used by `/slopstop:merge` for autonomous-mode decisions and non-autonomous workflow config.

## Invocation-scoped override

Autonomous mode for `:merge` is activated by the `--autonomous` flag on the command line, not by `[autonomous] enabled = true` in `.project-conf.toml`. This means:

- **Orchestrators** pass `--autonomous` explicitly when invoking `:merge` so they skip the confirm prompt.
- **Interactive sessions** never see `--autonomous` unless the user types it, so they always get the confirm prompt — even in repos with `[autonomous] enabled = true`.
- **Migration:** if your orchestrator relied on `enabled = true` to drive `:merge` autonomously, update its invocation to pass `--autonomous`. The other `[autonomous]` keys (`merge_strategy`, `merge_target_state`, `archive_immediately`, `metrics_emit_path`) are still read and respected when `--autonomous` is passed — only `enabled = true` is no longer the trigger.

**Cross-skill note:** `:pr`, `:start`, `:archive`, and `:plan` still gate on `[autonomous] enabled = true` (unchanged in this fix). Keep `enabled = true` in your config if those skills need it; pass `--autonomous` to `:merge` in addition.

## Autonomous behavior

Applies only when `--autonomous` is passed on the command line.

### Strategy selection (Arguments / Step 4)

If `--strategy` was NOT passed on the command line, and `[autonomous] merge_strategy` is set, use it as `$STRATEGY` without prompting. Valid values: `squash`, `merge`, `rebase`. Any other value: fall back to the default (`merge`) and log a warning.

### Confirmation skip (Step 3)

Skip the interactive `yes / no / merge-only` confirmation and proceed as if `yes` was given. Log the full plan that would have been shown:

```
[autonomous] Skipping confirmation. Merging $TICKET:
  PR:     #$PR ($BRANCH → $BASE) — $STRATEGY
  Ticket: $CURRENT_STATE → $COMPUTED_NEXT_STATE
```

If soft warnings are present (BLOCKED, BEHIND, failing checks, no review approval), log them but proceed.

### Forward-only guard (Step 5)

Before Step 5 applies the computed transition, a forward-direction check runs. Backward transitions are hard-stopped with a `[autonomous]` log line. Per-system: JIRA refuses category regressions (same-category advances are permitted); Linear refuses backward type-bucket or same-bucket lateral (same-position) moves; GitHub refuses `swap-labels` actions adding a negative-outcome label (`close-and-remove-label` 3-state closes are never refused). See `merge-execute-transition.md → Autonomous forward-only guard` for per-system rules and log format. If the guard refuses, the transition is not applied and the orchestrator must resolve the ticket state manually — the PR merge has already completed.

### Update tracking files — unconditional (Step 6)

In autonomous mode, always run `/slopstop:update` unconditionally against `$TICKET`. No staleness prompt, no skip option. This is the only sensible autonomous choice — there is no reason to skip updating progress.md before pushing docs to the ticket.

### Target state override (Step 2 / Step 5)

When `[autonomous] merge_target_state` is set, override the computed `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION`:

| Value | Effect |
|---|---|
| `auto` (default) | use the computed "advance one" target — no change from non-autonomous behavior |
| `done` | skip the "advance one" computation; target the workflow's first terminal/Done-type state directly. For JIRA: first transition whose target has `status.statusCategory.key === "done"` AND whose name does NOT match `/won.?t do\|cancel\|reject\|abandon\|invalid\|duplicate/i` (same exclusion filter as Step 2's normal computation). For Linear: first state with `type === "completed"` (same exclusion of `type === "canceled"` states as Step 2). For GitHub 3-state: `close-and-remove-label`. For GitHub 4-state: two-step — (a) execute the `swap-labels` action as normal (Step 5), then (b) additionally close the issue: MCP path `${GH_MCP_NS}update_issue(owner=$OWNER, repo=$REPO, issueNumber=$N, state="closed")`; CLI path `$GH issue close $N`. |
| `skip` | set `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION` to `null` — skip the transition entirely (same as `merge-only` but the branch cleanup still runs). |

### Automatic archive chain (Step 10 — after confirm)

When `[autonomous] archive_immediately = true` and the merge completes successfully (Step 4 returns `state: MERGED`), chain into `/slopstop:archive` **only if the post-transition state is terminal** — use the same classification Step 10 of the main spine uses. Two edge cases to handle explicitly: Linear `state.type === "canceled"` is terminal (same as `completed`); GitHub already-terminal tickets (branch C) have `$NEXT_GH_ACTION === null` and `state === "CLOSED"` — match on those conditions, not only on the `close-and-remove-label` transition kind. If the state is NOT terminal, skip the chain and log: `[autonomous] archive_immediately=true — skipping archive (ticket in intermediate state '<state>')`. When the state is terminal, log:

```
[autonomous] archive_immediately=true — chaining into :archive for $TICKET (state: <state>).
```

`:archive` is called as a Skill invocation. Note: `:archive` does not accept `--autonomous` — its non-interactive mode is triggered by `[autonomous] enabled = true` in `.project-conf.toml`. Orchestrators that migrated away from `enabled = true` must keep it set (or add `[workflow] skip_confirm = true`) to keep the archive chain non-interactive. If `:archive` fails (divergence stop, unexpected state, any other error), surface the error and do NOT retry. The merge is already done; `:archive` failure is not fatal to the overall run.

### Metrics emit (after Step 9)

After Step 9 completes (and after `:archive` if it ran — metrics emit runs regardless of `:archive` success or failure), if `[autonomous] metrics_emit_path` is set, merge the following fields into `<metrics_emit_path>/<TICKET>/pipeline.json`. If the file does not exist, create it with these fields plus `{"ticket": "$TICKET"}`.

```json
{
  "merge_strategy": "$STRATEGY",
  "completed_at": "<ISO timestamp>"
}
```

## [workflow] section — non-autonomous config

These keys live under a `[workflow]` table in `.project-conf.toml`. They apply in **interactive (non-autonomous)** sessions across multiple lifecycle skills. Autonomous mode has its own overrides under `[autonomous]` and ignores these.

| Key | Type | Default | Applies to | Effect |
|---|---|---|---|---|
| `skip_confirm` | bool | `false` | `:merge`, `:archive`, `:start` | `true` → skip the interactive confirm prompt in normal sessions; auto-proceed as `yes` and log the plan. For `:start`: when a branch-type heuristic suggestion is available, uses it without prompting; when no suggestion is available, still prompts. Has no effect on `:merge` when `--autonomous` is passed; has no effect on `:archive` and `:start` when `[autonomous] enabled = true` is set (autonomous mode already skips confirmations in both cases). |

Example `.project-conf.toml` addition:

```toml
[workflow]
skip_confirm = true   # auto-confirm merge and archive without interactive prompt
```

**When to use `skip_confirm = true`:** on projects where you always say `yes` and the confirmation adds friction without value — e.g. a personal project with no separate review/QA state, or a project where you run `:merge` and `:archive` repeatedly in a session.

**When NOT to use it:** any project with a multi-state workflow where you want to verify the computed next state before it executes, or where team members besides yourself might be merging.
