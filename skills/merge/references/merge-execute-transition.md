# merge-execute-transition.md — Step 5 full dispatch detail

Used by `/slopstop:merge` Step 5 to apply the computed transition per system.

## Skip conditions

Skip Step 5 entirely if any:
- The user chose `merge-only` in Step 3 (and Step 9's recommendation falls through to branch **E**).
- `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION` is `null` (already-terminal current state, or no forward transition available on this workflow). Note this in the Step 9 summary as `"already terminal — no transition needed"` (branch **C**) or `"no forward transition available"` (branch **D**) respectively.

## Autonomous forward-only guard

Applies whenever autonomous mode is active (`[autonomous] enabled = true`, or `--autonomous` passed on the command line). Skip in non-autonomous sessions — the user validates the target state interactively in Step 3.

Before the per-system dispatch below, verify the computed transition does not move backward. Per-system forward criteria differ; lateral handling varies by system.

**JIRA:** Category order is `new` < `indeterminate` < `done`. If the target `$NEXT_TRANSITION.to.statusCategory.key` is strictly behind the current `statusCategory.key` (category regresses: `indeterminate` → `new`, `done` → `indeterminate`, or `done` → `new`), hard-stop and log:
```
[autonomous] Forward-only guard refused: JIRA transition '<current status>' → '<target status>' moves backward (category: <current key> → <target key>). Transition not applied — resolve manually.
```
Same-category transitions (`indeterminate` → `indeterminate`) are permitted; intra-category direction is not verifiable from the transition object alone. If your workflow has explicit same-category send-back transitions, set `[autonomous] merge_target_state = done` to skip intermediate states.

**Linear:** Compare type buckets first (`triage < backlog < unstarted < started < completed`). If the target `$NEXT_STATE.type` bucket is behind the current `state.type` bucket, or if the bucket is the same and `$NEXT_STATE.position` is not greater than `state.position` (lateral/same-position move within the bucket), hard-stop and log:
```
[autonomous] Forward-only guard refused: Linear transition '<current state>' → '<target state>' is not a forward advance (type: <current type> → <target type>, position: <current> → <target>). Transition not applied — resolve manually.
```

**GitHub:** If `$NEXT_GH_ACTION.kind === "swap-labels"` and `$NEXT_GH_ACTION.add` matches `/won.?t do|cancel|reject|abandon|invalid|duplicate/i` (negative-outcome label), hard-stop and log:
```
[autonomous] Forward-only guard refused: GitHub action would apply a negative-outcome label transition (<$NEXT_GH_ACTION.add>). Transition not applied — resolve manually.
```
For `close-and-remove-label` (3-state): `$NEXT_GH_ACTION` carries only `kind` and `remove` — no `state_reason` field. Not-planned closes (`state_reason = "not_planned"`) are not detectable at the action-object layer. The actual protection is that the GitHub dispatch below calls `update_issue(state="closed")` without a `state_reason` parameter — GitHub then defaults to `state_reason = "completed"`. A `not_planned` close cannot fire because the dispatch never sets it.

If the direction check passes, proceed to the per-system dispatch below.

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
