# Merge: Summary and Next-Step Recommendation (Step 9 detail)

Print the summary block, then exactly **one** `Next step:` block.

## Summary block

```
Shipped $TICKET.

PR:      #$PR merged ($STRATEGY, $MERGE_COMMIT) into $baseRefName
Ticket:  $TICKET advanced from '<old state>' to '<new state>' on $SYSTEM
         ( or "already terminal — no transition needed" / "no forward transition available" / "unchanged (merge-only)" )
Docs:    <"description updated, DoD posted, findings posted" | "already current — skipped" | "failed: <reason>" | "skipped (skip_archive=true) — posted commit-id comment">
Remotes: $baseRefName pushed to <list of non-$ORIGIN_REMOTE remotes>
         ( or "$ORIGIN_REMOTE only" / "skipped (merge-only)" )
Branch:  <"worktree removed + local branch dropped" | "local branch dropped" | "not found locally — skipped">; remote feature branch deleted at merge
         ( or "untouched (merge-only)" )
Local:   $TRACKING_DIR/$TICKET/ untouched (see archive result below for terminal-state tickets)
```

In **adopt mode**, the `PR:` line must say `already merged <mergedAt> — adopted`, not a
strategy. The operator must never come away believing `:merge` merged something it did not.

## Terminal-state classification

Computed from the **post-transition** state, using data Step 2 already fetched — no new
ticket-system call:

- **JIRA:** the new state's status-category key is `"done"`.
- **Linear:** the new state's `type` is `"completed"` or `"canceled"`.
- **GitHub:** depends on the workflow shape recorded in Step 2.
  - **3-state** (`$NEXT_GH_ACTION.kind === "close-and-remove-label"`): after Step 5 the issue is CLOSED → **terminal** → branch **A**.
  - **4-state** (`$NEXT_GH_ACTION.kind === "swap-labels"`): after Step 5 the issue is OPEN with `$IN_REVIEW_LABEL` → **NOT terminal** → branch **B**.

## The five `Next step:` blocks — print exactly one

- **A — advanced into terminal state:** `✅ Ticket is now in '<new state>' — terminal. Archive will run automatically (Step 10).` (if `skip_archive == true`: `✅ Ticket is now in '<new state>' — terminal. Archive skipped ([workflow] skip_archive=true).`)
- **B — advanced into intermediate state:** `⚠️ Ticket is now in '<new state>' — NOT terminal. Wait for QA sign-off, then run /slopstop:archive manually.`
- **C — already terminal before merge:** `✅ Ticket was already in '<state>' (terminal). Archive will run automatically (Step 10).` (if `skip_archive == true`: `✅ Ticket was already in '<state>' (terminal). Archive skipped ([workflow] skip_archive=true).`)
- **D — no forward transition available:** `⏸ No forward transition available — ticket stays in '<state>'. Run /slopstop:archive manually once the ticket reaches a terminal state (transition manually first).`
- **E — merge-only path:** `⏸ Ticket state NOT advanced (merge-only). Run /slopstop:archive manually once the ticket reaches a terminal state.`

Branches **A** and **C** are the only ones that reach Step 10.
