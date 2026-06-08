---
description: Merge PR + advance ticket one state (not auto-Done) + delete branch. Confirms once; shows computed next state. Chains :archive automatically when the ticket lands in a terminal state after merge. Tells you to run :archive manually for intermediate-state workflows.
disable-model-invocation: true
---

# /slopstop:merge

## Project scope

Read `.project-conf.toml`. Set `$PREFIX = key`, `$SYSTEM = system`. Only operate on `$PREFIX-\d+` branches.
Missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

If `[autonomous] enabled = true`: prompts skipped per **Autonomous behavior** section; otherwise unchanged.

## Arguments

Optional `--pr <N>` to disambiguate when the current branch has more than one open PR. Optional `--strategy <squash|merge|rebase>` to override the default. Default strategy is `merge` (real merge commit; preserves per-commit traceability for `git bisect`). Pass `--strategy squash` or `--strategy rebase` only when a specific PR genuinely benefits from collapsed history.

The active ticket is parsed from `git branch --show-current` (see Pre-flight). If empty: `"No active $PREFIX ticket to merge."` and stop.

## Pre-flight

Run these in parallel:

- **Resolve active ticket from branch.** Parse `$TICKET` from the current git branch:
  - `$BRANCH = $(git branch --show-current)`
  - Find the first match of `$PREFIX-\d+` in `$BRANCH` (case-insensitive on `$PREFIX`; canonical-case the result).
  - No match → stop with `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."`
  - Match → `$TICKET` (e.g. `MAZ-43`, `BILL-2`).
- **In-flight check.** Verify `~/.claude/ticket-active/$TICKET/` exists. If not: stop with `"$TICKET is not in-flight. Run :start $TICKET first."`
- `$BRANCH` = `git branch --show-current`. If on the main branch (`main` or `master`): refuse with `"Refusing to merge: cwd is on the main branch, not a feature branch."`
- `$DIRTY` = `git status --porcelain`. If non-empty: refuse with `"Refusing: working tree has uncommitted changes. Commit or stash first."`
- `$AHEAD` = `git rev-list --count @{upstream}..HEAD` (or `0` if no upstream). If non-zero: refuse with `"Refusing: branch has N commits not pushed to origin. Push first."`
- **GitHub auth:** deferred to Step 1a — checked only when `$GH_PR_BACKEND = "CLI"` (after PR backend detection).

## Step 1 — Resolve the PR

### 1a. Detect GitHub PR backend

Run two ToolSearches in parallel:

```
ToolSearch(query="select:mcp__github__list_pull_requests,mcp__github__pull_request_read,mcp__github__merge_pull_request,mcp__github__create_pull_request", max_results=8)
ToolSearch(query="github list pull requests merge pull request", max_results=5)
```

