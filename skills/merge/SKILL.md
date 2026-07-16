---
description: Merge PR + advance ticket one state + update tracking files + push docs to ticket + delete branch. Confirms once; shows computed next state. Chains :archive (file move) automatically when the ticket lands in a terminal state after merge. Tells you to run :archive manually for intermediate-state workflows.
disable-model-invocation: true
---

# /slopstop:merge

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Set `$PREFIX` (`prefix` field), `$SYSTEM` (`system` field). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Only operate on `$PREFIX-\d+` branches.

Also read `tracking_dir` (optional): resolve to `$TRACKING_DIR`. If absent or equal to `~/.claude/ticket-active`, default to `~/.claude/ticket-active`. If a relative path (no leading `/` or `~/`), resolve from `dirname "$(git rev-parse --git-common-dir)"`. Absolute paths (starting with `/` or `~/`) are used as-is. **Guard:** if the resolved path lies under `~/.claude/`, warn `"tracking_dir resolves under ~/.claude, a protected path — headless agents cannot write there even with a matching --add-dir. Set a project-local path (e.g. \".slopstop/ticket-active\")."` and continue. The legacy default works interactively; it silently breaks fleet agents.

Missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

Autonomous mode is active when either is true: `[autonomous] enabled = true` in `.project-conf.toml` (same trigger `:start`, `:pr`, and `:plan` use), or `--autonomous` is passed on the command line for this invocation only. Either way: prompts skipped per **Autonomous behavior** section; otherwise unchanged.

## Arguments

Optional positional `<TICKET>` (e.g. `BILL-132`) to target a specific ticket from outside its branch — intended for the orchestrator pattern where `:merge` runs at the root against a finished worktree. When given, `$TICKET` is set from the arg and `$BRANCH` is resolved from the PR's `headRefName` in Step 1b; several pre-flight safety gates are re-keyed accordingly (see Pre-flight). When absent, behavior is unchanged.

Optional `--pr <N>` to disambiguate when the target branch has more than one PR. Optional `--strategy <squash|merge|rebase>` to override the default. Default strategy is `merge` (real merge commit; preserves per-commit traceability for `git bisect`). Pass `--strategy squash` or `--strategy rebase` only when a specific PR genuinely benefits from collapsed history. Optional `--autonomous` to force autonomous mode for this invocation even when `[autonomous] enabled = true` is not set in config (see `merge-autonomous.md`).

When no positional arg is given, the active ticket is parsed from `git branch --show-current` (see Pre-flight). If empty: `"No active $PREFIX ticket to merge."` and stop.

## Pre-flight

**Parse arguments first.**

If a positional arg is present and matches `^$PREFIX-\d+$`: `$TICKET = arg`, `$TARGET_GIVEN = true`. `$BRANCH` is deferred — resolved from the PR's `headRefName` in Step 1b.

If a positional arg is present but does NOT match: refuse with `"$ARG doesn't match this project's prefix ($PREFIX)."`

If no positional arg: `$TARGET_GIVEN = false`.

Run these in parallel (using `$TICKET` from above when `$TARGET_GIVEN`):

- **Resolve active ticket.**
  - `$TARGET_GIVEN = false`: parse `$TICKET` from `git branch --show-current` (find first `$PREFIX-\d+` match, case-insensitive, canonical-case result). No match → stop with `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."` Set `$BRANCH = git branch --show-current`.
  - `$TARGET_GIVEN = true`: `$TICKET` already set; `$BRANCH` resolved in Step 1b.
- **In-flight check.** Verify `$TRACKING_DIR/$TICKET/` exists (`$TICKET` is known in both paths). If not: stop with `"$TICKET is not in-flight. Run :start $TICKET first."`
- **Main-branch refusal.** Only when `$TARGET_GIVEN = false`: if `$BRANCH` (set above) is `main` or `master`, refuse with `"Refusing to merge: cwd is on the main branch, not a feature branch."` When `$TARGET_GIVEN = true`, being on the primary branch is intended — skip this check.
- `$DIRTY` = `git status --porcelain`. If non-empty: refuse with `"Refusing: working tree has uncommitted changes. Commit or stash first."`
- **Remote config** — read from `.project-conf.toml` (both optional, default `"origin"`):
  - `$ORIGIN_REMOTE` = `origin-remote` if present, else `"origin"`. Fetch, pull, and multi-remote loop skip use this.
