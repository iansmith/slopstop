# Branch type — the one definition

Picks the Conventional-Commits prefix for a ticket's branch: `<type>/<TICKET>`.

**There is no config key for this.** `[autonomous].branch_type` was removed 2026-08-06 —
it was a knob for a decision that should just be made, and its failure mode was a hard stop
when the heuristic found nothing. Renaming a branch is trivial; stalling a run is not.

**Never ask the user.** This resolves to an answer every time, on its own.

## Three tiers — first sufficient tier wins

### Tier 1 — labels, then title

Cheapest signal, and usually enough. **A label match beats a title match.** When several
labels match different types, prefer in this order:

`fix` > `feat` > `refactor` > `perf` > `docs` > `chore` > `test`

| Label signal | Type |
|---|---|
| `bug`, `regression`, `hotfix`, `defect` | `fix` |
| `feature`, `enhancement`, `story` | `feat` |
| `chore`, `maintenance`, `cleanup`, `tech-debt`, `tech debt` | `chore` |
| `docs`, `documentation` | `docs` |
| `refactor`, `refactoring` | `refactor` |
| `perf`, `performance` | `perf` |
| `test`, `testing`, `qa` | `test` |

| Title pattern | Type |
|---|---|
| Starts with `Fix `, `Bug:`, `Regression:`, or contains ` bug ` | `fix` |
| Starts with `Add `, `Implement `, `Build `, `Create `, `New ` | `feat` |
| Starts with `Refactor `, `Cleanup `, `Rename ` | `refactor` |
| Contains `documentation`, `README`, or `docs` (whole word) | `docs` |

### Tier 2 — the ticket body

Only when tier 1 produced nothing, or produced a genuine tie you cannot break. Read the
ticket's description and judge what the work *is*:

- Repairing behavior that is specified and wrong → `fix`
- Building behavior that does not exist yet → `feat`
- Changing structure with no behavior change → `refactor`
- Making existing behavior faster or cheaper → `perf`
- Only prose, comments, or documentation files → `docs`
- Only tests → `test`
- Dependency bumps, config, tooling, housekeeping → `chore`

This is a judgment call on evidence you have already read for other reasons — it costs
nothing extra.

### Tier 3 — `unk`

**If tier 2 leaves you genuinely uncertain, use `unk`. Do not guess, and do not stop.**

`unk` is a real, valid answer, not a failure. A branch named `unk/BILL-412` is renamed with
one command, and being wrong about the prefix costs nothing — the ticket key is what
carries meaning. Confabulating `feat` for something you could not classify is worse than
`unk`, because it looks decided.

## Validation

Whatever tier answers, the result must pass `git check-ref-format` as a branch-name
component. `unk` always does. If a tier-2 judgment produces something that does not, fall
to `unk` rather than sanitizing it into a different word.
