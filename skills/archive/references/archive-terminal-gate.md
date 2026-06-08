# archive-terminal-gate — Step 2 detail

## Per-system state checks

**JIRA:**
- Get cloudId via `mcp__atlassian__getAccessibleAtlassianResources` and cache it.
- Fetch via `mcp__atlassian__getJiraIssue($TICKET, cloudId, fields=["status","description"])`.
- If `status.statusCategory.key !== "done"`, refuse.

**Linear:**
- Fetch via `mcp__linear-server__get_issue($TICKET)`.
- If `state.type` ∉ `{"completed", "canceled"}`, refuse.

**GitHub:**
- Parse `$OWNER` and `$REPO` from `.project-conf.toml`'s `key` field. Parse `$N` from `$TICKET`.
- **MCP path:** `${GH_MCP_NS}get_issue(owner=$OWNER, repo=$REPO, issueNumber=$N)` → read `state` and `body`.
- **CLI path:** `$GH issue view $N --json state,body` → same fields.
- If `state !== "CLOSED"`, refuse. Github has no completed/canceled nuance — binary OPEN/CLOSED.

## Refusal output

```
Cannot archive $TICKET — ticket is in state '<state name>' (<system> category: <category>).

/slopstop:archive only operates on tickets already in a terminal state on the ticket system.
- JIRA: Done category (Done, Closed, Resolved, Won't Do, Canceled).
- Linear: state type 'completed' or 'canceled'.
- GitHub: issue state CLOSED.

Move $TICKET to a terminal state on <system> first, then re-run /slopstop:archive.
```

Stop. Do not push anything. Do not archive. Do not modify any local files.