- **`$AHEAD` check.** Only when `$TARGET_GIVEN = false`: `$AHEAD = git rev-list --count @{upstream}..HEAD` (or `0` if no upstream). If non-zero: refuse with `"Refusing: branch has N commits not pushed to $ORIGIN_REMOTE. Push first."` When `$TARGET_GIVEN = true`, skip — the agent's `:pr` step already pushed the branch.
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

`$OWNER` and `$REPO` = `pr-repo` if present, else parse from `key` (e.g. `iansmith/slopstop` → `$OWNER=iansmith`, `$REPO=slopstop`).

See `design/github-backend-primitives.md` for the full PR primitives + rationale.

### 1b. Find the PR

**When `$TARGET_GIVEN = true`** (an explicit ticket arg): the PR may be in **any** state — already merged, or closed. Resolve `$PR`, set `$BRANCH` from `headRefName`, and run the MERGED/CLOSED/OPEN dispatch there. This applies **whether or not `--pr <N>` was also given**:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-target-given.md`

Then return here for Step 1c and the gates.

**When `$TARGET_GIVEN = false`** (no explicit ticket arg — the default): if `--pr <N>` was given, use it directly as `$PR` and skip the search. Otherwise search open PRs on `$BRANCH`.

**MCP path:** `${GH_MCP_NS}list_pull_requests(owner=$OWNER, repo=$REPO, head="$OWNER:$BRANCH", state="open", perPage=5)`. (Note: `head` requires `owner:branch` format, e.g. `iansmith:feat/BILL-60`.)

**CLI path:** `$GH pr list --head $BRANCH --state open --json number,title,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup --limit 5`

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
- `headRefName != $BRANCH` — `"PR #$PR's head ref is '$headRefName', not the expected branch '$BRANCH'. Aborting to avoid merging the wrong PR."`

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
- **GitHub** — `$GH_PR_BACKEND` and `$GH_MCP_NS` inherit from Step 1a. No additional ToolSearch needed.

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

`$OWNER` and `$REPO` = `pr-repo` if present, else parse from `key`; `$N` from `$TICKET`. Read `$IN_PROGRESS_LABEL` and `$IN_REVIEW_LABEL` from `[status_labels]`.
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

Then proceed as if `yes` was given. If `skip_confirm` is absent or `false`, continue below.

**If autonomous mode is active** (`[autonomous] enabled = true` or `--autonomous` passed): skip the interactive prompt and proceed as `yes` — follow `merge-autonomous.md` → Confirmation skip for the log format.

**Otherwise** — the interactive path — show the plan, get explicit approval (`yes` / `no` / `merge-only`), and act on the answer:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-confirm-prompt.md`

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

## Step 6 — Update tracking files

Read `progress.md` in `$TRACKING_DIR/$TICKET/` and find the timestamp of the most recent `## Update` or `## Session` header.

**Non-autonomous mode:** Show:
> "Tracking files last updated at <timestamp>. Update them now before pushing to ticket? (yes / skip)"
- `yes` → invoke `/slopstop:update` inline against `$TICKET`. Wait for completion.
- `skip` → proceed with current tracking file contents.

**Autonomous mode:** always run `/slopstop:update` inline against `$TICKET`. No prompt, no staleness check.
→ Read `~/.claude/commands/slopstop-merge-refs/merge-autonomous.md` for the autonomous rule.

## Step 7 — Push docs to ticket (:document)

Invoke `/slopstop:document` against `$TICKET`. This is best-effort: if :document fails (divergence, network error, or any other error), record `$DOC_RESULT = "failed: <reason>"` and continue — do NOT roll back the merge. The merge has already landed; doc push failure is not fatal.

On success: record `$DOC_RESULT` reflecting what was pushed vs already-current.

## Step 8 — Local branch cleanup + propagate the merge to other remotes

Skip if `merge-only`.

For the full git command sequences (8a switch+pull, 8b multi-remote push, 8c worktree/branch deletion):
→ Read `~/.claude/commands/slopstop-merge-refs/merge-cleanup.md`

## Step 9 — Confirm and recommend next step

Print the summary, then a `Next step:` block.

### Summary block

