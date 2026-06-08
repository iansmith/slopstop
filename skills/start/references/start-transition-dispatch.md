# Per-system transition dispatch (Step 3)

## a. Already in progress — skip transition

- **JIRA:** `status.statusCategory.key === "indeterminate"`
- **Linear:** `state.type === "started"`
- **GitHub:** issue is `OPEN` AND already has `$IN_PROGRESS_LABEL`

Note "already In Progress" in the confirmation and continue to Step 4.

## b. Pre-progress — transition

**JIRA** (`status.statusCategory.key === "new"`):
- Call `getTransitionsForJiraIssue`.
- Pick the transition whose target has `statusCategory.key === "indeterminate"`. If multiple, prefer one whose name contains "progress" (case-insensitive); else first.
- Call `transitionJiraIssue` with that transition id.
- If no matching transition exists: print `"Couldn't find an In-Progress transition on $ARGUMENTS — transition manually on JIRA if needed."` and continue.

**Linear** (`state.type ∈ {"backlog", "unstarted"}`):
- Call `mcp__linear-server__list_issue_statuses` for the issue's team.
- Filter to entries with `type === "started"`. If multiple, prefer one whose name contains "progress"; else first.
- Call `mcp__linear-server__save_issue` with the issue id and `stateId = <chosen state id>`.
- If no `started`-type state exists: print warning and continue.

**GitHub** (issue is `OPEN` AND does NOT have `$IN_PROGRESS_LABEL`):
- **MCP path:** `${GH_MCP_NS}add_issue_labels(owner=$OWNER, repo=$REPO, issueNumber=$N, labels=[$IN_PROGRESS_LABEL])`.
- **CLI path:** `$GH issue edit $N --add-label "$IN_PROGRESS_LABEL"`.
- GitHub silently accepts adding a label already on the issue — no pre-check needed.
- If the label doesn't exist on the repo, the call fails: print the error and continue with seeding (user can create the label manually or via `/slopstop:gh-init`).

## c. Already done — confirm before reopening

- **JIRA:** `status.statusCategory.key === "done"`
- **Linear:** `state.type ∈ {"completed", "canceled"}`
- **GitHub:** issue is `CLOSED`

Print: `"Ticket $ARGUMENTS is in a terminal state ('<state name>'). Start work anyway? This will reopen it to In Progress. (yes / no)"`

- `no` → stop. Don't create tracking dir.
- `yes` → transition as in case (b). For GitHub, reopen first (`${GH_MCP_NS}update_issue(owner=$OWNER, repo=$REPO, issueNumber=$N, state="open")` or `$GH issue reopen $N`), then apply the in-progress label.