Set `$GH_PR_BACKEND` and `$GH_MCP_NS`:
- Canonical `mcp__github__*` tools found → `$GH_PR_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__github__"`.
- Canonical empty → run fallback: `ToolSearch(query="select:mcp__plugin_github_github__list_pull_requests,mcp__plugin_github_github__pull_request_read,mcp__plugin_github_github__merge_pull_request", max_results=8)`. If non-empty → `$GH_PR_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
- Both empty → `$GH_PR_BACKEND = "CLI"`. Find `$GH` binary by trial path: `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`. If none resolve, stop: `"Neither GitHub MCP nor 'gh' CLI found. Install one of: gh CLI (https://cli.github.com/) or the github plugin (/plugin install github@claude-plugins-official)."`. Run `$GH auth status` — if not authenticated, stop.

Parse `$OWNER` and `$REPO` from `.project-conf.toml`'s `key` field (e.g. `iansmith/slopstop` → `$OWNER=iansmith`, `$REPO=slopstop`).

See `design/github-backend-primitives.md` for the full PR primitives + rationale.

### 1b. Find the PR

If `--pr <N>` was given, use it directly as `$PR`. Otherwise list open PRs on `$BRANCH`:

**MCP path** (`$GH_PR_BACKEND = "MCP"`): call `${GH_MCP_NS}list_pull_requests(owner=$OWNER, repo=$REPO, head="$OWNER:$BRANCH", state="open", perPage=5)`. (Note: `head` requires `owner:branch` format, e.g. `iansmith:feat/BILL-60`.)

**CLI path** (`$GH_PR_BACKEND = "CLI"`):

```
$GH pr list --head $BRANCH --state open --json number,title,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup --limit 5
```

- Zero results: refuse with `"No open PR found for branch $BRANCH. Create one first."`
- More than one: print the list and ask `"Multiple open PRs on $BRANCH; pass --pr <N> to choose."` and stop.
- Exactly one: that's `$PR`.

### 1c. Read PR details

**MCP path:** `${GH_MCP_NS}pull_request_read(method="get", owner=$OWNER, repo=$REPO, pullNumber=$PR)`

**CLI path:** `$GH pr view $PR --json number,title,headRefName,baseRefName,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup,url`

### Pre-merge gates (refuse-and-explain, no remote calls past this point)

Refuse with a clear reason if any:

- `state != OPEN` — `"PR #$PR is in state '$state', not OPEN."`
- `isDraft == true` — `"PR #$PR is a draft. Mark ready for review first."`
- `mergeable == CONFLICTING` — `"PR #$PR has merge conflicts. Resolve and re-push first."`
- `mergeable == UNKNOWN` — `"GitHub hasn't computed mergeability yet. Wait a few seconds and re-run."`
- `headRefName != $BRANCH` — `"PR #$PR's head ref is '$headRefName', not the current branch '$BRANCH'. Aborting to avoid merging the wrong PR."`

### Pre-merge soft warnings (mention, but allow proceeding via confirmation)

- `mergeStateStatus == BLOCKED` (e.g. required reviews not satisfied) — note it; the user may have a temporary admin-merge override planned.
- `mergeStateStatus == BEHIND` — note that base has new commits; user may want to rebase first.
- `reviewDecision == REVIEW_REQUIRED` or `CHANGES_REQUESTED` — note it.
- Any failing or pending status check in `statusCheckRollup` — list the failed/pending check names.

## Step 2 — Detect ticket system

`.project-conf.toml`'s `system` field is authoritative for which backend to use; the ToolSearches resolve *how* to talk to it.

Run three ToolSearches in parallel:

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__editJiraIssue,mcp__atlassian__getTransitionsForJiraIssue,mcp__atlassian__transitionJiraIssue,mcp__atlassian__addCommentToJiraIssue,mcp__atlassian__getAccessibleAtlassianResources", max_results=10)
ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__save_comment,mcp__linear-server__list_issue_statuses", max_results=8)
ToolSearch(query="select:mcp__github__get_issue,mcp__github__add_issue_comment,mcp__github__update_issue,mcp__github__list_issue_comments", max_results=8)
```

Read `system` from `.project-conf.toml`. Set `$SYSTEM` (title-cased: `JIRA`, `Linear`, `GitHub`) and resolve the backend:

- **JIRA** — JIRA ToolSearch must be non-empty. If empty → stop: `"system='jira' in .project-conf.toml but no Atlassian MCP found. Configure it and retry."`
- **Linear** — Linear ToolSearch must be non-empty. If empty → stop: `"system='linear' in .project-conf.toml but no Linear MCP found. Configure it and retry."`
- **GitHub** — `$GH_BACKEND` and `$GH_MCP_NS` inherit from Step 1a. No additional ToolSearch needed.

See `design/github-backend-primitives.md` for the full primitives + rationale.

### Fetch current state and compute the "advance one" target

