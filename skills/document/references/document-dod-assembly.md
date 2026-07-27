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

## Scoring each item

Score every DoD item with the shared scorer — `:document` is a **post-merge** caller,
so it gets the full evidence set including the merge commit, the merged PR, and
`progress.md`:
→ Read `~/.claude/commands/slopstop-run-refs/dod-scoring.md`

Render its three verdicts into this comment's two states:

- `met` → ✅
- `not-met` → ⚠️, `Reason:` naming what the evidence showed
- `unverifiable` → ⚠️, `Reason:` naming which artifact was missing

Both non-`met` verdicts render ⚠️, so the `Reason:` line is the only thing separating
"we checked and it failed" from "we could not check". Never omit it.

Never fake a confirmation. If evidence isn't there, use ⚠️ and explain plainly. A ⚠️ item is more honest than a ✅ that doesn't hold up.

Set `$EXPECTED_DOD` to the assembled comment body. Note the `Confirmed at:` timestamp line — Step 4b strips it before comparison so pure timestamp changes are treated as `unchanged`.