```
Shipped $TICKET.

PR:      #$PR merged ($STRATEGY, $MERGE_COMMIT) into $baseRefName
Ticket:  $TICKET advanced from '<old state>' to '<new state>' on $SYSTEM
         ( or "already terminal — no transition needed" / "no forward transition available" / "unchanged (merge-only)" )
Docs:    <"description updated, DoD posted, findings posted" | "already current — skipped" | "failed: <reason>">
Remotes: $baseRefName pushed to <list of non-$ORIGIN_REMOTE remotes>
         ( or "$ORIGIN_REMOTE only" / "skipped (merge-only)" )
Branch:  <"worktree removed + local branch dropped" | "local branch dropped" | "not found locally — skipped">; remote feature branch deleted at merge
         ( or "untouched (merge-only)" )
Local:   $TRACKING_DIR/$TICKET/ untouched (see archive result below for terminal-state tickets)
```

### Next-step recommendation

Compute terminal-state classification from the **post-transition** state, using the same data Step 2 already fetched (no new ticket-system call):

- **JIRA terminal:** new state's status category key is `"done"`.
- **Linear terminal:** new state's `type === "completed"`.
- **GitHub terminal:** depends on the workflow shape recorded in Step 2.
  - **3-state** (`$NEXT_GH_ACTION.kind === "close-and-remove-label"`): after Step 5 the issue is CLOSED → **terminal** → branch **A**.
  - **4-state** (`$NEXT_GH_ACTION.kind === "swap-labels"`): after Step 5 the issue is OPEN with `$IN_REVIEW_LABEL` → **NOT terminal** → branch **B**.

Then print exactly ONE of these `Next step:` blocks based on what happened:

- **A — Advanced into terminal state:** `✅ Ticket is now in '<new state>' — terminal. Archive will run automatically (Step 10).`
- **B — Advanced into intermediate state:** `⚠️ Ticket is now in '<new state>' — NOT terminal. Wait for QA sign-off, then run /slopstop:archive manually.`
- **C — Already terminal before merge:** `✅ Ticket was already in '<state>' (terminal). Archive will run automatically (Step 10).`
- **D — No forward transition available:** `⏸ No forward transition available — ticket stays in '<state>'. Run /slopstop:archive manually once the ticket reaches a terminal state (transition manually first).`
- **E — Merge-only path:** `⏸ Ticket state NOT advanced (merge-only). Run /slopstop:archive manually once the ticket reaches a terminal state.`

## Step 10 — Inline archive (terminal-state tickets only)

This step runs only for branches **A** and **C** (post-transition state is terminal). For branches B, D, and E, skip this step entirely.

**If terminal (branch A or C):**

Log: `Post-merge state is terminal — running archive sequence inline.`

(Docs were already pushed to the ticket in Step 7. This archive step only moves the local tracking directory.)

Invoke `/slopstop:archive` against `$TICKET`. The archive runs as a Skill invocation. Because the user already confirmed the merge in Step 3 (which includes the inline archive for terminal tickets), `:archive` should proceed without its own Step 2 confirm prompt — treat this invocation as `skip_confirm = true` regardless of the project config.

If `:archive` succeeds, print the archive result below the Step 9 summary (as a continuation of the output after Step 9 completes).

If `:archive` fails (e.g., divergence stop, unexpected state, any other error), surface the error and continue. The merge succeeded; archive failure is non-fatal. Print:
`⚠️ Archive failed: <error summary>. The merge is complete. Re-run /slopstop:archive manually when ready.`

## Rules

- Confirms ONCE in Step 3. All-or-nothing on PR merge (Step 4); if merge fails, no other state changes.
- Advance ONE state, not auto-Done. Same-bucket transitions preferred. Target shown in Step 3; user can say `no`.
- Chains `:archive` inline for terminal-state tickets (Step 10); for intermediate-state workflows, leaves `$TRACKING_DIR/$TICKET/` untouched.
- Ticket transition (Step 5) is best-effort — surface failures but don't roll back the merge.
- `:document` call (Step 7) is best-effort — failure is reported in the summary `Docs:` line but does not roll back the merge.
- Branch deletion uses PR's `state: MERGED` from Step 4 (squash/rebase merges work correctly).
- Never `git push --force`, `git reset --hard`, skip pre-commit hooks, or `gh pr merge --admin`.
- Step 5 fails → print error, continue to Step 6 (falls through to branch **D**).
- Step 8 fails → leave local branch, continue to Step 9.

## Autonomous behavior

Applies whenever autonomous mode is active (`[autonomous] enabled = true` in `.project-conf.toml`, or `--autonomous` passed on the command line).

For all autonomous decisions (strategy selection, confirmation skip, update tracking, target state override, archive chain) and `[workflow]` non-autonomous config:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-autonomous.md`