For the full preference-ranking algorithms (JIRA/Linear/GitHub), 3-state/4-state dispatch, already-terminal detection, and `$NEXT_GH_ACTION` kinds:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-state-machines.md`

**JIRA:**

Fetch via `mcp__atlassian__getJiraIssue` with `fields=["status","description"]`. Record `status.name` and the current status category key.
Fetch available transitions via `mcp__atlassian__getTransitionsForJiraIssue`.
Compute `$NEXT_TRANSITION` (exclude won't-do/cancel/reject, prefer same-category, fall back to category-advancing).

**Linear:**

Fetch via `mcp__linear-server__get_issue`. Record `state.name`, `state.type`, `state.position`.
Fetch team statuses via `mcp__linear-server__list_issue_statuses`.
Compute `$NEXT_STATE` (exclude canceled, prefer same-type advance by position, fall back to completed type).

**GitHub:**

Parse `$OWNER`/`$REPO` from `key`, `$N` from `$TICKET`. Read `$IN_PROGRESS_LABEL` and `$IN_REVIEW_LABEL` from `[status_labels]`.
Fetch issue state and labels. Compute `$NEXT_GH_ACTION` based on 3-state vs 4-state workflow shape.

### Already-terminal handling

If already terminal, set all `$NEXT_*` to `null` (merge proceeds; Step 5 no-op). Surface as `"already terminal — no transition needed"`.

## Step 3 — Confirm with the user

**Auto-confirm check (non-autonomous sessions):** Before showing the interactive prompt, read `.project-conf.toml` for `[workflow] skip_confirm`. If `skip_confirm = true` **and** autonomous mode is NOT already active, skip the interactive prompt and log the plan instead:

```
[workflow.skip_confirm=true] Auto-confirming merge of $TICKET.
  PR:     #$PR ($BRANCH → $BASE) — $STRATEGY
  Ticket: $CURRENT_STATE → $COMPUTED_NEXT_STATE
  <soft-warning lines if any>
