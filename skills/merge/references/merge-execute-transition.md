# merge-execute-transition.md — Step 5 full dispatch detail

Used by `/slopstop:merge` Step 5 to apply the computed transition per system.

## Skip conditions

Skip Step 5 entirely if any:
- The user chose `merge-only` in Step 3 (and Step 9's recommendation falls through to branch **E**).
- `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION` is `null` (already-terminal current state, or no forward transition available on this workflow). Note this in the Step 9 summary as `"already terminal — no transition needed"` (branch **C**) or `"no forward transition available"` (branch **D**) respectively.

## JIRA

`mcp__atlassian__transitionJiraIssue($TICKET, cloudId, $NEXT_TRANSITION.id)`.

## Linear

`mcp__linear-server__save_issue` with the issue id and `stateId = $NEXT_STATE.id`.

## GitHub

**3-state** (`$NEXT_GH_ACTION.kind === "close-and-remove-label"`):
- MCP path: `${GH_MCP_NS}update_issue(owner=$OWNER, repo=$REPO, issueNumber=$N, state="closed")` then `${GH_MCP_NS}remove_issue_label(owner=$OWNER, repo=$REPO, issueNumber=$N, label=$NEXT_GH_ACTION.remove)`.
- CLI path: `$GH issue close $N && $GH issue edit $N --remove-label "$NEXT_GH_ACTION.remove"`.

**4-state** (`$NEXT_GH_ACTION.kind === "swap-labels"`):
- MCP path: two calls — `${GH_MCP_NS}add_issue_labels(owner=$OWNER, repo=$REPO, issueNumber=$N, labels=[$NEXT_GH_ACTION.add])` then `${GH_MCP_NS}remove_issue_label(owner=$OWNER, repo=$REPO, issueNumber=$N, label=$NEXT_GH_ACTION.remove)`. (Add first to avoid a label-less intermediate state if remove succeeds but add fails.)
- CLI path: single atomic call — `$GH issue edit $N --add-label "$NEXT_GH_ACTION.add" --remove-label "$NEXT_GH_ACTION.remove"`. Issue stays OPEN.

For both kinds: GitHub silently accepts add/remove of a label that's already in the target state, so retries are safe.

## Error handling

On any transition error: print the error and continue to Step 6. The PR is already merged; an inability to advance the ticket state isn't fatal. The user can transition manually after the fact.
