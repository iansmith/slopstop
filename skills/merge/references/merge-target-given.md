# merge-target-given.md — explicit-ticket PR resolution (Step 1b/1c detail)

Read this only when `$TARGET_GIVEN = true` — an explicit ticket argument was passed. The
default path (no ticket arg) resolves the PR from `$BRANCH` in the spine and never needs
any of this.

The difference: with an explicit ticket the PR may be in *any* state — it may already be
merged, or closed. So the search widens to all PRs, and a three-way state dispatch runs
before the pre-merge gates.

## Find the PR

Search all PRs (open and closed) for the target ticket.

**MCP path:** `${GH_MCP_NS}list_pull_requests(owner=$OWNER, repo=$REPO, state="all", perPage=10)`, then filter for PRs whose `headRefName` contains `$TICKET` (case-insensitive) or whose `title` starts with `[$TICKET]` or `$TICKET:`.

**CLI path:** `$GH pr list --search "$TICKET in:title" --state all --json number,title,headRefName,baseRefName,state,isDraft,mergeable,mergeStateStatus,reviewDecision,mergedAt,mergeCommit,url --limit 10`

- Zero results: refuse with `"No PR found for ticket $TICKET. Create one with /slopstop:pr first."`
- More than one: print the list and ask `"Multiple PRs for $TICKET; pass --pr <N> to choose."` and stop.
- Exactly one: that's `$PR`. Set `$BRANCH = headRefName` from the result.

## Three-way state dispatch

- `state == MERGED` → the PR is already shipped. Capture `$MERGE_COMMIT` from the result (CLI: `mergeCommit.oid`; MCP: merge commit SHA from PR details). Log: `"PR #$PR for $TICKET is already merged ($MERGE_COMMIT) — skipping Step 4, proceeding with ticket transition and archive."` Skip Step 4; continue from Step 5 with `$MERGE_COMMIT` in hand.
- `state == CLOSED` (not merged) → reopen before proceeding:
  - `$GH pr reopen $PR` (both paths — MCP has no reopen primitive).
  - On reopen failure: stop with the error verbatim. (A PR closed due to branch deletion may be unrecoverable — surface this.)
  - After successful reopen, proceed as `OPEN`.
- `state == OPEN` → proceed normally.

## When `--pr <N>` was also given

The search above is skipped — `$PR` is known. **The state dispatch still applies.** Read the
PR details first (the spine's Step 1c calls), then set `$BRANCH = headRefName` and run the
same three-way above. Skipping the dispatch here would leave `$BRANCH` unset and re-merge
an already-merged PR.

Note the spine's `headRefName != $BRANCH` gate still does real work in this case: it catches
a `--pr <N>` that names a PR belonging to a different branch than expected.
