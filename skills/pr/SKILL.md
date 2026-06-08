---
description: Open a pull request for the active ticket's branch with pre-commit simplify + tests + configurable review (CodeRabbit or Claude). Use /slopstop:pr to (1) run Claude Code's code-simplifier agent on uncommitted changes, (2) run the project's tests and refuse to commit on failures, (3) commit with a ticket-anchored message, (4) push and open a PR via GitHub MCP or gh CLI, (5) trigger or run the configured review backend — CodeRabbit (default) or Claude /code-review — posting findings to the PR, and (6) categorize the suggestions for action. Stops after presenting — never auto-applies (unless fix = true in [pr_review], which commits fixable findings after code-review completes). Review backend is set via [pr_review] in .project-conf.toml; omit the block to keep CodeRabbit as the default.
disable-model-invocation: true
---

# /slopstop:pr

Open a pull request for the active ticket's branch with a pre-commit simplify pass and a configurable review backend — CodeRabbit (default) or Claude `/code-review`, set via `[pr_review]` in `.project-conf.toml`.

Confirms before each significant remote action. Stops after presenting the review — the user decides which suggestions to apply.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd. Extract `key` (Linear team key, JIRA project key, or GitHub `owner/repo`) and call it `$PREFIX`. Also note `system` (`linear` | `jira` | `github`) for downstream logic.

**Only operate on `$PREFIX`'s tickets. The branch-IS-selection parser only matches `$PREFIX-\d+`, so a branch encoding a different project's prefix correctly fails the no-match check.**

If `.project-conf.toml` is missing in cwd: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill skips interactive prompts by consulting the config instead of asking. If `[autonomous]` is absent or `enabled = false`, behavior is unchanged. See **Autonomous behavior** at the bottom of this file for the per-prompt decisions.

## Arguments

