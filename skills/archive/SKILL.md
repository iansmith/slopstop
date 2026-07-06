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

## Step 3 — Re-harvest closed ticket into text DB (BILL-90)

Re-harvest the now-closed ticket into the `ticket_chunks` table so that
`/slopstop:search` returns the final description, DoD comment, and findings
rather than the stale `:start`-time snapshot.

**Config gate:** read `[hooks] text_harvest_on_merge` from `.project-conf.toml`
(default: `true`). If `false`, skip this step entirely.

**RAG health gate:** call `GET /healthz` on the RAG service. If the service is
unavailable or unhealthy, skip re-harvest and log:
`⚠️ RAG service unavailable — text DB re-harvest skipped for $TICKET`
Continue to Step 4. Never block archive on harvest failure.

**If healthy and enabled:**
- POST to the RAG service `/harvest/ticket` endpoint:
  ```json
  {"ticket_id": "$TICKET", "system": "$SYSTEM", "owner": "$OWNER", "repo": "$REPO"}
  ```
  For `$SYSTEM == "GitHub"`: `$OWNER` and `$REPO` = `pr-repo` if present, else parse from `key`.
  For JIRA/Linear: omit `owner` and `repo` from the payload.
- This is fire-and-forget: do not await confirmation that chunks are upserted.
  The POST is best-effort; the call is considered done when the request is sent.
- On any error from the POST (connection refused, non-2xx, timeout): log
  `⚠️ text DB re-harvest failed for $TICKET — ticket_chunks will be stale until manually re-harvested`
  and continue to Step 4. Harvest failure is **never fatal** to the archive.

## Step 4 — Archive locally

- `mv $TRACKING_DIR/$TICKET ~/.claude/ticket-archive/$TICKET`
- If destination already exists: rename to `~/.claude/ticket-archive/$TICKET-<timestamp>`. Don't lose history.

## Step 5 — Confirm

```
Archived $TICKET.

Text harvest:  <"triggered" | "skipped (text_harvest_on_merge=false)" | "skipped (RAG unavailable)" | "failed (stale — re-harvest manually)">
Local:         archived to ~/.claude/ticket-archive/$TICKET/
Undo:          mv ~/.claude/ticket-archive/$TICKET <resolved-$TRACKING_DIR>/$TICKET
```

## Rules

- This command does NOT transition the ticket-system state. Runs regardless of the ticket's current state on the ticket system.
- **File-lifecycle only.** Documentation push (:document) is handled by `:merge` before the archive chain runs. `:archive`'s role is: re-harvest (Step 3, conditional) + local `mv` (Step 4).
- **Text DB re-harvest (Step 3) is non-blocking.** Harvest failure logs a warning but never stops the archive or the local move. The ticket may be stale in the text corpus until someone manually triggers `/harvest/ticket` or re-runs `:archive`.
- After archive, future `/slopstop:start $TICKET` treats it as fresh-start.
- To resume an archived ticket without the reopen prompt: the undo command is shown in the Step 5 confirm output (resolved `$TRACKING_DIR` path substituted).
- Failure handling:
  - System detection fails: error and stop. No state changed.
  - Archive move fails: report and leave active dir in place. Re-run `:archive` — Step 4 retries the move.
  - Harvest failure (Step 3): log warning, continue to Step 4. Non-fatal.