```

Then proceed as if `yes` was given. If `skip_confirm` is absent or `false`, show the full interactive prompt below.

---

Show the plan and get explicit approval:

> About to merge $TICKET and ship the code:
>
> 1. **Merge** PR #$PR (`$BRANCH` → `$baseRefName`) with strategy `$STRATEGY`, then delete the remote feature branch.
> 2. **Advance** $TICKET on $SYSTEM by one state: `<current state name>` → `<computed next state name>`. (Or `"<current> — already terminal, no transition needed"` / `"<current> — no forward transition available on this workflow"` if applicable.) This is one step forward, NOT auto-Done. If the workflow's next state isn't what you expected, say `no` and handle it manually.
> 3. **Switch to `$baseRefName`, pull the merge from origin, push it to any other remotes** (mirrors / forks / upstream — if `git remote` lists anything besides `origin`), then **delete the local branch** `$BRANCH` (only after the merge is confirmed `state: MERGED`).
>
> Local tracking and ticket description NOT touched. Archive runs automatically after merge when the ticket lands in a terminal state.
>
> <soft-warning summary if any: BLOCKED / BEHIND / failing checks / no review approval>
>
> Proceed? (yes / no / merge-only)

- `yes`: all three steps.
- `merge-only`: merge only (step 1). No ticket transition, no non-origin pushes, no branch deletion.
- `no`: stop. No state changed.

If any soft warnings were present, append: `"Note the warnings above — confirming will proceed anyway."`

## Step 4 — Merge the PR

**MCP path** (`$GH_PR_BACKEND = "MCP"`): call `${GH_MCP_NS}merge_pull_request(owner=$OWNER, repo=$REPO, pullNumber=$PR, merge_method=$STRATEGY)`. (Explicitly not `--auto`; the merge happens now or fails now.)

**CLI path** (`$GH_PR_BACKEND = "CLI"`):

```
$GH pr merge $PR --$STRATEGY --delete-branch --auto=false
```

On failure: print error verbatim, stop. No state changes.

On success — verify the merge and capture the commit SHA:

**MCP path:** `${GH_MCP_NS}pull_request_read(method="get", owner=$OWNER, repo=$REPO, pullNumber=$PR)` → assert `state == "MERGED"`. Capture the merge commit SHA from the response as `$MERGE_COMMIT`. If state is not MERGED, treat as failure and stop.

**CLI path:** `$GH pr view $PR --json state,mergedAt,mergedBy,mergeCommit` → assert `state == "MERGED"`. Capture `mergeCommit.oid` as `$MERGE_COMMIT`. If state is not MERGED, treat as failure and stop.

**Remote branch deletion (MCP path only):** `gh pr merge --delete-branch` handles remote cleanup on the CLI path automatically. On the MCP path, `merge_pull_request` does not delete the remote branch — do it separately after confirming `state == "MERGED"`:
- If `$GH` (gh CLI) is available: `$GH api -X DELETE "repos/$OWNER/$REPO/git/refs/heads/$BRANCH"`.
- If `gh` is absent: skip and surface it: `"Remote branch '$BRANCH' was NOT deleted — delete it from the GitHub UI or run: gh api -X DELETE repos/$OWNER/$REPO/git/refs/heads/$BRANCH"`. Continue to Step 5 — the PR is merged and that's what matters.

## Step 5 — Advance the ticket by one state

Skip entirely if `$NEXT_TRANSITION`/`$NEXT_STATE`/`$NEXT_GH_ACTION` is `null`. Otherwise apply it via the appropriate MCP call or gh CLI command per system.

For the full JIRA/Linear/GitHub dispatch (MCP and CLI paths for each):
→ Read `~/.claude/commands/slopstop-merge-refs/merge-execute-transition.md`

On transition error: print and continue (not fatal — PR already merged).

## Step 6 — Local branch cleanup + propagate the merge to other remotes

Skip if `merge-only`.

### 6a. Switch to the base and pull the merge

```
git fetch origin --prune
git switch $baseRefName
git pull --ff-only origin $baseRefName
```

### 6b. Push the merged-onto branch to all other remotes

The merge only updated origin. If the repo has any other remotes configured (e.g. an `upstream` for a fork, a `mirror` for backup, an internal-vs-public pair), propagate `$baseRefName` to them now:

```
for remote in $(git remote); do
  [ "$remote" = "origin" ] && continue
  git push "$remote" "$baseRefName" || echo "  warning: push to $remote failed (continuing)"
done
```

This is best-effort — a failed push to a fork doesn't roll anything back. The merge already landed on origin (the source of truth); the warning surfaces so the user knows to fix the mirror manually. If `git remote` returns only `origin`, this loop is a no-op.

### 6c. Delete the local feature branch

The simple rule: "delete if the PR is logically merged." For squash/rebase merges the commits don't appear identical on the base, so `git branch -d` (safety check) would refuse. Use the merge confirmation we already have from Step 4:

- We have `state == MERGED` → the branch is logically merged regardless of strategy.
- `git branch -D $BRANCH` (force, since squash/rebase rewrites history).

If the working tree on the new base is dirty after pull (shouldn't happen — Step 6a just switched + pulled), refuse to delete the branch and report.

## Step 7 — Confirm and recommend next step

Print the summary, then a `Next step:` block. The recommendation is computed from the post-transition state — terminal vs intermediate. For terminal-state tickets Step 8 will chain archive inline; for intermediate-state tickets Step 8 is skipped and the recommendation tells the user when to run `:archive` manually.

### Summary block

```
Shipped $TICKET.

PR:      #$PR merged ($STRATEGY, $MERGE_COMMIT) into $baseRefName
Ticket:  $TICKET advanced from '<old state>' to '<new state>' on $SYSTEM
         ( or "already terminal — no transition needed" / "no forward transition available" / "unchanged (merge-only)" )
