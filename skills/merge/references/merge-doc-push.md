# Merge: Push Docs to the Ticket (Step 7 detail)

Gated on `[workflow] skip_archive` (default `false`). That key is `[workflow]`-scoped, not
`[autonomous]` — it behaves identically in interactive and autonomous mode.

**Both branches are best-effort.** The merge has already landed; a doc-push failure never
rolls it back.

## `skip_archive == false` (default) — full push

Invoke `/slopstop:document` against `$TICKET`. On failure (divergence, network error,
anything else) record `$DOC_RESULT = "failed: <reason>"` and continue. On success, record
`$DOC_RESULT` reflecting what was pushed versus already-current.

## `skip_archive == true` — commit-id comment only

Skip `:document` entirely: no description update, no DoD-confirmation comment, no findings
comment. Post one minimal comment instead, using the ticket-system tools already resolved
in Step 2:

- **JIRA:** `mcp__atlassian__addCommentToJiraIssue($TICKET, cloudId, body=$COMMIT_COMMENT)`
- **Linear:** `mcp__linear-server__save_comment(issueId=$TICKET, body=$COMMIT_COMMENT)`
- **GitHub MCP:** `${GH_MCP_NS}add_issue_comment(owner=$OWNER, repo=$REPO, issueNumber=$N, body=$COMMIT_COMMENT)`
- **GitHub CLI:** `$GH issue comment $N --body "$(cat <<'EOF'` … `EOF`)"`

`$COMMIT_COMMENT`:

```
## Merged into $baseRefName (<UTC ISO 8601 timestamp>)

Commit: $MERGE_COMMIT
```

Record `$DOC_RESULT = "skipped (skip_archive=true) — posted commit-id comment"`. On
failure warn (`"Could not post commit-id comment to $TICKET: <error>. Continuing."`) and
continue — same best-effort semantics as the full push.
