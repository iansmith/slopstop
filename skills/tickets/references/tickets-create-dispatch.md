# Tickets: Per-System Creation Dispatch (Step 5 detail)

Create in dependency-aware order (parents before children, blockers before blocked)
so every reference in a body points at an already-created ticket.

**Placeholder substitution:** drafts reference each other via `%%LETTER%%` tokens
(defined at draft time — Step 3). Because creation order guarantees every referenced
draft is already created, substitution is a mechanical exact-token replace on each
body just before its creation call (e.g. `sed -e "s|%%A%%|#163|g"` per assigned key —
the token shape cannot collide with prose). After all creations, grep the created
bodies for `%%` — any hit is an unresolved reference to repair. Record the
letter→key map in `run.md`.

## GitHub (`system = "github"`)

- Create: `gh issue create --repo $OWNER/$REPO --title "<title>" --body-file <tmp>`
  (write bodies to temp files; heredoc-inlined markdown with backticks is
  shell-hazardous). Capture the issue number from the printed URL.
- Umbrella linking (sub-issues): the API takes the child's database id, not its
  number:

```bash
cid=$(gh api "repos/$OWNER/$REPO/issues/$CHILD" --jq .id)
gh api -X POST "repos/$OWNER/$REPO/issues/$PARENT/sub_issues" -F sub_issue_id="$cid"
```

- `Blocked by:` stays in the body text (GitHub has no native blocked-by field).
- MCP alternative: `issue_write` (create) + `sub_issue_write` where the GitHub MCP is
  connected; fall back to CLI for anything the MCP's token cannot do (observed: some
  PATs 403 on PR/comment endpoints — surface and fall back, don't retry).

## Linear (`system = "linear"`)

- Create via `mcp__linear-server__save_issue` with `team` from `key`; set `parentId`
  to the umbrella's id for leaves (native parent/sub-issue support).
- Blocked-by: Linear relations where the MCP exposes them; otherwise body text.

## JIRA (`system = "jira"`)

- Create via `mcp__atlassian__createJiraIssue`; umbrellas as Epics, leaves linked via
  the epic-link field (or parent for subtasks — team convention decides which level).
- Blocked-by: JIRA issue links (`Blocks`/`Blocked by`) where the MCP exposes them.

## All systems

- Every body opens with the provenance header (already in the draft).
- Titles are plain (no ticket-key prefix — keys are assigned by the system);
  version markers `(V2)`/`(V3)` appear only on Stage-3 rewrites, never at creation.
- On a mid-sequence creation failure: stop creating, report what landed and what
  didn't — a partial tree is recoverable by re-running Step 5 (already-created
  tickets are recorded in `run.md`; skip them).
