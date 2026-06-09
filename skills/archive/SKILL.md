---
description: End the local lifecycle for a ticket. Delegates the documentation push to /slopstop:document (description body + DoD-confirmation comment + findings comment, with idempotent skip-when-current and divergence-stop safety), then mv the local tracking dir to ~/.claude/ticket-archive/. Does NOT support --force — if the documentation push would overwrite a divergent managed version on the ticket, archive stops cleanly; the user runs /slopstop:document --force separately to overwrite (after eyeballing the diff), then re-runs :archive. Auto-detects ticket system.
disable-model-invocation: true
---

# /slopstop:archive

End the local lifecycle for a ticket: delegate documentation push to `/slopstop:document`, then move the local tracking dir to `~/.claude/ticket-archive/`. Auto-detects ticket system.

`:archive`'s job is the *lifecycle* (local archive); the *content push* lives in `/slopstop:document`. See `skills/document/SKILL.md` for the full per-artifact classification, divergence detection, DoD-evidence gathering, and description-appendix logic.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd. Extract `key` and `system`. Set `$PREFIX` and `$SYSTEM` (`JIRA` | `Linear` | `GitHub`).

If `.project-conf.toml` is missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill runs unmodified — no interactive prompts. Safe to call from an autonomous pipeline after `:merge` when `archive_immediately = true`.

## Arguments and target ticket

- If `$ARGUMENTS` matches `^$PREFIX-\d+$`, use it as `$TICKET`. If it's another prefix, refuse: `"$ARGUMENTS doesn't match this project's prefix ($PREFIX)."`
- If `$ARGUMENTS` is empty, resolve `$TICKET` from the current git branch. If the branch doesn't encode a `$PREFIX-N` ticket: stop with the standard no-match error.
- Verify `~/.claude/ticket-active/$TICKET/` exists. If not:
  - If `~/.claude/ticket-archive/$TICKET/` exists → print `"Archive already completed — $TICKET."` and stop.
  - Otherwise → print `"$TICKET is not in-flight. Run :start $TICKET first."` and stop.

## Step 1 — Detect ticket system

`.project-conf.toml`'s `system` field is authoritative. Run three ToolSearches in parallel to detect the backend. Resolve `$SYSTEM` from `.project-conf.toml`.

→ Read `~/.claude/commands/slopstop-archive-refs/archive-system-detection.md` for the ToolSearch queries and per-system backend resolution.

**Empty-tracking edge case:** if all three tracking files are template-empty:
- With `skip_confirm = true` or `[autonomous] enabled = true`: proceed as `yes` and log `[archive] Empty tracking detected — proceeding with empty plan push.`
- Otherwise, ask: `"Tracking is empty — really archive $TICKET? Will push an empty plan and skip the findings comment. (yes / no)"`
  - `yes`: proceed.
  - `no`: print `Archive cancelled.` and stop.

## Step 2 — Confirm with the user

**Auto-confirm check:** Read `.project-conf.toml` for `[workflow] skip_confirm`. If `skip_confirm = true` and autonomous mode is NOT active, skip the interactive prompt and proceed as `yes`. Log the plan:

```
[workflow.skip_confirm=true] Auto-confirming archive of $TICKET.
  Push documentation to $SYSTEM (description + DoD comment + findings).
  mv ~/.claude/ticket-active/$TICKET/ → ~/.claude/ticket-archive/$TICKET/
```

The empty-tracking edge case still applies even with `skip_confirm = true`.

If `skip_confirm` is absent or `false`:
→ Read `~/.claude/commands/slopstop-archive-refs/archive-confirm-prompt.md` for the interactive prompt text and yes/no/skip-push handling.

## Step 3 — Push documentation (delegate to `/slopstop:document`)

Skip entirely if user picked `skip-push` in Step 2.

Execute `/slopstop:document` Steps 1–7 against `$TICKET`. No `--force`, no `--dry-run`. If divergence stops the push, archive propagates the stop: print the per-artifact diff, skip Steps 3.5 and 4, append the re-run instructions, and exit cleanly.

## Step 3.5 — Re-harvest closed ticket into text DB (BILL-90)

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
  where `$OWNER` and `$REPO` are parsed from `.project-conf.toml`'s `key` field.
- This is fire-and-forget: do not await confirmation that chunks are upserted.
  The POST is best-effort; the call is considered done when the request is sent.
- On any error from the POST (connection refused, non-2xx, timeout): log
  `⚠️ text DB re-harvest failed for $TICKET — ticket_chunks will be stale until manually re-harvested`
  and continue to Step 4. Harvest failure is **never fatal** to the archive.

## Step 4 — Archive locally

- `mv ~/.claude/ticket-active/$TICKET ~/.claude/ticket-archive/$TICKET`
- If destination already exists: rename to `~/.claude/ticket-archive/$TICKET-<timestamp>`. Don't lose history.

## Step 5 — Confirm

```
Archived $TICKET on $SYSTEM.

Description:   <"updated (new)" | "already current — skipped" | "skipped (skip-push selected)">
DoD comment:   <"posted (new)" | "already current — skipped" | "skipped (no DoD section in task_plan.md)" | "skipped (skip-push selected)">
Findings:      <"posted (new)" | "already current — skipped" | "skipped (findings.md template-empty)" | "skipped (skip-push selected)">
Text harvest:  <"triggered" | "skipped (text_harvest_on_merge=false)" | "skipped (RAG unavailable)" | "skipped (push not completed)" | "failed (stale — re-harvest manually)">
Local:         archived to ~/.claude/ticket-archive/$TICKET/
```

## Rules

- This command does NOT transition the ticket-system state. Runs regardless of the ticket's current state on the ticket system.
- **Delegates the documentation push to `/slopstop:document`** (Step 3). All push-side logic lives in `:document`; `:archive` adds the local-tracking move (Step 4) and text DB re-harvest (Step 3.5).
- **No `--force` support.** If divergence fires, `:archive` stops without touching local tracking. Run `/slopstop:document --force` separately (after eyeballing the diff), then re-run `:archive`.
- **Text DB re-harvest (Step 3.5) is non-blocking.** Harvest failure logs a warning but never stops the archive or the local move. The ticket may be stale in the text corpus until someone manually triggers `/harvest/ticket` or re-runs `:archive`.
- After archive, future `/slopstop:start $TICKET` treats it as fresh-start.
- To resume an archived ticket without the reopen prompt: manually `mv ~/.claude/ticket-archive/$TICKET ~/.claude/ticket-active/` first.
- Failure handling:
  - System detection fails: error and stop. No state changed.
  - `:document` reports divergence: print per-artifact diff, skip Steps 3.5 and 4, exit cleanly. Local tracking unchanged.
  - `:document` mid-push failure: skip Steps 3.5 and 4 — half-published remote state without local archive lets the user retry without losing the active tracking dir.
  - Archive move fails (after all pushes succeeded): report and leave active dir in place. Re-run `:archive` — Step 3's idempotency makes the push a no-op and Step 4 retries the move.
  - Harvest failure (Step 3.5): log warning, continue to Step 4. Non-fatal.
