---
description: Push the current state of task_plan.md and findings.md to the ticket without archiving locally. Runs /slopstop:update first to checkpoint progress.md, then delegates the push to /slopstop:document. Idempotent — running twice with no changes is a no-op. Auto-detects ticket system.
disable-model-invocation: true
---

# /slopstop:update-ticket

Push the active ticket's local documentation (`task_plan.md`, `findings.md`) to the ticket system without ending the local lifecycle. A mid-flight sync: useful before a pairing session, at EOD checkpoints, or after major investigation milestones.

Sequence: checkpoint local state with `/slopstop:update`, then push to the ticket with `/slopstop:document`. No state transition. No local archive move.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd. Extract `key` and `system`. Set `$PREFIX` and `$SYSTEM` (`JIRA` | `Linear` | `GitHub`).

If `.project-conf.toml` is missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill runs unmodified — no interactive prompts. Safe to call from an autonomous pipeline for mid-flight syncs.

## Arguments and target ticket

- If `$ARGUMENTS` matches `^$PREFIX-\d+$`, use it as `$TICKET`. If it's another prefix, refuse: `"$ARGUMENTS doesn't match this project's prefix ($PREFIX)."`
- If `$ARGUMENTS` is empty, resolve `$TICKET` from the current git branch. If the branch doesn't encode a `$PREFIX-N` ticket: stop with the standard no-match error.
- Verify `~/.claude/ticket-active/$TICKET/` exists. If not:
  - If `~/.claude/ticket-archive/$TICKET/` exists → print `"$TICKET is already archived. Use /slopstop:document $TICKET to push from the archive copy."` and stop.
  - Otherwise → print `"$TICKET is not in-flight. Run :start $TICKET first."` and stop.
- Optional `--force` flag: pass through to `:document` to override divergence detection.

## Step 1 — Checkpoint with `/slopstop:update`

Invoke `/slopstop:update` against `$TICKET`. This captures current progress.md state (branch, HEAD, completed work, current state, next step) before the remote push.

If `:update` fails for any reason, stop and report the failure. Do NOT proceed to the remote push with a stale checkpoint.

## Step 2 — Detect ticket system

`.project-conf.toml`'s `system` field is authoritative. Run three ToolSearches in parallel to detect the backend. Resolve `$SYSTEM` from `.project-conf.toml`.

→ Read `~/.claude/commands/slopstop-archive-refs/archive-system-detection.md` for the ToolSearch queries and per-system backend resolution.

## Step 3 — Push documentation (delegate to `/slopstop:document`)

Execute `/slopstop:document` Steps 1–7 against `$TICKET`, reusing system context from Step 2.

Three artifacts are pushed:

| Local source | Ticket target |
|---|---|
| `task_plan.md` (whole body) | Ticket **description**, with prior original description preserved as `## Original description (preserved)` appendix |
| `task_plan.md`'s `## Definition of Done` section + evidence | Separate **comment** titled `## Definition of Done — Confirmation` |
| `findings.md` (if non-template) | Separate **comment** titled `## Findings (from local tracking)` |

- If `--force` was passed: pass `--force` through to `:document`.
- If divergence fires without `--force`: propagate the stop cleanly. Print the per-artifact diff. Do NOT touch local tracking.
- This step is **idempotent**: if local files match what's on the ticket, all artifacts classify as `unchanged` and `:document` skips the push. Running `:update-ticket` twice in a row with no local changes is a clean no-op.

## Step 4 — Confirm

```
Updated $TICKET on $SYSTEM.

Description:   <"updated (new)" | "already current — skipped" | "skipped (divergent — run with --force to override)">
DoD comment:   <"posted (new)" | "already current — skipped" | "skipped (no DoD section in task_plan.md)">
Findings:      <"posted (new)" | "already current — skipped" | "skipped (findings.md template-empty)">
Local:         ticket-active/$TICKET/ untouched
```

## Rules

- Does NOT archive. Does NOT transition ticket state. Does NOT touch local tracking files beyond the `:update` checkpoint.
- **Idempotent:** running twice without local changes is a no-op — `:document` handles this via artifact classification (`unchanged` → skip).
- No `--force` by default. Pass `--force` only to override a divergence stop.
- `progress.md` is updated by the `:update` checkpoint (Step 1) but is NOT pushed to the ticket (`:document` intentionally omits it).
- Failure handling:
  - System detection fails: error and stop. No state changed.
  - `:update` fails: stop before pushing. Local tracking unchanged beyond any partial progress.md write.
  - `:document` divergence without `--force`: stop with divergence diff; local tracking unchanged.
  - `:document` mid-push failure: print partial results; local tracking unchanged.
