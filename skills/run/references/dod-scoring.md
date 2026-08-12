# DoD scoring — the one definition

Scoring a ticket's **Definition of Done** item by item. Read by two callers, which is
the whole point: `:run`'s stage-14 `close` gate, and the requirements adversary at
stage 10b handoff verification. One definition, so the two cannot disagree about
whether a ticket is done.

This file owns the verdict vocabulary and the evidence sources. It does **not** own
what a caller does with a verdict — `close` blocks, handoff verification reports —
nor any caller's own output format.

> **Both callers now live inside `:run`, and that is a narrowing, not a simplification.**
> Until the 4.0.0 mass deletion this file served `:merge`'s pre-merge gate and
> `:document`'s DoD-confirmation comment as well; both skills were deleted in `32ecb23`
> and `:run` absorbed their work inline. The shared-definition rule still binds — two
> readers scoring the same items at different points is exactly the disagreement this
> file exists to prevent — and it binds harder now that the two sit at opposite ends of
> the merge.

## Verdicts

Every item gets exactly one:

- `met` — the evidence shows the item is satisfied.
- `not-met` — the evidence shows it is not.
- `unverifiable` — the evidence needed to decide is not available at this calling
  point.
- `out-of-band` — the item carries the `(out-of-band)` marker from
  `ticket-standard.md` §3: no artifact can settle it, by design. **Report it once,
  naming what evidence is owed and from whom. Never re-score it, and never score it
  `not-met`.**

**`out-of-band` and `unverifiable` are not the same verdict and must not be merged.**
`unverifiable` says *the artifact should exist and I could not reach it* — a defect in
the evidence set or in the calling point, and loud on purpose. `out-of-band` says *no
artifact will ever exist, and the ticket said so at authoring time*. Collapsing them
turns a declared, accepted condition into a recurring failure.

That is not hypothetical. SOP-262 carried an unmarked item requiring a manual
end-to-end call; `"DoD item 8"` appears **19 times across 12 handoff rounds**, scored
`not-met` every time, correctly, by an adversary doing its job on an item that could not
be met. The marker is what stops that loop — and it only works if **both** scorers
honour it, which is why it is defined here and in `skills/adversary/SKILL.md` from one
source rather than twice.

**A ticket whose DoD is entirely `out-of-band` is a finding, not a pass.** Nothing
mechanical is being claimed at all, and that is a ticket-authoring defect for a human.

Never fake a confirmation. `unverifiable` is the honest answer when the artifact is
absent, and it is more useful than a `met` that does not hold up. It is **not** a
polite `met`: callers that gate treat it as failing (see the Callers table), because a
scorer reaching for the wrong evidence set produces `unverifiable` for everything, and
that must be loud rather than silent.

## Evidence-gathering sources (per DoD item)

**Which sources exist depends on when you are called.** This is the part that is easy
to get wrong: a scorer that assumes post-merge sources scores every pre-merge item
`unverifiable`, because `gh pr list --state merged` returns nothing before the merge.

### Pre-merge sources — the branch exists, the merge has not landed

Used by the requirements adversary at stage 10b. There is no merge commit and no
merged PR, so nothing below may depend on one.

**At 10b there is no PR either** — stage 11 opens it, one stage later. The adversary is
fed the worktree and the branch, per `handoff-verification.md`'s "Both are fed artifacts
only", so the diff below is a branch diff at that calling point. A scorer that reaches
for `$GH pr diff $PR` at 10b gets nothing and scores every code-anchored item
`unverifiable` — the same class of mistake as reaching for post-merge sources pre-merge,
one stage earlier.

- **The diff.** The code as it stands. An item asserting a file, symbol, or
  behavior exists is decided here. At 10b, the branch diff against the integration
  branch. Where a PR exists, `$GH pr diff $PR`, or
  `${GH_MCP_NS}pull_request_read(method="get_diff", …)` on the MCP backend.