Optional `--base <branch>` to override the PR target branch (default: the repo's default branch — usually `master` or `main`).
Optional `--no-simplify` to skip Step 1's simplify pass.
Optional `--no-test` to skip Step 2's pre-commit test run.
Optional `--no-poll` to open the PR and stop without running any review step (applies to both CodeRabbit and Claude backends). Useful for documentation-only PRs, or when you want to ship and review separately.

The active ticket is parsed from `git branch --show-current` (see Pre-flight). If empty: `"No active $PREFIX ticket to PR."` and stop.

## Pre-flight (run in parallel)

- **Resolve active ticket from branch.** Parse `$TICKET` from the current git branch:
  - `$BRANCH = $(git branch --show-current)`
  - Find the first match of `$PREFIX-\d+` in `$BRANCH` (case-insensitive on `$PREFIX`; canonical-case the result).
  - No match → stop with `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."`
  - Match → `$TICKET` (e.g. `MAZ-43`, `BILL-2`).
- **In-flight check.** Verify `~/.claude/ticket-active/$TICKET/` exists. If not: stop with `"$TICKET is not in-flight. Run :start $TICKET first."`
- `$BRANCH` = `git branch --show-current`. If on the main/master branch: refuse with `"Refusing: on the main branch, not a feature branch."`
- `$DIRTY` = `git status --porcelain` (used in Step 1 and Step 2).
- `$DEFAULT_BRANCH` = `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name` (cache for Step 4c).
- `$BASE` = `--base` argument if given, else `$DEFAULT_BRANCH`.
- **`[pr_review]` config** — read from `.project-conf.toml` (all fields optional):
  - `$PR_BACKEND` = `pr_review.backend` if present, else `"coderabbit"`.
  - `$PR_EFFORT`  = `pr_review.effort`  if present, else `"high"` (Claude only).
  - `$PR_FIX`     = `pr_review.fix`     if present, else `false`  (Claude only).

If an open PR already exists for `$BRANCH` (`gh pr list --head $BRANCH --state open` returns ≥1), refuse: `"PR already exists for $BRANCH: <url>. Use /slopstop:merge to ship it, or push more commits to update."`

## Step 0 — Pre-PR health gate

**Run the full test suite before touching anything.**

### 0a. Identify the test command (same logic as Step 2a below)

Use `**Test command:**` from `task_plan.md` if present. Otherwise auto-detect (same table as Step 2a). If not determinable, skip this gate with a warning and continue to Step 1.

### 0b. Run the full suite and evaluate

Execute the test command. Capture output and exit code.

**Pass (exit 0):** print `"Pre-PR gate: all tests passing. Proceeding."` and continue to Step 1.

**Fail (non-zero exit):** Classify each failing test as **Regression** (passed at Phase 0 time) or **Expected failure** (Phase 0 red test for THIS ticket not yet green).

**If there are ANY regressions:** hard stop in autonomous mode (default), or ask in interactive mode. With `benchmark-continue`: proceed with override record and prominent PR body warning.

**If there are ONLY expected failures (no regressions):** warn but allow user (or autonomous config) to decide.

For the structured summary output format and the benchmark override record JSON:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-test-failure-gate.md`

### 0c. Cyclomatic Complexity gate

Check for over-complex functions in source files modified by this PR. High CC (cyclomatic complexity) predicts structural decay — our eval data shows CC max climbing from 18→26→34→40 across checkpoints, correlating with test-pass collapse.

**Tool: `lizard`** — a single pip-installable tool that computes function-level CC across Python, JavaScript, TypeScript, Java, Go, Rust, C/C++, C#, Kotlin, Swift, Scala, PHP, Ruby, and more.

Compute `CHANGED_CODE` = source files (lizard-supported extensions) modified since branch point. If `CHANGED_CODE` is empty: **skip this gate.**

Read thresholds from `.project-conf.toml`:
- `cc_warn_threshold` (default: **10**) — 🟡 elevated boundary
- `cc_reject_threshold` (default: **15**) — 🔴 hard-gate threshold

**Decision:** If 🔴 violations exist: hard stop (interactive) or benchmark-continue (autonomous, with `pipeline.json` record and `⚠️ BENCHMARK OVERRIDE (CC)` PR body note). If only 🟡 elevated: proceed; append a **Complexity notes** section to the PR body. If `CHANGED_CODE` empty or `lizard` unavailable: skip.

For the full shell implementation (`BASE_SHA` computation, `CHANGED_CODE` detection, lizard auto-install cascade, `CC_JSON` parsing, lizard JSON fields, `NEW_FUNC_NAMES` extraction, CC report format, benchmark override record JSON):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-cc-gate.md`

## Step 1 — Simplify pass on uncommitted changes

Skip if `--no-simplify` was passed, OR if `$DIRTY` is empty (nothing to simplify).

Catch reuse/quality/efficiency issues before they land in a commit. Snapshot the diff before and after; invoke the code-simplifier agent; compare. If identical: continue silently. If different: show delta and ask `continue / abort`.

For the snapshot commands, Agent tool invocation block, and before/after diff comparison logic:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-simplify.md`

## Step 2 — Run relevant tests before committing

Skip if `--no-test` was passed.

### 2a. Identify the test command

In order: (1) `**Test command:**` line in `task_plan.md`, (2) auto-detect from project files, (3) ask the user once and cache.

Auto-detect from project files (`Taskfile.yml` → `task test`, `Makefile` → `make test`, `package.json` → npm/yarn/pnpm, `Cargo.toml` → `cargo test`, `go.mod` → `go test ./...`, `pyproject.toml` → `pytest`). Full table:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-test-detection.md`

### 2b. Run the tests

Execute the test command. Treat exit code 0 as success, anything else as failure.

### 2c. Handle results

- **Pass** (exit 0): print `"Tests passed. Continuing to commit."` and proceed to Step 3.
- **Fail** (non-zero exit): print failures, then offer `fix / commit anyway / abort`. On `fix` or `abort`: stop. On `commit anyway`: continue to Step 3 with a `Note: <N> test(s) failing at commit time` body line.

## Step 3 — Commit (with a ticket-anchored message)

Skip if `$DIRTY` is empty after Step 1 (nothing to commit).

Stage everything: `git add -A`. Generate commit message:
- **Subject** (≤ 72 chars): `[$TICKET] <imperative summary>`.
- **Body** (1–3 short paragraphs): explain WHY. Pull from `task_plan.md`'s Plan section.
- **Trailer**: `Refs: $TICKET`.

Commit with `-m` flags or HEREDOC. If pre-commit hooks fail: print the hook output verbatim and stop. Do NOT pass `--no-verify`.

## Step 4 — Find the GitHub backend, then push

### 4a. Locate the GitHub backend

Run two ToolSearches in parallel for `mcp__github__*` tools. Set `$BACKEND`: MCP if found, else CLI. Find `$GH` binary (try `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`). If none: stop with install instructions.

### 4b. Push the branch

- No upstream: `git push -u origin $BRANCH`.
- Ahead of upstream: `git push origin $BRANCH`.
- In sync: skip push.

On push failure: stop with git output verbatim. Never `git push --force`.

## Step 5 — Create the PR

### 5a. Build title and body

- **Title**: `[$TICKET] <summary>` (from most recent commit subject).
- **Body**: `## Summary` (1–3 bullets), `## Ticket` (URL), `## Test plan` (checklist).

### 5b. Create the PR

MCP: call the create-pull-request tool. CLI: use HEREDOC with `$GH pr create`. Capture `$PR` and `$PR_URL`. Print: `"PR created: $PR_URL (target: $BASE)"`.

### 5c. Trigger CodeRabbit (CodeRabbit backend only)

Skip if `$PR_BACKEND == "claude"` or `--no-poll`. If `$BASE != $DEFAULT_BRANCH`: post `@coderabbitai review` comment. On failure: warn and continue.

## Step 6 — Review pass (backend-dependent)

**Skip entirely if `--no-poll` was passed.** Continue to Step 8.

Dispatch on `$PR_BACKEND`:
- **`"coderabbit"`** → Step 6-cr, then Step 7.
- **`"claude"`** → Step 6-claude, then Step 8.

---

## Step 6-cr — Poll for CodeRabbit feedback

Poll for a `coderabbitai[bot]` walkthrough comment referencing `$HEAD_SHA` (the reliable completion signal for both first and incremental reviews). Poll every 60 s, up to 20 iterations.

For the complete polling implementation (shell script, first-vs-incremental trap explanation, timeout handling, clean-incremental-pass note):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-cr-polling.md`

## Step 6-claude — Claude code review

Build args: `--effort $PR_EFFORT --comment` (add `--fix` if `$PR_FIX == true`). Invoke `Skill({skill: "code-review", args: ...})`.

For the full invocation blocks and `--fix` commit/push flow:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-claude-review.md`

---

## Step 7 — Verify, classify, and present CodeRabbit's proposals

**(CodeRabbit backend only — `$PR_BACKEND == "coderabbit"`. Claude path skips to Step 8.)**

Fetch findings filtered to `commit_id == $HEAD_SHA`. For each inline comment: read the actual code at the cited line, verify CodeRabbit's premise, classify (🔴 Should fix / 🟡 Could fix / ⚪ Skip), and present with CodeRabbit's quoted text.

For the full verification process (7-pre zero-findings fast path, fetch commands, premise-check table, decision tree, present format, 7d-clean format):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-verification-classification.md`

Continue to Step 8.

**Stop after presenting.** This skill never auto-applies CodeRabbit suggestions.

## Step 8 — Confirm

```
PR opened for $TICKET.

PR:         #$PR ($BRANCH → $BASE) — $PR_URL
Commit:     <sha> [$TICKET] <subject>
Simplify:   <"clean — no changes needed" | "applied N changes (user confirmed)" | "skipped (--no-simplify)" | "skipped (no uncommitted changes)" | "user aborted">
Tests:      <"passed — N tests" | "skipped (--no-test)" | "skipped (user said skip)" | "failed but user said commit-anyway">
CC gate:    <"clean (max CC=N)" | "N violation(s) blocked and fixed" | "N violation(s) — benchmark-continue override" | "N elevated (CC W–T) — noted in PR body" | "skipped (radon not installed)">
Backend:    <"MCP" | "CLI ($GH)">
Review:     <"CodeRabbit — $N comments categorized above" | "CodeRabbit — clean ✅" | "CodeRabbit — timed out after 20 min" | "Claude /code-review --effort $PR_EFFORT [--fix] — findings posted to PR" | "skipped (--no-poll)">
```

## Rules

- **One confirmation per destructive remote action.** Step 1 may ask for confirmation if simplify made changes. Step 2 may pause if pre-commit hooks fail. Step 4 doesn't ask separately — pushing and creating the PR is the implicit confirmation that came from invoking this skill.
- **Never** `git push --force`, `git reset --hard`, `git commit --no-verify`, or `gh pr merge --admin`. None of those have a place in this flow.
- **Never auto-apply CodeRabbit suggestions in Step 6.** Present only. The user explicitly opts in.
- **All commits made by this skill are anchored to the active ticket** via `Refs: $TICKET` in the trailer.
- **Simplify is a soft prerequisite.** If unavailable, warn and ask the user to confirm continuing — not a hard stop.
- **Review backend is configured in `.project-conf.toml` `[pr_review]`.** Default is `coderabbit`.
- **CodeRabbit is a soft prerequisite.** If the PR is created but CodeRabbit never responds within 20 minutes, that's not a failure.
- **Claude review (`backend = "claude"`) requires the `code-review` skill to be available.** If unavailable, warn and ask continue/abort.
- **Failure handling per step:**
  - **Pre-flight fails**: stop. No state changed.
  - **Step 1 (simplify) unavailable**: warn, ask continue/abort.
  - **Step 1 (simplify) made changes**: ask user to confirm or abort.
  - **Step 2 (tests) command unknown** (user said `skip`): warn and continue.
  - **Step 2 (tests) fail**: refuse commit by default; offer `fix / commit anyway / abort`.
  - **Step 3 (commit) fails** (pre-commit hook): print hook output, stop.
  - **Step 4a (no backend found)**: stop with install instructions.
  - **Step 4b (push) fails**: stop. User resolves manually.
  - **Step 5b (PR creation) fails**: print error, stop.
  - **Step 5c (CodeRabbit trigger comment) fails**: warn but continue.
  - **Step 6 (poll timeout)**: not a failure — print and continue to Step 8.
  - **Step 6-claude (`code-review` skill unavailable)**: warn, ask continue/abort.
  - **Step 6-claude (`--fix` commit/push fails)**: print git output, stop.
  - **Step 7 (analysis)**: zero-findings case takes 7-pre / 7d-clean fast path. Non-zero takes 7-full path.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

For all autonomous prompt-skip decisions (simplify confirmation, test failure, red-findings fix loop, metrics emit):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-autonomous.md`
