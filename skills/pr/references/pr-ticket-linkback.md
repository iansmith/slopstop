# PR: Link the Review Back to the Ticket (Step 7f)

**Runs for all three backends.** CodeRabbit, Greptile and Claude (with `--comment`, the
default) all post their findings onto the **PR**, so in every case the ticket needs a
pointer back. Skip only when `--no-poll` was passed — then Step 6 never ran and there is no
review to link.

The ticket may be closed or in a different status by the time anyone reads this comment (a
3-state workflow closes it at merge, and the PR itself may be merged or closed too). The
comment is a **durable pointer, not a status change** — it must not touch ticket status.

## Resolve the ticket-system comment backend

Independent of Step 4a's `$BACKEND`, which is the *code-hosting* backend used to create the
PR. These can differ, and conflating them posts the comment to the wrong place.

Branch on `$SYSTEM` (resolved in Pre-flight) and run **only** that system's search — a
matching search on a system this project doesn't use returns full tool schemas for
nothing:

- **JIRA** — `ToolSearch(query="select:mcp__atlassian__addCommentToJiraIssue,mcp__atlassian__getAccessibleAtlassianResources", max_results=8)`
- **Linear** — `ToolSearch(query="select:mcp__linear-server__save_comment", max_results=4)`
- **GitHub** — `ToolSearch(query="select:mcp__github__add_issue_comment,mcp__github__update_issue", max_results=8)`.
  The result must actually include **`add_issue_comment`** — `update_issue` alone
  is not enough, since that is the tool this step calls. Present → `$GH_MCP_NS =
  "mcp__github__"`. Absent →
  fallback `ToolSearch(query="select:mcp__plugin_github_github__add_issue_comment", max_results=4)`;
  non-empty → `$GH_MCP_NS = "mcp__plugin_github_github__"`. Both empty → use the `$GH` CLI
  already resolved in Step 4a.

## Post it

- **JIRA:** resolve `cloudId` first from `mcp__atlassian__getAccessibleAtlassianResources` (that is why it is in the ToolSearch above), then `mcp__atlassian__addCommentToJiraIssue($TICKET, cloudId, body=$REVIEW_LINK_BODY)`
- **Linear:** `mcp__linear-server__save_comment(issueId=$TICKET, body=$REVIEW_LINK_BODY)`
- **GitHub MCP:** `$N` = numeric suffix of `$TICKET`; `${GH_MCP_NS}add_issue_comment(owner=$OWNER, repo=$REPO, issueNumber=$N, body=$REVIEW_LINK_BODY)`
- **GitHub CLI:** `$GH issue comment $N --repo $OWNER/$REPO --body "$(cat <<'EOF'` … `EOF`)"` — `--repo` is required, so the comment lands on the canonical repo rather than whatever cwd's remote happens to be

`$REVIEW_LINK_BODY`:

```
## PR review — $PR_BACKEND (<UTC ISO 8601 timestamp>)

PR: #$PR — $PR_URL
Review backend: <"CodeRabbit" | "Greptile" | "Claude /code-review">
Outcome: <same outcome string used in Step 8's Review: line>
```

`$PR_BACKEND` here is the value Pre-flight **resolved**, so an `--inline` run correctly
reports `claude` rather than the overridden config value. Reporting the configured-but-
overridden backend would put a false claim somewhere durable.

On failure: warn (`"Could not post review link to $TICKET: <error>. Continuing."`) and
continue to Step 8 — never block PR completion on this.
