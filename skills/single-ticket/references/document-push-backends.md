# Step 6 — Per-backend push detail

## 6a. Description

- **JIRA:** `mcp__atlassian__editJiraIssue($TICKET, cloudId, description=$EXPECTED_DESC)`.
- **Linear:** `mcp__linear-server__save_issue(id=<issue id>, description=$EXPECTED_DESC)`.
- **GitHub MCP:** `${GH_MCP_NS}update_issue(owner=$OWNER, repo=$REPO, issueNumber=$N, body=$EXPECTED_DESC)`.
- **GitHub CLI:** `$GH issue edit $N --body "$(cat <<'EOF'` … `EOF`)"` (HEREDOC for multi-line).

Do NOT touch ticket status.

## 6b. DoD-confirmation comment

- If `new`: post a new comment.
  - **JIRA:** `mcp__atlassian__addCommentToJiraIssue($TICKET, cloudId, body=$EXPECTED_DOD)`.
  - **Linear:** `mcp__linear-server__save_comment(issueId=$TICKET, body=$EXPECTED_DOD)`.
  - **GitHub MCP:** `${GH_MCP_NS}add_issue_comment(owner=$OWNER, repo=$REPO, issueNumber=$N, body=$EXPECTED_DOD)`.
  - **GitHub CLI:** `$GH issue comment $N --body "$(cat <<'EOF'` … `EOF`)"`.
- If `divergent` + `--force`:
  - Edit existing comment by id if backend supports it. **GitHub MCP:** `${GH_MCP_NS}update_issue_comment(owner=$OWNER, repo=$REPO, commentId=$ID, body=$EXPECTED_DOD)`. **GitHub CLI:** `$GH api -X PATCH "repos/$OWNER/$REPO/issues/comments/$ID" -f body="$EXPECTED_DOD"`.
  - If backend doesn't expose edit-comment (some JIRA/Linear MCP installs), post a new comment and leave the old one. Note in Step 7 output so user can delete the stale comment.

## 6c. Findings comment

Same shape as 6b — substitute `$EXPECTED_FINDINGS` for `$EXPECTED_DOD` and match on `## Findings (from local tracking)`.

## Failure handling

If push fails on any artifact mid-loop: print which succeeded and which didn't, do NOT attempt rollback. User can re-run — succeeded pushes become `unchanged` on retry.