Remotes: $baseRefName pushed to <list of non-origin remotes>
         ( or "origin only" / "skipped (merge-only)" )
Branch:  local $BRANCH deleted; remote feature branch deleted at merge
         ( or "untouched (merge-only)" )
Local:   ticket-active/$TICKET/ untouched
```

### Next-step recommendation

Compute terminal-state classification from the **post-transition** state, using the same data Step 2 already fetched (no new ticket-system call):

- **JIRA terminal:** new state's status category key is `"done"`.
- **Linear terminal:** new state's `type === "completed"`.
- **GitHub terminal:** depends on the workflow shape recorded in Step 2.
  - **3-state** (`$NEXT_GH_ACTION.kind === "close-and-remove-label"`): after Step 5 the issue is CLOSED → **terminal** → branch **A**.
  - **4-state** (`$NEXT_GH_ACTION.kind === "swap-labels"`): after Step 5 the issue is OPEN with `$IN_REVIEW_LABEL` → **NOT terminal** → branch **B**.

Then print exactly ONE of these `Next step:` blocks based on what happened:

- **A — Advanced into terminal state:** `✅ Ticket is now in '<new state>' — terminal. Archive will run automatically (Step 8).`
- **B — Advanced into intermediate state:** `⚠️ Ticket is now in '<new state>' — NOT terminal. Wait for QA sign-off, then run /slopstop:archive manually.`
- **C — Already terminal before merge:** `✅ Ticket was already in '<state>' (terminal). Archive will run automatically (Step 8).`
- **D — No forward transition available:** `⏸ No forward transition available — ticket stays in '<state>'. Run /slopstop:archive manually once the ticket reaches a terminal state (transition manually first).`
- **E — Merge-only path:** `⏸ Ticket state NOT advanced (merge-only). Run /slopstop:archive manually once the ticket reaches a terminal state.`

`progress.md` is intentionally NOT written to — the user can capture mid-flight notes via `/slopstop:update` if they want.

## Step 8 — Inline archive (terminal-state tickets only)

This step runs only for branches **A** and **C** (post-transition state is terminal). For branches B, D, and E, skip this step entirely.

**If terminal (branch A or C):**

Log: `Post-merge state is terminal — running archive sequence inline.`

Invoke `/slopstop:archive` against `$TICKET`, passing the already-resolved system context (no fresh system detection needed — reuse `$SYSTEM`, `$GH_MCP_NS`, and related variables from Step 2). The archive runs as a Skill invocation, inheriting the same session context.

If `:archive` succeeds, print the archive result as part of the Step 7 confirmation block (append it below the summary).

If `:archive` fails (e.g., divergence stop, unexpected state, any other error), surface the error and continue. The merge succeeded; archive failure is non-fatal. Print:
`⚠️ Archive failed: <error summary>. The merge is complete. Re-run /slopstop:archive manually when ready.`

**If NOT terminal (branches B, D, E):** skip this step entirely.

## Rules

- Confirms ONCE in Step 3. All-or-nothing on PR merge (Step 4); if merge fails, no other state changes.
- Advance ONE state, not auto-Done. Same-bucket transitions preferred. Target shown in Step 3; user can say `no`.
- Chains `:archive` inline for terminal-state tickets (Step 8); for intermediate-state workflows, leaves `~/.claude/ticket-active/$TICKET/` untouched.
- Ticket transition (Step 5) is best-effort — surface failures but don't roll back the merge.
- Branch deletion uses PR's `state: MERGED` from Step 4 (squash/rebase merges work correctly).
- Never `git push --force`, `git reset --hard`, skip pre-commit hooks, or `gh pr merge --admin`.
- Step 5 fails → print error, continue to Step 6 (falls through to branch **D**).
- Step 6 fails → leave local branch, continue to Step 7.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

For all autonomous decisions (strategy selection, confirmation skip, target state override, archive chain) and `[workflow]` non-autonomous config:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-autonomous.md`
