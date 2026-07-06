---
description: Start or resume work on a Linear or JIRA ticket. Use /slopstop:start <KEY> (e.g. /slopstop:start MAZ-26). Fresh-starts a new ticket (fetches it, transitions to In Progress, asks for a Conventional-Commits-style branch type and creates a feature branch like fix/MAZ-26 or feat/MAZ-26 — with a heuristic suggestion from labels/title and the choice between branching off the default branch vs the current branch when cwd is on a feature branch, plus a "skip" option to opt out of branch creation entirely — then seeds tracking files), or resumes an existing one. Auto-detects ticket system.
disable-model-invocation: true
---

# /slopstop:start

Start or resume work on a ticket.

**On fresh-start:** transitions to In Progress, creates `<type>/$ARGUMENTS` branch (e.g. `fix/MAZ-99`), seeds tracking files at `$TRACKING_DIR/<TICKET>/`.

**On resume:** reads tracking dir, prints summary, appends session header. No ticket-system call, no git.

Auto-detects ticket system (JIRA via Atlassian MCP, Linear via Linear MCP, GitHub via GitHub MCP or `gh` CLI).

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Extract `key` (`$PREFIX`) and `system` (`linear` | `jira` | `github`). Only operate on `$PREFIX`'s tickets — the branch-IS-selection parser only matches `$PREFIX-\d+`.

Also read `tracking_dir` (optional): resolve to `$TRACKING_DIR`. If absent or equal to `~/.claude/ticket-active`, default to `~/.claude/ticket-active`. If a relative path (no leading `/` or `~/`), resolve from `dirname "$(git rev-parse --git-common-dir)"`. Absolute paths (starting with `/` or `~/`) are used as-is.

Also read the remote config (both optional, default `"origin"`):
- `$PR_REMOTE`     = `pr-remote` if present, else `"origin"`. Used when checking/fetching a remote branch (Steps 5a–5b).
- `$ORIGIN_REMOTE` = `origin-remote` if present, else `"origin"`. Used as the base branch remote (Step 4c).

If `.project-conf.toml` is missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `[autonomous] enabled = true` in `.project-conf.toml`, skip interactive prompts by consulting config. See **Autonomous behavior** at the bottom of this file for per-step decisions.

## Arguments

`$ARGUMENTS` must be a ticket key like `MAZ-26`. If empty, ask. Must start with `$PREFIX-`; if not: `"$ARGUMENTS doesn't match this project's prefix ($PREFIX). cd to the right project first."`

## Two modes

- **Resume:** `$TRACKING_DIR/$ARGUMENTS/` exists with content → read state, summarize, hand back. No ticket-system call. No transition.
- **Fresh-start:** dir absent or empty → detect system, fetch ticket, transition, seed files.

## Pre-flight

1. Validate `$ARGUMENTS` matches `^[A-Z]+-\d+$`. If not, ask for a valid key and stop.
2. If current branch encodes a *different* `$PREFIX-N` ticket, suggest `/slopstop:pause` first. Same branch or non-ticket branch → continue.

## Resume mode

- Read `$TRACKING_DIR/$ARGUMENTS/{task_plan,findings,progress}.md`.
- Find the most recent `## Pause` or `## Session` header in `progress.md`.
- Print:
  ```
  Resuming $ARGUMENTS

  Last paused: <date or "never">
  Branch when paused: <from progress.md>
  Last completed: <from progress.md>
  Next step: <from progress.md "Next" line, if present>
  Open questions: <from progress.md "Open" section, if present>
  ```
- Append `## Session <YYYY-MM-DD HH:MM>` to `progress.md` with "Resumed".
- Stop. If `progress.md` records a different branch than `git branch --show-current`, mention it but don't switch.

## Fresh-start mode

### Step 1 — Detect ticket system

