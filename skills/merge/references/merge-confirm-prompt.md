# merge-confirm-prompt.md — Step 3 interactive confirmation

Read this only on the **interactive** path — i.e. autonomous mode is NOT active
(`[autonomous] enabled = true` not set and `--autonomous` was NOT passed) and
`[workflow] skip_confirm` is not `true`. Every fleet merge and every `skip_confirm` merge
skips this file entirely; the spine's two-line skip check is all those paths need.

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
