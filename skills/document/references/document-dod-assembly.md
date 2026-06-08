# DoD-confirmation comment — assembly template

Build the expected comment body as:

```
## Definition of Done — Confirmation (<UTC ISO 8601 timestamp>)

Confirming each DoD item from the agreed plan against the work delivered:

<for each DoD item in task_plan.md's ## Definition of Done section:>
  ✅ **<item restated from task_plan.md>**
     Evidence: <test name(s) passing, commit SHA(s), PR link, manual verification note from progress.md if any>

  <OR if evidence is missing:>
  ⚠️ **<item>** — Could not confirm.
     Reason: <why — e.g., "no red test was written for this behavior" or "manual verification step still pending">
     What this means: <what the client should know>

Confirmed at: <UTC timestamp, ISO 8601>
```

## Evidence-gathering sources (per DoD item)

- **Phase 0 red test status:** if `task_plan.md` has a `**Test command:**` line, run it (or rely on the most recent test result in `progress.md` — typically a `## /slopstop:pr` or `## Implementation` section). Match red-test names against DoD items to confirm green.
- **Commits and PR:** `gh pr list --search "$TICKET" --state merged --json number,url,mergeCommit` for the merged PR + merge commit SHA. `git log --grep "[$TICKET]" --oneline` for ticket-anchored commits. (When inlined by `:archive` after a merge, the merge commit and PR URL are likely in `progress.md` already.)
- **Manual / observable verification:** read `progress.md` for `## Update` sections documenting hands-on verification.

Never fake a confirmation. If evidence isn't there, use ⚠️ and explain plainly. A ⚠️ item is more honest than a ✅ that doesn't hold up.

Set `$EXPECTED_DOD` to the assembled comment body. Note the `Confirmed at:` timestamp line — Step 4b strips it before comparison so pure timestamp changes are treated as `unchanged`.
