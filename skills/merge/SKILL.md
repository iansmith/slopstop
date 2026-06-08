---
description: End-to-end "ship it" for the active ticket — code side only. Use /slopstop:merge to merge the PR, advance the ticket by one state in its workflow on Linear/JIRA (NOT auto-Done — same-bucket transitions like "In Progress" → "In Review" are preferred over jumps to Done so review/QA gates aren't skipped), and delete the merged branch. Does NOT archive local tracking or push the task plan back to the ticket — that's /slopstop:archive, which the user runs separately once the ticket actually reaches a terminal Done-type state (typically after QA). The end-of-run summary classifies the post-transition state and tells the user whether to run :archive now or wait. Confirms once before any destructive remote operation; the confirmation prompt shows the specific computed next state so you know what you're agreeing to. Refuses safely on dirty trees, unpushed commits, draft PRs, or merge conflicts. Auto-detects ticket system.
disable-model-invocation: true
---

# /slopstop:merge

Merge the active ticket's PR, advance the ticket by one state on the ticket system (not auto-Done — the workflow's "next" state, which is typically a review/QA step before Done), and delete the corresponding branch if cleanly merged. The local tracking dir (`~/.claude/ticket-active/$TICKET/`) and the ticket description are NOT touched — those belong to `/slopstop:archive`, which the user runs separately once the ticket has reached a terminal state.

End-to-end "ship it" path for the code side only. Irreversible. Confirms once before remote operations, and the confirmation shows the specific computed next state so the user knows what they're agreeing to. After completion, the summary classifies the post-transition state (terminal vs intermediate) and tells the user whether to run `/slopstop:archive` now or wait for QA.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd. Extract `key` (Linear team key, JIRA project key, or GitHub `owner/repo`) and call it `$PREFIX`. Also note `system` (`linear` | `jira` | `github`) for downstream logic.

**Only operate on `$PREFIX`'s tickets. The branch-IS-selection parser only matches `$PREFIX-\d+`, so a branch encoding a different project's prefix correctly fails the no-match check.**

If `.project-conf.toml` is missing in cwd: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill skips interactive prompts by consulting the config instead of asking. If `[autonomous]` is absent or `enabled = false`, behavior is unchanged. See **Autonomous behavior** at the bottom of this file for the per-prompt decisions.

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
- **GitHub** — `$GH_BACKEND` and `$GH_MCP_NS` inherit directly from Step 1a (`$GH_BACKEND = $GH_PR_BACKEND`; `$GH_MCP_NS` unchanged). The same MCP namespace that exposes PR-level tools (Steps 1/4) also exposes the issue-level tools needed here (read issue, add/remove label, close issue). No additional ToolSearch or auth check needed.

See `design/github-backend-primitives.md` for the full primitives + rationale.

### Fetch current state and compute the "advance one" target

The merge advances the ticket by **one** state in the workflow — not auto-Done. Plenty of teams have an intermediate review or QA state between In Progress and Done, and `gh pr merge` shouldn't skip past them. The computed target is shown in Step 3's confirmation prompt before anything irreversible happens, so if it's not what the user expects, they can abort.

**JIRA:**

