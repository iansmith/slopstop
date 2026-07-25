# merge-confirm-prompt.md — Step 3 confirmation, both paths

The **interactive** plan-and-approve flow is below. Autonomous mode has its own log format
in `merge-autonomous.md` → Confirmation skip. The third path, `[workflow] skip_confirm`,
emits this and proceeds as `yes`:

```
[workflow.skip_confirm=true] Auto-confirming merge of $TICKET.
  PR:     #$PR ($BRANCH → $BASE) — $STRATEGY
  Ticket: $CURRENT_STATE → $COMPUTED_NEXT_STATE
  <soft-warning lines if any>
```

In adopt mode the `PR:` line's `— $STRATEGY` becomes `— already merged <mergedAt> —
adopting`, since no merge will be performed. Note this block is **not** the autonomous
one: that has a different prefix line, so a session must not substitute one for the other.

Everything below applies only to the **interactive** path — autonomous mode is NOT active
(`[autonomous] enabled = true` not set and `--autonomous` was NOT passed) and
`[workflow] skip_confirm` is not `true`.

## Show the plan and get explicit approval

**Adopt mode (`$ADOPT == true`, PR already merged — spine Step 1d):** open with
`About to finish $TICKET — its PR is already merged, so NO merge will be performed:`
and replace item 1 with:

> 1. **Adopt** PR #$PR (`$BRANCH` → `$baseRefName`), merged $mergedAt as `$MERGE_COMMIT`. Nothing is merged now; the remaining steps bring $TICKET to the end state it should already have.

Items 2–3 and everything below are unchanged (item 3's `state: MERGED` precondition is
already satisfied, and its cleanup tolerates a remote branch the original merge deleted).
Drop the soft-warning line — those describe merge-readiness, which is moot. The `merge-only`
answer still means "stop after item 1", which in adopt mode is a no-op that changes nothing.

> About to merge $TICKET and ship the code:
>
> 1. **Merge** PR #$PR (`$BRANCH` → `$baseRefName`) with strategy `$STRATEGY`, then delete the remote feature branch.
> 2. **Advance** $TICKET on $SYSTEM by one state: `<current state name>` → `<computed next state name>`. (Or `"<current> — already terminal, no transition needed"` / `"<current> — no forward transition available on this workflow"` if applicable.) This is one step forward, NOT auto-Done. If the workflow's next state isn't what you expected, say `no` and handle it manually.
> 3. **Switch to `$baseRefName`, pull the merge from $ORIGIN_REMOTE, push it to any other remotes** (mirrors / forks / upstream — if `git remote` lists anything besides `$ORIGIN_REMOTE`), then **remove the agent worktree or delete the local branch** `$BRANCH` as appropriate (only after the merge is confirmed `state: MERGED`).
>
> After merge: tracking files updated (:update, Step 6) then pushed to ticket (:document, Step 7). For terminal-state tickets, archive (file move only) runs automatically (Step 10).
>
> <soft-warning summary if any: BLOCKED / BEHIND / failing checks / no review approval>
>
> Proceed? (yes / no / merge-only)

## Answers

- `yes`: all three steps.
- `merge-only`: merge only (step 1). No ticket transition, no non-$ORIGIN_REMOTE pushes, no branch deletion.
- `no`: stop. No state changed.

If any soft warnings were present, append: `"Note the warnings above — confirming will proceed anyway."`
