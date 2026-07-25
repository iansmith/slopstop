# Merge: Ticket-System Detection and Next-State Computation (Step 2 detail)

`.project-conf.toml`'s `system` field is authoritative for **which** backend to use; the
ToolSearches resolve **how** to talk to it. Never infer the system from MCP availability.

## Resolve the backend

Run three ToolSearches in parallel:

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__editJiraIssue,mcp__atlassian__getTransitionsForJiraIssue,mcp__atlassian__transitionJiraIssue,mcp__atlassian__addCommentToJiraIssue,mcp__atlassian__getAccessibleAtlassianResources", max_results=10)
ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__save_comment,mcp__linear-server__list_issue_statuses", max_results=8)
ToolSearch(query="select:mcp__github__get_issue,mcp__github__add_issue_comment,mcp__github__update_issue,mcp__github__list_issue_comments", max_results=8)
```

Set `$SYSTEM` (title-cased `JIRA` | `Linear` | `GitHub`) from config, then:

- **JIRA** — the JIRA ToolSearch must be non-empty, else stop: `"system='jira' in .project-conf.toml but no Atlassian MCP found. Configure it and retry."`
- **Linear** — the Linear ToolSearch must be non-empty, else stop: `"system='linear' in .project-conf.toml but no Linear MCP found. Configure it and retry."`
- **GitHub** — `$GH_PR_BACKEND` and `$GH_MCP_NS` inherit from Step 1a; no extra ToolSearch.

Full primitives and rationale: `design/github-backend-primitives.md`.

## Fetch current state and compute the "advance one" target

Preference-ranking algorithms per system, 3-state/4-state dispatch, already-terminal
detection, and the `$NEXT_GH_ACTION` kinds:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-state-machines.md`

**JIRA.** Fetch via `mcp__atlassian__getJiraIssue` with `fields=["status","description"]`;
record `status.name` and the current status-category key. Fetch transitions via
`mcp__atlassian__getTransitionsForJiraIssue`. Compute `$NEXT_TRANSITION` — exclude
won't-do/cancel/reject, prefer same-category, fall back to category-advancing.

**Linear.** Fetch via `mcp__linear-server__get_issue`; record `state.name`, `state.type`,
`state.position`. Fetch team statuses via `mcp__linear-server__list_issue_statuses`.
Compute `$NEXT_STATE` — exclude canceled, prefer same-type advance by position, fall back
to the completed type.

**GitHub.** `$OWNER`/`$REPO` = `pr-repo` if present else parse from `key`; `$N` from
`$TICKET`. Read `$IN_PROGRESS_LABEL` and `$IN_REVIEW_LABEL` from `[status_labels]`. Fetch
issue state and labels. Compute `$NEXT_GH_ACTION` from the 3-state vs 4-state shape.

## Already-terminal handling

Set every `$NEXT_*` to `null` — the merge still proceeds and Step 5 becomes a no-op.
Surface it as `"already terminal — no transition needed"`; Step 9 reports it and Step 10
treats it as branch **C**.

**The per-system predicates for "terminal" live in `merge-state-machines.md`** (linked
above) and are deliberately not repeated here — restating the consequence without the
predicate would leave a reader unable to evaluate the condition they were just given.
