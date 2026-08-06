# DoD scoring — the one definition

Scoring a ticket's **Definition of Done** item by item. Read by three callers, which
is the whole point: `:merge`'s pre-merge gate, `:run`'s requirements adversary, and
`:document`'s DoD-confirmation comment. One definition, so the three cannot disagree
about whether a ticket is done.

This file owns the verdict vocabulary and the evidence sources. It does **not** own
what a caller does with a verdict — `:merge` blocks, `:run` reports, `:document`
renders — nor any caller's own output format.

## Verdicts

Every item gets exactly one:

- `met` — the evidence shows the item is satisfied.
- `not-met` — the evidence shows it is not.
- `unverifiable` — the evidence needed to decide is not available at this calling
  point.

Never fake a confirmation. `unverifiable` is the honest answer when the artifact is
absent, and it is more useful than a `met` that does not hold up. It is **not** a
polite `met`: callers that gate treat it as failing (see `:merge` below), because a
scorer reaching for the wrong evidence set produces `unverifiable` for everything, and
that must be loud rather than silent.

## Evidence-gathering sources (per DoD item)

**Which sources exist depends on when you are called.** This is the part that is easy
to get wrong: a scorer that assumes post-merge sources scores every pre-merge item
`unverifiable`, because `gh pr list --state merged` returns nothing before the merge.

### Pre-merge sources — the PR is open

Used by `:merge`'s gate, `:run`'s adversary, and any `:document` run before the merge
(the mid-ticket checkpoint is a first-class use — see `document-lifecycle.md`). There
is no merge commit and no merged PR, so nothing below may depend on one.

- **The PR diff.** The code as it stands. An item asserting a file, symbol, or
  behavior exists is decided here. `$GH pr diff $PR`, or
  `${GH_MCP_NS}pull_request_read(method="get_diff", …)` on the MCP backend.
- **The recorded test result.** `:pr` runs the suite **locally** and records the
  outcome in `run.jsonl` — typically the `implement` or `gates` span's
  section. That record is the artifact. Where the project also has CI running the same
  suite, the PR's check-run status (`statusCheckRollup`, already fetched by Step 1c)
  corroborates it — do not re-fetch, and do **not** re-run the suite. Most projects
  have no such CI; treat its absence as normal, not as missing evidence.
- **The Phase 0 red-test commit.** Match the frozen red tests against DoD items. An
  item anchored to a named test is `met` when that test is green in the recorded run
  *and* was genuinely red at Phase 0.
- **Manual / observable verification.** `progress.md`'s `## Update` sections, for
  hands-on verification no artifact can show. `:merge` requires the tracking dir to
  exist before Step 1, so this is always available.

### Post-merge sources — once the PR is merged

Everything above, plus the two things that do not exist until the merge lands. A
caller reaches for these **only** when the PR is actually merged; a mid-ticket
`:document` run uses the pre-merge set alone, and must not mark items `unverifiable`
merely because the merge has not happened yet.

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

## Callers

| Caller | When | On a non-`met` verdict |
|---|---|---|
| `:run` | stage 14 `close`, after the merge | blocks: any `not-met` or `unverifiable` stops the ticket |
| `:run` | handoff verification | reported to the orchestrator with the rest of the charter |
| `:document` | either — post-merge for the confirmation comment, pre-merge for a mid-ticket checkpoint | rendered `met` → ✅, `not-met` / `unverifiable` → ⚠️ |
