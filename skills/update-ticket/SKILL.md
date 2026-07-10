---
description: Push the current state of task_plan.md and findings.md to the ticket without archiving locally. Runs /slopstop:update first to checkpoint progress.md, then delegates the push to /slopstop:document. Idempotent — running twice with no changes is a no-op. Auto-detects ticket system.
disable-model-invocation: true
---

# /slopstop:update-ticket

Push the active ticket's local documentation (`task_plan.md`, `findings.md`) to the ticket system without ending the local lifecycle. A mid-flight sync: useful before a pairing session, at EOD checkpoints, or after major investigation milestones.

Sequence: checkpoint local state with `/slopstop:update`, then push to the ticket with `/slopstop:document`. No state transition. No local archive move.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd. Extract `$PREFIX` (`prefix` field), `system`, and `key` (for reference). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Set `$SYSTEM` (`JIRA` | `Linear` | `GitHub`).

Also read `tracking_dir` (optional): resolve to `$TRACKING_DIR`. If absent or equal to `~/.claude/ticket-active`, default to `~/.claude/ticket-active`. If a relative path (no leading `/` or `~/`), resolve from `dirname "$(git rev-parse --git-common-dir)"`. Absolute paths (starting with `/` or `~/`) are used as-is. **Guard:** if the resolved path lies under `~/.claude/`, warn `"tracking_dir resolves under ~/.claude, a protected path — headless agents cannot write there even with a matching --add-dir. Set a project-local path (e.g. \".slopstop/ticket-active\")."` and continue. The legacy default works interactively; it silently breaks fleet agents.

Also read `archive_dir` (optional): resolve to `$ARCHIVE_DIR` by the same rules; absent defaults to `~/.claude/ticket-archive`.

If `.project-conf.toml` is missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill runs unmodified — no interactive prompts. Safe to call from an autonomous pipeline for mid-flight syncs.

## Arguments and target ticket

- If `$ARGUMENTS` matches `^$PREFIX-\d+$`, use it as `$TICKET`. If it's another prefix, refuse: `"$ARGUMENTS doesn't match this project's prefix ($PREFIX)."`
- If `$ARGUMENTS` is empty, resolve `$TICKET` from the current git branch. If the branch doesn't encode a `$PREFIX-N` ticket: stop with the standard no-match error.
- Verify `$TRACKING_DIR/$TICKET/` exists. If not:
  - If `$ARCHIVE_DIR/$TICKET/` exists → print `"$TICKET is already archived. Use /slopstop:document $TICKET to push from the archive copy."` and stop.
  - Otherwise → print `"$TICKET is not in-flight. Run :start $TICKET first."` and stop.
- Optional `--force` flag: pass through to `:document` to override divergence detection.

## Step 1 — Checkpoint with `/slopstop:update`

Invoke `/slopstop:update` against `$TICKET`. This captures current progress.md state (branch, HEAD, completed work, current state, next step) before the remote push.

If `:update` fails for any reason, stop and report the failure. Do NOT proceed to the remote push with a stale checkpoint.

## Step 2 — Detect ticket system

`.project-conf.toml`'s `system` field is authoritative. Run three ToolSearches in parallel to detect the backend. Resolve `$SYSTEM` from `.project-conf.toml`.

→ Read `~/.claude/commands/slopstop-archive-refs/archive-system-detection.md` for the ToolSearch queries and per-system backend resolution.

## Step 3 — Push documentation (delegate to `/slopstop:document`)

Execute `/slopstop:document` Steps 1–7 against `$TICKET`. Pass `--force` if provided. If `:document` stops (divergence stop or mid-push failure), propagate the stop and do NOT touch local tracking. This step is idempotent — `:document` skips already-current artifacts automatically.

## Step 4 — Confirm

```
Updated $TICKET on $SYSTEM.

Description:   <"updated (new)" | "already current — skipped" | "skipped (divergent — run with --force to override)">
DoD comment:   <"posted (new)" | "already current — skipped" | "skipped (no DoD section in task_plan.md)" | "posted (--force overrode divergent; old comment left on ticket)">
Findings:      <"posted (new)" | "already current — skipped" | "skipped (findings.md template-empty)" | "posted (--force overrode divergent; old comment left on ticket)">
Local:         $TRACKING_DIR/$TICKET/ untouched
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