Run three ToolSearches in parallel:

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__getAccessibleAtlassianResources,mcp__atlassian__getTransitionsForJiraIssue,mcp__atlassian__transitionJiraIssue", max_results=8)
ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__list_issue_statuses", max_results=8)
ToolSearch(query="select:mcp__github__get_issue,mcp__github__add_issue_comment,mcp__github__update_issue,mcp__github__list_issue_comments", max_results=8)
```

Set `$SYSTEM` from `.project-conf.toml`:

- **JIRA** — JIRA ToolSearch must be non-empty; else stop: `"system='jira' in .project-conf.toml but no Atlassian MCP found."`
- **Linear** — Linear ToolSearch must be non-empty; else stop: `"system='linear' in .project-conf.toml but no Linear MCP found."`
- **GitHub** — resolve `$GH_BACKEND`:
  - Canonical github ToolSearch non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__github__"`.
  - Canonical empty → fallback: `ToolSearch(query="select:mcp__plugin_github_github__get_me,mcp__plugin_github_github__add_issue_comment,mcp__plugin_github_github__issue_write", max_results=8)`. Non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
  - Both empty → `$GH_BACKEND = "CLI"`. Try paths `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, `command -v gh`; save first succeeding as `$GH`. None → stop: `"Neither GitHub MCP nor 'gh' CLI found."`. Verify auth: `$GH auth status`.

See `design/github-backend-primitives.md` for full primitives.

### Step 2 — Fetch the ticket

**JIRA:**
- Get cloudId via `mcp__atlassian__getAccessibleAtlassianResources` (cache for this run).
- Fetch via `mcp__atlassian__getJiraIssue(issueIdOrKey=$ARGUMENTS, cloudId=<cached>, fields=["summary","description","status","assignee","priority","fixVersions","labels"])`.
- Read `status.statusCategory.key` ∈ `{"new","indeterminate","done"}`.

**Linear:**
- Fetch via `mcp__linear-server__get_issue($ARGUMENTS)`. Returns title, description, state, assignee, team, priority, labels, url.
- Read `state.type` ∈ `{"backlog","unstarted","started","completed","canceled"}`.

**GitHub:**
- `$OWNER` and `$REPO` = `pr-repo` if present, else parse from `key` (e.g. `iansmith/slopstop`). Parse `$N` from `$ARGUMENTS` digits.
- MCP: `${GH_MCP_NS}get_issue(owner=$OWNER, repo=$REPO, issueNumber=$N)`. CLI: `$GH issue view $N --json number,title,state,body,labels,assignees,milestone,url`.
- Read `state` ∈ `{"OPEN","CLOSED"}` and `labels`.
- Parse `$IN_PROGRESS_LABEL` from `.project-conf.toml` `[status_labels].in_progress`. Missing → stop: `"system='github' requires [status_labels].in_progress in .project-conf.toml."`

### Step 3 — Transition to In Progress

Three cases: a. already in progress (skip), b. pre-progress (transition), c. already done (confirm reopen).
→ Read `~/.claude/commands/slopstop-start-refs/start-transition-dispatch.md`

### Step 4 — Decide branch type and base ref

Branch name: `<type>/$ARGUMENTS`. `<type>` is a Conventional-Commits prefix (`fix`, `feat`, `chore`, `docs`, `refactor`, `perf`, `test`, `ci`, `build`, `deploy`, `revert`) or a custom token passing `git check-ref-format`.

#### 4a. Suggest a default type

Infer from labels then title (case-insensitive). First label match wins; multi-label conflicts resolve by priority `fix > feat > refactor > perf > docs > chore > test`.
→ Read `~/.claude/commands/slopstop-start-refs/start-branch-type-heuristics.md`

#### 4b. Ask the user for the type

**`skip_confirm` shortcut:** If `[workflow] skip_confirm = true` in `.project-conf.toml` AND Step 4a produced a heuristic suggestion, use the suggestion without prompting. Log:
```
[workflow.skip_confirm=true] Using suggested branch type: <type> (from label '<label-name>' / title heuristic)
```
Set `$TYPE = <suggestion>`, `$NEW_BRANCH = "$TYPE/$ARGUMENTS"`, and skip the rest of Step 4b. If no suggestion is available, fall through to the interactive prompt below.

**With a suggestion:**
```
Branch type for $ARGUMENTS?
  Suggested: <type>  (from label '<label-name>' / title heuristic)
  Choices:   fix | feat | chore | docs | refactor | perf | test | ci | build | deploy | revert | <custom> | skip
```

**Without a suggestion:**
```
Branch type for $ARGUMENTS? (no signal from labels or title)
  Choices: fix | feat | chore | docs | refactor | perf | test | ci | build | deploy | revert | <custom> | skip
```

- Listed type → use it.
- Custom string → validate via `git check-ref-format --branch "<type>/$ARGUMENTS"`. Fail → `"Invalid branch type — '<input>' produces an invalid git branch name."` and re-ask.
- `skip` → `$NEW_BRANCH = null`. Step 5 is a no-op.

Set `$TYPE`, then `$NEW_BRANCH = "$TYPE/$ARGUMENTS"`.

#### 4c. Determine the base ref

Skip if `$NEW_BRANCH == null`.

- `$CURRENT_BRANCH = git branch --show-current`.
- `$DEFAULT_BRANCH = gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`. On failure: `git symbolic-ref refs/remotes/$ORIGIN_REMOTE/HEAD | sed "s@^refs/remotes/$ORIGIN_REMOTE/@@"`. Both fail → ask.

`$CURRENT_BRANCH == $DEFAULT_BRANCH` → `$BASE_REF = "$ORIGIN_REMOTE/$DEFAULT_BRANCH"` (no prompt).

`$CURRENT_BRANCH != $DEFAULT_BRANCH` → warn and ask:
```
You're currently on '$CURRENT_BRANCH', not '$DEFAULT_BRANCH'.
<if dirty:>     Working tree has uncommitted changes.
<if ahead:>     '$CURRENT_BRANCH' has N commits ahead of $ORIGIN_REMOTE/$DEFAULT_BRANCH.

