---
description: "End the local lifecycle for a ticket: move the local tracking dir from `$TRACKING_DIR/` to `~/.claude/ticket-archive/`. Documentation push (:document) is handled by :merge before archive runs. Does NOT support --force."
disable-model-invocation: true
---

# /slopstop:archive

End the local lifecycle for a ticket: move the local tracking dir to `~/.claude/ticket-archive/`. Documentation push is handled by `:merge` before the archive chain runs. Auto-detects ticket system.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Extract `key` and `system`. Set `$PREFIX` and `$SYSTEM` (`JIRA` | `Linear` | `GitHub`).

Also read `tracking_dir` (optional): resolve to `$TRACKING_DIR`. If absent or equal to `~/.claude/ticket-active`, default to `~/.claude/ticket-active`. If a relative path (no leading `/` or `~/`), resolve from `dirname "$(git rev-parse --git-common-dir)"`. Absolute paths (starting with `/` or `~/`) are used as-is.

For the **GitHub backend**, also read `pr-repo` (optional): `$OWNER` and `$REPO` = `pr-repo` if present, else parse from `key`.

If `.project-conf.toml` is missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill runs unmodified — no interactive prompts. Safe to call from an autonomous pipeline after `:merge` when `archive_immediately = true`.

## Arguments and target ticket

- If `$ARGUMENTS` matches `^$PREFIX-\d+$`, use it as `$TICKET`. If it's another prefix, refuse: `"$ARGUMENTS doesn't match this project's prefix ($PREFIX)."`
- If `$ARGUMENTS` is empty, resolve `$TICKET` from the current git branch. If the branch doesn't encode a `$PREFIX-N` ticket: stop with the standard no-match error.
- Verify `$TRACKING_DIR/$TICKET/` exists. If not:
  - If `~/.claude/ticket-archive/$TICKET/` exists → print `"Archive already completed — $TICKET."` and stop.
  - Otherwise → print `"$TICKET is not in-flight. Run :start $TICKET first."` and stop.

## Step 1 — Detect ticket system

`.project-conf.toml`'s `system` field is authoritative. Run three ToolSearches in parallel to detect the backend. Resolve `$SYSTEM` from `.project-conf.toml`.

→ Read `~/.claude/commands/slopstop-archive-refs/archive-system-detection.md` for the ToolSearch queries and per-system backend resolution.

**Empty-tracking edge case:** if all three tracking files are template-empty:
- With `skip_confirm = true` or `[autonomous] enabled = true`: proceed as `yes` and log `[archive] Empty tracking detected — archiving anyway (no content to push).`
- Otherwise, ask: `"Tracking is empty — really archive $TICKET? Will move the local dir to ticket-archive with no content. (yes / no)"`
  - `yes`: proceed.
  - `no`: print `Archive cancelled.` and stop.

## Step 2 — Confirm with the user

**Auto-confirm check:** Read `.project-conf.toml` for `[workflow] skip_confirm`. If `skip_confirm = true` and autonomous mode is NOT active, skip the interactive prompt and proceed as `yes`. Log the plan:

```
[workflow.skip_confirm=true] Auto-confirming archive of $TICKET.
  mv $TRACKING_DIR/$TICKET/ → ~/.claude/ticket-archive/$TICKET/
```

The empty-tracking edge case still applies even with `skip_confirm = true`.

If `skip_confirm` is absent or `false`:
→ Read `~/.claude/commands/slopstop-archive-refs/archive-confirm-prompt.md` for the interactive prompt text and yes/no handling.

## Step 3 — Archive locally

- `mv $TRACKING_DIR/$TICKET ~/.claude/ticket-archive/$TICKET`
- If destination already exists: rename to `~/.claude/ticket-archive/$TICKET-<timestamp>`. Don't lose history.

## Step 4 — Confirm

```
Archived $TICKET.

Local:         archived to ~/.claude/ticket-archive/$TICKET/
Undo:          mv ~/.claude/ticket-archive/$TICKET <resolved-$TRACKING_DIR>/$TICKET
```

## Rules

- This command does NOT transition the ticket-system state. Runs regardless of the ticket's current state on the ticket system.
- **File-lifecycle only.** Documentation push (:document) is handled by `:merge` before the archive chain runs. `:archive`'s role is: local `mv` (Step 3).
- After archive, future `/slopstop:start $TICKET` treats it as fresh-start.
- To resume an archived ticket without the reopen prompt: the undo command is shown in the Step 4 confirm output (resolved `$TRACKING_DIR` path substituted).
- Failure handling:
  - System detection fails: error and stop. No state changed.
  - Archive move fails: report and leave active dir in place. Re-run `:archive` — Step 3 retries the move.
