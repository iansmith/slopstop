# Plan: Final Report and Merge Detail (Steps 9–10 detail)

## Step 9 — Final report and auto-merge (with confirmation)

When all agents are in a terminal state, print the full report:

```
$TICKET — agent fanout complete.

agent-1 (<name>):   status: done       commits: 7   worktree: <path>   branch: <branch>
agent-2 (<name>):   status: done       commits: 4   worktree: <path>   branch: <branch>
agent-3 (<name>):   status: stopped    commits: 2   worktree: <path>   branch: <branch>
                       reason: auto-stop: 62min no commits + repeating "X not found" error
...
```

### 9a. Offer auto-merge

Build the merge order from the Plan's dependency graph (Step 2's "Depends on" fields):

```
Auto-merge agents' work back into $BRANCH?

Merge order (by dependencies):
  1. agent-1 (no deps)
  2. agent-2 (no deps)
  3. agent-4 (depends on agent-1)
  ...

For each: git merge --no-ff <agent-branch> -m "[$TICKET] merge <agent-id>: <summary>".
Stops on first conflict; you resolve manually from there.

  - merge all                → run merges in order
  - merge specific <list>    → merge only the listed agents (e.g. "merge specific 1,2,4")
  - skip                     → print the manual recipe and stop
  - abort                    → no merge
```

### 9b. Execute the merge (if user opts in)

For `merge all` or `merge specific <list>`:

1. `git switch $BRANCH` (back to the user's working branch).
2. For each selected agent branch in dependency order:
   - `git merge --no-ff <agent-branch> -m "[$TICKET] merge <agent-id>: <summary from agent's work>"`.
   - If conflict: stop the merge sequence. Print:
     ```
     Conflict merging <agent-branch>. Resolve and commit manually:

       <list of conflicted files>

     After resolving:
       git add <files>
       git commit
       <remaining merge commands to run>
     ```
   - If clean: continue to next.
3. After all selected merges land cleanly: print:
   ```
   Merged <J> agent branches into $BRANCH.
   New HEAD: <sha> <subject>

   You can clean up agent worktrees with:
     git worktree remove <worktree-path>
   (or leave them in place to inspect later).
   ```

For `skip`: print the manual recipe (the same git commands you'd otherwise run) and stop.
For `abort`: print "No merge performed. Agent branches preserved at <list of paths>." and stop.

## Step 10 — Final confirm

```
Plan + execution complete for $TICKET.

Plan:          <N> work items, <K> parallelized
Investigation: appended to findings.md
Agents:        <K launched, M completed, X auto-stopped, Y errored>
Integration:   <"auto-merged <J> branches, HEAD now at <sha>" | "manual integration left to you" | "no agents launched">
Adversary:     <"N gap tests added (RED verified)" | "no gaps found" | "skipped (--no-adversary)" | "skipped (user chose skip)" | "skipped (autonomous on_test_gaps=skip)">

Next: /slopstop:pr to open a PR for review.
```