Where should '$NEW_BRANCH' be based?
  - $DEFAULT_BRANCH    (clean stack off trunk)
  - $CURRENT_BRANCH    (stack on top of '$CURRENT_BRANCH')

(default / current)
```
`default` → `$BASE_REF = "$ORIGIN_REMOTE/$DEFAULT_BRANCH"` (after `git fetch $ORIGIN_REMOTE $DEFAULT_BRANCH`). `current` → `$BASE_REF = $CURRENT_BRANCH`.

### Step 5 — Create the branch

Skip if `$NEW_BRANCH == null`. Set `$BRANCH_OUTCOME = "skipped — user picked 'skip'"`.

#### 5a. Branch already exists → switch instead of creating

- Local exists (`git rev-parse --verify "refs/heads/$NEW_BRANCH"`) → `git switch "$NEW_BRANCH"`. `$BRANCH_OUTCOME = "switched to existing local branch '$NEW_BRANCH'"`. Skip 5b.
- Remote only (`git ls-remote --heads $PR_REMOTE "$NEW_BRANCH"`) → `git fetch $PR_REMOTE "$NEW_BRANCH"`, `git switch --track "$PR_REMOTE/$NEW_BRANCH"`. `$BRANCH_OUTCOME = "tracked existing remote branch '$PR_REMOTE/$NEW_BRANCH'"`. Skip 5b.

#### 5b. Create fresh

- If `$BASE_REF` starts with `$ORIGIN_REMOTE/`: `git fetch $ORIGIN_REMOTE "<ref-after-$ORIGIN_REMOTE/>"` first.
- `git switch -c "$NEW_BRANCH" "$BASE_REF"`.
- `$BRANCH_OUTCOME = "created '$NEW_BRANCH' off '$BASE_REF'"`.

On any git failure: print stderr verbatim and stop. Do not seed the tracking dir. Ticket is already In Progress (idempotent on re-run via Step 3a).

### Step 6 — Seed the tracking dir

- Create `$TRACKING_DIR/$ARGUMENTS/`.
- Write `task_plan.md`:
  ```markdown
  # $ARGUMENTS — <title>

  **Ticket system:** <JIRA | Linear | GitHub>
  **State:** <current state>
  **Assignee:** <assignee or "unassigned">
  **Priority:** <priority>
  **Labels / fixVersions:** <comma-joined>
  **Ticket URL:** <url>
  **Started:** <YYYY-MM-DD>

  ## Original description (snapshot at start)

  <description verbatim>

  ## Plan

  _(fill in as you scope the work)_
  ```
- Write `findings.md`:
  ```markdown
  # $ARGUMENTS — Findings

  _(populated as investigation progresses)_
  ```
- Write `progress.md`:
  ```markdown
  # $ARGUMENTS — Progress

  ## Session <YYYY-MM-DD HH:MM>

  Started fresh from <JIRA | Linear | GitHub> description.
  Branch: <git branch --show-current> (cwd: <pwd>) — $BRANCH_OUTCOME
  Transition: <"none — already In Progress" | "<old state> → In Progress" | "no transition available — change manually">
  ```
- Print: `"Started $ARGUMENTS — tracking at $TRACKING_DIR/$ARGUMENTS/. <transition summary>. <branch summary>."` where `<branch summary>` is: `"On '$NEW_BRANCH' (created off '$BASE_REF')"` | `"On '$NEW_BRANCH' (existing branch)"` | `"Branch creation skipped — you're on '<git branch --show-current>'"`.

## Rules

- Fresh-start transitions to In Progress. Resume does NOT touch ticket-system state.
- Branch `<type>/$ARGUMENTS` created unless user picks `skip`; `<type>` always user-confirmed (heuristic is a suggestion only).
- Resume does NOT touch git. If `progress.md` records a different branch than current, mention it but don't switch.
- On a non-default branch at fresh-start, warn and ask whether to base off default or current — never silently use current.
- No `git push --force`, `git reset --hard`, or `git branch -D`. Git failures surface verbatim.
- Tracking at `$TRACKING_DIR/$ARGUMENTS/`, not in any repo.
- Failure handling:
  - System detection fails → error, no seed, no git.
  - Ticket fetch fails → error, no seed, no git.
  - Transition fails after fetch → report, continue to branch + seeding. Note in `progress.md`.
  - Branch creation fails → report verbatim. No seed. Re-run after fix is clean (Step 3a is idempotent).
  - Disk write fails → report and stop. Branch already created; re-running re-seeds cleanly.

## Autonomous behavior

When `[autonomous] enabled = true`, consult config instead of prompting.
→ Read `~/.claude/commands/slopstop-start-refs/start-autonomous.md`