Fetch via `mcp__atlassian__getJiraIssue` with `fields=["status","description"]`. Record `status.name` and the current status category key.
Fetch available transitions via `mcp__atlassian__getTransitionsForJiraIssue`.
Compute `$NEXT_TRANSITION` (exclude won't-do/cancel/reject, prefer same-category, fall back to category-advancing).

For the full preference-ranking algorithm:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-state-machines.md`

**Linear:**

Fetch via `mcp__linear-server__get_issue`. Record `state.name`, `state.type`, `state.position`.
Fetch team statuses via `mcp__linear-server__list_issue_statuses`.
Compute `$NEXT_STATE` (exclude canceled, prefer same-type advance by position, fall back to completed type).

For the full preference-ranking algorithm:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-state-machines.md`

**GitHub:**

Parse `$OWNER`/`$REPO` from `key`, `$N` from `$TICKET`. Read `$IN_PROGRESS_LABEL` and `$IN_REVIEW_LABEL` from `[status_labels]`.
Fetch issue state and labels. Compute `$NEXT_GH_ACTION` based on 3-state vs 4-state workflow shape.

For the full 3-state/4-state dispatch and `$NEXT_GH_ACTION` kinds:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-state-machines.md`

### Already-terminal handling

If the current state is already terminal, set `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION` to `null`. The merge can still proceed; the transition step becomes a clean no-op. Surface this in Step 3 as `"already terminal — no transition needed"`.

For terminal-state detection criteria per system:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-state-machines.md`

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

Show the full plan and get explicit approval. This is the only confirmation prompt — all three remote actions happen on `yes`.

> About to merge $TICKET and ship the code:
>
> 1. **Merge** PR #$PR (`$BRANCH` → `$baseRefName`) with strategy `$STRATEGY`, then delete the remote feature branch.
> 2. **Advance** $TICKET on $SYSTEM by one state: `<current state name>` → `<computed next state name>`. (Or `"<current> — already terminal, no transition needed"` / `"<current> — no forward transition available on this workflow"` if applicable.) This is one step forward, NOT auto-Done. If the workflow's next state isn't what you expected, say `no` and handle it manually.
> 3. **Switch to `$baseRefName`, pull the merge from origin, push it to any other remotes** (mirrors / forks / upstream — if `git remote` lists anything besides `origin`), then **delete the local branch** `$BRANCH` (only after the merge is confirmed `state: MERGED`).
>
> Local tracking (`~/.claude/ticket-active/$TICKET/`) and the ticket description are **NOT** touched by this command. After the merge, the summary will tell you whether to run `/slopstop:archive` now (ticket landed in a terminal Done-type state) or to wait until QA/review completes (ticket landed in an intermediate state like `In Review`).
>
> <soft-warning summary if any: BLOCKED / BEHIND / failing checks / no review approval>
>
> Proceed? (yes / no / merge-only)

- `yes`: all three steps.
- `merge-only`: step 1 only — merge the PR, then stop. Do NOT touch the ticket system, do NOT push to non-origin remotes, do NOT delete the local branch, do NOT touch local tracking.
- `no`: stop. No state changed.

If any soft warnings were present, append: `"Note the warnings above — confirming will proceed anyway."`

## Step 4 — Merge the PR

**MCP path** (`$GH_PR_BACKEND = "MCP"`): call `${GH_MCP_NS}merge_pull_request(owner=$OWNER, repo=$REPO, pullNumber=$PR, merge_method=$STRATEGY)`. (Explicitly not `--auto`; the merge happens now or fails now.)

**CLI path** (`$GH_PR_BACKEND = "CLI"`):

```
$GH pr merge $PR --$STRATEGY --delete-branch --auto=false
```

On failure (either path):
- Print the error verbatim.
- Stop. Do not touch the ticket system. Do not touch local files. The branch is unchanged.

On success — verify the merge and capture the commit SHA:

**MCP path:** `${GH_MCP_NS}pull_request_read(method="get", owner=$OWNER, repo=$REPO, pullNumber=$PR)` → assert `state == "MERGED"`. Capture the merge commit SHA from the response as `$MERGE_COMMIT`. If state is not MERGED, treat as failure and stop.

**CLI path:** `$GH pr view $PR --json state,mergedAt,mergedBy,mergeCommit` → assert `state == "MERGED"`. Capture `mergeCommit.oid` as `$MERGE_COMMIT`. If state is not MERGED, treat as failure and stop.

**Remote branch deletion (MCP path only):** `gh pr merge --delete-branch` handles remote cleanup on the CLI path automatically. On the MCP path, `merge_pull_request` does not delete the remote branch — do it separately after confirming `state == "MERGED"`:
- If `$GH` (gh CLI) is available: `$GH api -X DELETE "repos/$OWNER/$REPO/git/refs/heads/$BRANCH"`.
- If `gh` is absent: skip and surface it: `"Remote branch '$BRANCH' was NOT deleted — delete it from the GitHub UI or run: gh api -X DELETE repos/$OWNER/$REPO/git/refs/heads/$BRANCH"`. Continue to Step 5 — the PR is merged and that's what matters.

## Step 5 — Advance the ticket by one state

Step 2 already computed `$NEXT_TRANSITION` (JIRA), `$NEXT_STATE` (Linear), or `$NEXT_GH_ACTION` (GitHub). Step 3 showed it in the confirmation prompt. Step 5 just applies it.

Skip entirely if `$NEXT_TRANSITION`/`$NEXT_STATE`/`$NEXT_GH_ACTION` is `null` (already terminal or merge-only path chosen).

Apply the computed transition via the appropriate MCP call or gh CLI command per system.

For the full JIRA/Linear/GitHub dispatch (MCP and CLI paths for each):
→ Read `~/.claude/commands/slopstop-merge-refs/merge-execute-transition.md`

On any transition error: print the error and continue to Step 6. The PR is already merged; an inability to advance the ticket state isn't fatal.

> **Why advance one state and not auto-Done?** Most real workflows have intermediate states between "In Progress" and "Done" — typically a review or QA step the team uses to gate deployment. Auto-Done on PR merge skips those gates, which is wrong for most teams. Advance-one respects whatever shape the team's workflow happens to be. If your workflow has no intermediate state (just In Progress → Done), advance-one IS Done — because that's what your workflow's "next" actually is.

## Step 6 — Local branch cleanup + propagate the merge to other remotes

**Skip Step 6 entirely** if the user chose `merge-only` in Step 3. The local feature branch stays, non-origin remotes stay unpropagated, and Step 7's summary reports `Branch: untouched (merge-only)` / `Remotes: skipped (merge-only)`.

Otherwise: Step 4 already handled the remote feature branch on origin. The local branch still exists, and any non-origin remotes (mirrors, upstream forks) still need the merged-onto branch pushed.

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

Print the summary, then a `Next step:` block recommending whether to run `/slopstop:archive` now or wait. The recommendation is computed from the post-transition state — terminal vs intermediate.

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

- **A — Advanced into terminal state:** `✅ Ticket is now in '<new state>' — terminal. Run /slopstop:archive.`
- **B — Advanced into intermediate state:** `⚠️ Ticket is now in '<new state>' — NOT terminal. Do NOT run :archive yet. Wait for QA sign-off, then run /slopstop:archive.`
- **C — Already terminal before merge:** `✅ Ticket was already in '<state>' (terminal). Run /slopstop:archive.`
- **D — No forward transition available:** `⏸ No forward transition available — ticket stays in '<state>'. Run :archive only when it reaches a terminal state (transition manually first).`
- **E — Merge-only path:** `⏸ Ticket state NOT advanced (merge-only). Run :archive only when ticket reaches terminal state.`

`progress.md` is intentionally NOT written to — the user can capture mid-flight notes via `/slopstop:update` if they want.

## Rules

- Confirms ONCE in Step 3 before any destructive remote action. After that, run to completion or fail loudly.
- **Advance ONE state, not auto-Done.** Same-bucket transitions preferred. Proposed target shown in Step 3; user can say `no`.
- **Does NOT touch local tracking or push the task plan.** `~/.claude/ticket-active/$TICKET/` stays in place. `/slopstop:archive` handles that separately, once the ticket reaches a terminal state.
- **Step 7 always tells the user whether to run `:archive` now or wait.** JIRA terminal = status category `"done"`, Linear terminal = `state.type === "completed"`. Terminal → recommend `:archive` now. Non-terminal → warn to wait for QA. No forward transition or merge-only → neutral note.
- All-or-nothing on the PR merge (Step 4). If it fails, no other state changes.
- The ticket transition (Step 5) is best-effort after the merge — surface failures but don't roll back.
- Branch deletion (Step 6) uses the PR's authoritative `state: MERGED` from Step 4, so squash and rebase merges work.
- Never run `git push --force`, `git reset --hard`, or skip pre-commit hooks.
- Never enable `--admin` on `gh pr merge` to bypass branch protection.
- Failure handling:
  - **Pre-flight / Step 1 fails**: stop. No state changed.
  - **Step 4 (merge) fails**: print error, stop. No state changed.
  - **Step 5 (transition) fails**: print error, continue to Step 6. PR is merged. Step 7 falls through to branch **D**.
  - **Step 6 (branch cleanup) fails**: leave local branch, continue to Step 7 and report.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

For all autonomous decisions (strategy selection, confirmation skip, target state override, archive chain) and `[workflow]` non-autonomous config:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-autonomous.md`
