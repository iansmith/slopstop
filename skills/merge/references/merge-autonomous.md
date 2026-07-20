# merge-autonomous.md — Autonomous behavior and [workflow] non-autonomous config

Used by `/slopstop:merge` for autonomous-mode decisions and non-autonomous workflow config.

## Trigger

Autonomous mode for `:merge` is activated by either of:

- `[autonomous] enabled = true` in `.project-conf.toml` — the same trigger `:start`, `:pr`, `:archive`, and `:plan` use. This is the normal way to make `:merge` autonomous for a project.
- `--autonomous` passed on the command line for a single invocation — an explicit override for forcing autonomous mode on a one-off call even when `enabled = true` is not set (e.g. an orchestrator invoking `:merge` against a project it doesn't otherwise control the config for).

Either trigger enables the same behavior below. The `[autonomous]` keys (`merge_strategy`, `merge_target_state`, `metrics_emit_path`) are read and respected whenever autonomous mode is active, regardless of which trigger activated it.

**Cross-skill note:** `:pr`, `:start`, `:archive`, and `:plan` gate on `[autonomous] enabled = true` only (no CLI flag). `:merge` now matches that as its primary trigger too, with `--autonomous` as an additional per-invocation override that the other skills don't have.

## Autonomous behavior

Applies whenever autonomous mode is active — `[autonomous] enabled = true` in config, or the `--autonomous` flag for a single invocation (see **Trigger** above).

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

### Automatic archive chain (Step 10)

No autonomous-specific override here — Step 10 of the main spine (inline `:archive` for branches A/C, the post-transition state is terminal) applies unchanged in autonomous mode. It already forces the chained `:archive` call to skip its own confirm prompt regardless of project config, so no separate `[workflow] skip_confirm` handling is needed here either. If `:archive` fails (divergence stop, unexpected state, any other error), surface the error and do NOT retry. The merge is already done; `:archive` failure is not fatal to the overall run.

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
| `skip_confirm` | bool | `false` | `:merge`, `:archive`, `:start` | `true` → skip the interactive confirm prompt in normal sessions; auto-proceed as `yes` and log the plan. For `:start`: when a branch-type heuristic suggestion is available, uses it without prompting; when no suggestion is available, still prompts. Has no effect on `:merge`, `:archive`, or `:start` when autonomous mode is already active (`[autonomous] enabled = true`, or for `:merge` also `--autonomous`) — autonomous mode already skips confirmations. |

Example `.project-conf.toml` addition:

```toml
[workflow]
skip_confirm = true   # auto-confirm merge and archive without interactive prompt
```

**When to use `skip_confirm = true`:** on projects where you always say `yes` and the confirmation adds friction without value — e.g. a personal project with no separate review/QA state, or a project where you run `:merge` and `:archive` repeatedly in a session.

**When NOT to use it:** any project with a multi-state workflow where you want to verify the computed next state before it executes, or where team members besides yourself might be merging.