- **The recorded test result.** The suite is run **locally** during the ticket's
  lifecycle and the outcome recorded in `run.jsonl` — typically the `implement` or
  `gates` span. That record is the artifact. Where a PR exists and the project also has
  CI running the same suite, the PR's check-run status (`statusCheckRollup`)
  corroborates it — do not re-fetch, and do **not** re-run the suite. Most projects
  have no such CI; treat its absence as normal, not as missing evidence.
- **The Phase 0 red-test commit.** Match the frozen red tests against DoD items. An
  item anchored to a named test is `met` when that test is green in the recorded run
  *and* was genuinely red at Phase 0.
- **Manual / observable verification.** `progress.md`'s `## Update` sections, for
  hands-on verification no artifact can show. `:run` seeds `$TRACKING_DIR/<TICKET>/` at
  stage 1 `intake`, so this is always available by the time either caller runs.

### Post-merge sources — once the PR is merged

Everything above, plus the two things that do not exist until the merge lands. A
caller reaches for these **only** when the PR is actually merged — which, of the two
callers, means stage 14 `close` alone. **The 10b adversary uses the pre-merge set and
nothing else**, and must not mark an item `unverifiable` merely because the merge has
not happened yet: at 10b it has not happened *by design*, three stages early.

- **Commits and merged PR.** `gh pr list --search "$TICKET" --state merged --json
  number,url,mergeCommit` for the merged PR and merge-commit SHA. `git log --grep
  "[$TICKET]" --oneline` for ticket-anchored commits. (When inlined by `:archive`
  after a merge, both are likely already in `progress.md`.)

## Scoring loop

For each item in the ticket's `## Definition of Done`:

1. Identify which stated artifact would settle it.
2. Look for that artifact in the evidence set for **this** calling point.
3. Record the verdict and the evidence that produced it — the file, test name, SHA, or
   `progress.md` line. A verdict with no recorded evidence is `unverifiable`, whatever
   you believe.

Score against what the ticket says, not against what the code does. An item the
implementation satisfies in spirit but not as written is `not-met`; the fix belongs in
the ticket, not in a generous reading.

### Where "the fix belongs in the ticket" lands

That rule prescribes a remedy — amend the ticket — and the remedy needs somewhere to go.
A ticket amended after a `not-met` is **re-scored**, not re-run: `:run`'s close stage has a
re-score path for exactly this state, and it is the only supported way back in. See
`:run`'s "Re-scoring after a ticket-defect `not-met`".

Two things that path guarantees, and that this file depends on:

- **Re-scoring reads the ticket as it is now.** An amended DoD is scored as amended, which
  is what makes amending the ticket a real remedy rather than a dead end.
- **The original `not-met` survives.** A re-score appends; it does not overwrite. A ticket
  that was fixed must not read as one that was always green — the pre-amendment verdict and
  the amendment that answered it are both part of what happened.

**None of this softens the rule above.** Scoring against what the ticket says stays correct,
and re-scoring is not a second, more generous pass over the same text — it is the same
scoring rule applied to text that changed. If the ticket did not change, neither does the
verdict.

## Callers

| Caller | When | Evidence set | On a non-`met` verdict |
|---|---|---|---|
| `:run` stage 10b | handoff verification, before the PR exists | pre-merge only | reported to the orchestrator with the rest of the charter |
| `:run` stage 14 | `close`, after stage 13 merged | pre-merge **and** post-merge | blocks: any `not-met` or `unverifiable` stops the ticket. **`out-of-band` does not block** — it is reported with what evidence is owed, and `[workflow] post_merge_done = false` is how such a ticket is parked rather than closed |

**Two callers, and the evidence column is why they are both listed.** They score the same
items from different sets — 10b has no PR and no merge commit, 14 has both — so an item
that is honestly `unverifiable` at 10b can be `met` at 14 without either scorer being
wrong. That is the disagreement this file exists to make legible rather than to hide.
