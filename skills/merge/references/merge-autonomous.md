# merge-autonomous.md — Autonomous behavior and [workflow] non-autonomous config

Used by `/slopstop:merge` for autonomous-mode decisions and non-autonomous workflow config.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

### Strategy selection (Arguments / Step 4)

If `--strategy` was NOT passed on the command line, and `[autonomous] merge_strategy` is set, use it as `$STRATEGY` without prompting. Valid values: `squash`, `merge`, `rebase`. Any other value: fall back to the default (`merge`) and log a warning.

### Confirmation skip (Step 3)

In autonomous mode, skip the interactive `yes / no / merge-only` confirmation and proceed as if `yes` was given. Log the full plan that would have been shown:

```
[autonomous] Skipping confirmation. Merging $TICKET:
  PR:     #$PR ($BRANCH → $BASE) — $STRATEGY
  Ticket: $CURRENT_STATE → $COMPUTED_NEXT_STATE
```

If soft warnings are present (BLOCKED, BEHIND, failing checks, no review approval), log them but proceed.

### Target state override (Step 2 / Step 5)

When `[autonomous] merge_target_state` is set, override the computed `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION`:

| Value | Effect |
|---|---|
| `auto` (default) | use the computed "advance one" target — no change from non-autonomous behavior |
| `done` | skip the "advance one" computation; target the workflow's first terminal/Done-type state directly. For JIRA: first transition whose target has `status.statusCategory.key === "done"` AND whose name does NOT match `/won.?t do\|cancel\|reject\|abandon\|invalid\|duplicate/i` (same exclusion filter as Step 2's normal computation). For Linear: first state with `type === "completed"` (same exclusion of `type === "canceled"` states as Step 2). For GitHub 3-state: `close-and-remove-label`. For GitHub 4-state: two-step — (a) execute the `swap-labels` action as normal (Step 5), then (b) additionally close the issue: MCP path `${GH_MCP_NS}update_issue(owner=$OWNER, repo=$REPO, issueNumber=$N, state="closed")`; CLI path `$GH issue close $N`. |
| `skip` | set `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION` to `null` — skip the transition entirely (same as `merge-only` but the branch cleanup still runs). |

### Automatic archive chain (Step 7 + after)

When `[autonomous] archive_immediately = true` and the merge completes successfully (Step 4 returns `state: MERGED`), chain into `/slopstop:archive` immediately after Step 7. Log:

```
[autonomous] archive_immediately=true — chaining into :archive for $TICKET.
```

`:archive` is called as a Skill invocation, not a separate shell command, so it inherits the same session context. If `:archive` fails (ticket not in a terminal state on the system, divergence stop, etc.), surface the error and do NOT retry. The merge is already done; `:archive` failure is not fatal to the overall run.

> **Prerequisite:** `:archive` enforces a hard terminal-state gate — it refuses if the ticket is not in a terminal state (JIRA `status.statusCategory.key === "done"`, Linear `type === "completed"`, GitHub `state === "CLOSED"`). For `archive_immediately = true` to succeed, the ticket must land in a terminal state after the merge. **Pair with `merge_target_state = "done"`**, or use a 3-state GitHub workflow where the merge closes the issue automatically. With `merge_target_state = "auto"` on a 4-state workflow (where the ticket lands in "In Review"), `:archive` will refuse on every merge — this is logged but non-fatal, and the local tracking dir will not be archived.

### Metrics emit (Step 7)

After Step 7 completes (and after `:archive` if it ran — metrics emit runs regardless of `:archive` success or failure), if `[autonomous] metrics_emit_path` is set, merge the following fields into `<metrics_emit_path>/<TICKET>/pipeline.json`. If the file does not exist, create it with these fields plus `{"ticket": "$TICKET"}`.

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
| `skip_confirm` | bool | `false` | `:merge`, `:archive` | `true` → skip Step 3 interactive prompts in normal sessions; auto-proceed as `yes` and log the plan. Has no effect when `[autonomous] enabled = true` (autonomous mode already skips confirmations). |

Example `.project-conf.toml` addition:

```toml
[workflow]
skip_confirm = true   # auto-confirm merge and archive without interactive prompt
```

**When to use `skip_confirm = true`:** on projects where you always say `yes` and the confirmation adds friction without value — e.g. a personal project with no separate review/QA state, or a project where you run `:merge` and `:archive` repeatedly in a session.

**When NOT to use it:** any project with a multi-state workflow where you want to verify the computed next state before it executes, or where team members besides yourself might be merging.
