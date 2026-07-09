# Run: Monitoring Loop (Step 5 detail)

The orchestrator's guard against agents that are stuck, looping, or out of bounds
(`design/slopstop-process.md` §7c). Every threshold is a `[fleet.monitoring]` key —
policy knobs, not constants.

## The poll (every `poll_interval_min`, default 5)

For each live agent, gather two signals and update `fleet-state.md`:

1. **Ticket comments** — new markers since the last poll (the reporting protocol:
   one comment per slopstop command + per material work unit).
2. **Worktree activity** — `git -C <worktree> status --porcelain` and recent file
   mtimes (`find <worktree> -newer <last-poll-stamp> -not -path '*/.git/*'`).

Schedule the next wake-up rather than busy-waiting; on every wake-up, re-read
`fleet-state.md` from disk before acting (the file, not memory, is the truth).

## The four triggers — exactly as configured

| Trigger | Condition | Action |
|---|---|---|
| **quiet** | no new ticket comment for `quiet_investigate_min` (default 15) | **Investigate, don't kill:** peek the worktree. Activity without comments = a healthy-but-silent agent — note it in fleet-state; do not kill on quiet alone. |
| **silence** | no new comments **AND** no worktree activity for `silence_kill_min` (default 30) | **Kill.** Both signals dead is the definition of stuck. |
| **loop** | the same failure reported in `loop_kill_reports` (default 3) consecutive markers with no new approach | **Kill.** More repetition will not converge. |
| **file-map violation** | worktree changed-files vs the recorded fork SHA — `git -C <worktree> diff --name-only <fork SHA>`, which catches committed **and** uncommitted writes (agents commit as they go, so `git status --porcelain` alone would miss committed out-of-map files) — contain a path outside the ticket's file map; directory-granular entries cover their subtree; `$TRACKING_DIR` writes are exempt (sanctioned carve-out) | `filemap_violation = "kill"`: **instant kill**, no grace period — this check is mechanical (path-prefix comparison), no model judgment. `"warn"`: log the violation in fleet-state and the ticket, let the agent continue — use while evaluating small models, then flip to `"kill"`. |

The asymmetry is deliberate: an agent writing where it was fenced out is doing damage
in the wrong place (instant, mechanical); a quiet agent might just be thinking
(patient, two-stage).

Also watch for the **`TICKET UNDERSPECIFIED:`** final line — that is not a kill or a
failure: route it to Step 7's rewrite path with **no attempt consumed**.

## The kill procedure

1. Terminate the agent's background session (the pid/task id recorded at launch).
2. Record in `fleet-state.md`: reason (`silence` / `loop` / `filemap: <path>`),
   timestamp, attempt number now consumed.
3. Post a one-line kill marker on the ticket (the audit trail lives with the work).
4. **Preserve the worktree** — never clean it on a kill; the next attempt resumes
   there with the kill reason and any prior findings cited in its brief (a retry
   without new information is a wasted attempt).
5. Relaunch is Step 7's decision (budgets, diagnosis, escalation) — monitoring only
   detects and kills; it never decides what happens next beyond recording.

Kills surface in reports (umbrella/final/G4 ledgers) — no human is interrupted, ever:
the human sees kills in the ledger, not as questions.
