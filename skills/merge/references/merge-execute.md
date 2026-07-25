# Merge: Executing the Merge (Step 4 detail)

**Skipped entirely when `$ADOPT` is true** — the PR is already merged and `$MERGE_COMMIT`
came from Step 1c. Re-merging is impossible and attempting it fails the run for no
reason.

## Perform the merge

- **MCP:** `${GH_MCP_NS}merge_pull_request(owner=$OWNER, repo=$REPO, pullNumber=$PR, merge_method=$STRATEGY)`. Explicitly **not** `--auto` — the merge happens now or fails now.
- **CLI:** `$GH pr merge $PR --$STRATEGY --delete-branch --auto=false`

On failure: print the error verbatim and stop. No other state changes.

## Verify, and capture the SHA

Never trust the merge call's own return — read the PR back and assert the state:

- **MCP:** `${GH_MCP_NS}pull_request_read(method="get", owner=$OWNER, repo=$REPO, pullNumber=$PR)` → assert `state == "MERGED"`; capture the merge commit SHA as `$MERGE_COMMIT`.
- **CLI:** `$GH pr view $PR --json state,mergedAt,mergedBy,mergeCommit` → assert `state == "MERGED"`; capture `mergeCommit.oid`.

If the state is not `MERGED`, treat it as a failure and stop.

## Remote branch deletion (MCP path only)

`gh pr merge --delete-branch` handles remote cleanup on the CLI path. On the MCP path,
`merge_pull_request` does **not** delete the remote branch — do it separately, after
confirming `state == "MERGED"`:

- `$GH` available: `$GH api -X DELETE "repos/$OWNER/$REPO/git/refs/heads/$BRANCH"`.
- `gh` absent: skip and surface it — `"Remote branch '$BRANCH' was NOT deleted — delete it from the GitHub UI or run: gh api -X DELETE repos/$OWNER/$REPO/git/refs/heads/$BRANCH"`. Continue to Step 5; the PR is merged and that is what matters.
