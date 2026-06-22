---
description: PR the active ticket branch — simplify → test → commit → push → create PR → review (CodeRabbit or Claude /code-review). Backend via [pr_review] in .project-conf.toml (default coderabbit). Loops on 🔴/🟡 findings (fix → simplify → commit → re-poll) until clean. ⚪ findings presented for human judgment.
disable-model-invocation: true
---

# /slopstop:pr

## Project scope

Read `.project-conf.toml`. Set `$PREFIX = key`, `$SYSTEM = system`. Only operate on `$PREFIX-\d+` branches.
Missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

If `[autonomous] enabled = true`: prompts skipped per **Autonomous behavior** section; otherwise unchanged.

## Arguments

Optional `--base <branch>` to override the PR target branch (default: the repo's default branch — usually `master` or `main`).
Optional `--no-simplify` to skip Step 1's simplify pass.
Optional `--no-test` to skip Step 2's pre-commit test run **and** Step 2d's slop-detection gate.
Optional `--no-poll` to skip the review step entirely (both backends).
Optional `--no-adversary` to skip Step 2d's slop-detection gate.

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
  - `$PR_CR_FIX`  = `pr_review.coderabbit_fix` if present, else `true` (CodeRabbit only — set to `false` for presentation-only behavior, reverting to the old never-auto-apply mode).
- **Remote config** — read from `.project-conf.toml` (both optional, default `"origin"`):
  - `$PR_REMOTE`     = `pr-remote` if present, else `"origin"`. Feature branches are pushed to this remote.
  - `$ORIGIN_REMOTE` = `origin-remote` if present, else `"origin"`. PR is opened against this remote's repo.
- **GitHub repo** — parse `$OWNER` and `$REPO` from `.project-conf.toml`'s `key` field (e.g. `"iansmith/slopstop"` → `$OWNER=iansmith`, `$REPO=slopstop`).

If an open PR already exists for `$BRANCH` (`gh pr list --head $BRANCH --state open --repo $OWNER/$REPO` returns ≥1), refuse: `"PR already exists for $BRANCH: <url>. Use /slopstop:merge to ship it, or push more commits to update."`

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

Check for over-complex functions in source files modified by this PR.

**Tool: `lizard`** — pip-installable, multi-language CC tool.

Compute `CHANGED_CODE` = source files (lizard-supported extensions) modified since branch point. If `CHANGED_CODE` is empty: **skip this gate.**

Read thresholds from `.project-conf.toml`:
- `cc_warn_threshold` (default: **10**) — 🟡 elevated boundary
- `cc_reject_threshold` (default: **15**) — 🔴 hard-gate threshold

**Decision:** If 🔴 violations exist: hard stop (interactive) or benchmark-continue (autonomous, with `pipeline.json` record and `⚠️ BENCHMARK OVERRIDE (CC)` PR body note). If only 🟡 elevated: proceed; append a **Complexity notes** section to the PR body. If `CHANGED_CODE` empty or `lizard` unavailable: skip.

For the full shell implementation (`BASE_SHA` computation, `CHANGED_CODE` detection, lizard auto-install cascade, `CC_JSON` parsing, lizard JSON fields, `NEW_FUNC_NAMES` extraction, CC report format, benchmark override record JSON):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-cc-gate.md`

## Step 1 — Simplify pass on uncommitted changes

Skip if `--no-simplify` was passed, OR if `$DIRTY` is empty (nothing to simplify).

Snapshot diff before and after; invoke code-simplifier agent; compare. Identical → continue silently. Different → show delta and ask `continue / abort`.

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

- **Pass** (exit 0): print `"Tests passed. Continuing to commit."` and proceed to Step 2d.
- **Fail** (non-zero exit): print failures, then offer `fix / commit anyway / abort`. On `fix` or `abort`: stop. On `commit anyway`: continue to Step 2d with a `Note: <N> test(s) failing at commit time` body line.

## Step 2d — Slop-detection pre-commit gate

Skip this step if `--no-adversary` or `--no-test` was passed, or if `$DIRTY` is empty (nothing to scan).

Spawn a slop-detection agent to review the current diff (uncommitted changes) against the Phase 0 red tests in `task_plan.md`. The agent hunts for AI-specific cheating patterns that make tests pass without actually solving the problem.

For the full slop-pattern catalog, 🔴/🟡 classification, override record format, and autonomous path:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-slop-detection.md`

**Gate behavior summary:**
- 🔴 findings (test manipulation, expectation inversion, test deletion): hard stop. Require explicit `override` from user with a reason. Record to `pipeline.json`. In autonomous mode, consult `[autonomous] on_slop_findings`.
- 🟡 findings (implementation testing, tautological tests, scope creep, fake error handling): surface and warn. User can proceed without override.
- Clean: silent pass, proceed to Step 3.

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

- No upstream: `git push -u $PR_REMOTE $BRANCH`.
- Ahead of upstream: `git push $PR_REMOTE $BRANCH`.
- In sync: skip push.

On push failure: stop with git output verbatim. Never `git push --force`.

## Step 5 — Create the PR

### 5a. Build title and body

- **Title**: `[$TICKET] <summary>` (from most recent commit subject).
- **Body**: `## Summary` (1–3 bullets), `## Ticket` (URL), `## Test plan` (checklist).

### 5b. Create the PR

MCP: call the create-pull-request tool with `owner=$OWNER, repo=$REPO` (the canonical repo from `key`). CLI: use HEREDOC with `$GH pr create --repo $OWNER/$REPO` so the PR targets the canonical repo even when `$PR_REMOTE` (the push remote) points at a personal fork. Capture `$PR` and `$PR_URL`. Print: `"PR created: $PR_URL (target: $BASE)"`.

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

After presenting: if `$PR_CR_FIX == true` (default) and 🔴/🟡 findings exist → proceed to Step 7e (fix-and-iterate loop). If `$PR_CR_FIX == false`: stop after presenting. ⚪ findings are always for human judgment. Continue to Step 8 when CodeRabbit returns clean or the loop limit is reached.

## Step 8 — Confirm

```
PR opened for $TICKET.

PR:         #$PR ($BRANCH → $BASE) — $PR_URL
Commit:     <sha> [$TICKET] <subject>
Simplify:   <"clean — no changes needed" | "applied N changes (user confirmed)" | "skipped (--no-simplify)" | "skipped (no uncommitted changes)" | "user aborted">
Tests:      <"passed — N tests" | "skipped (--no-test)" | "skipped (user said skip)" | "failed but user said commit-anyway">
Slop gate:  <"clean ✅" | "🔴 N finding(s) — override: <reason>" | "🟡 N warning(s) — proceeded" | "skipped (--no-adversary)" | "skipped (--no-test)" | "skipped (no uncommitted changes)" | "skipped (on_slop_findings=skip)">
CC gate:    <"clean (max CC=N)" | "N violation(s) blocked and fixed" | "N violation(s) — benchmark-continue override" | "N elevated (CC W–T) — noted in PR body" | "skipped (lizard not installed)">
Backend:    <"MCP" | "CLI ($GH)">
Review:     <"CodeRabbit — clean ✅ (1 round)" | "CodeRabbit — clean ✅ after N rounds" | "CodeRabbit — N ⚪ findings presented (no 🔴/🟡 to apply)" | "CodeRabbit — loop limit reached after 5 rounds, N finding(s) remain" | "CodeRabbit — timed out after 20 min" | "CodeRabbit — N 🔴/🟡 findings presented, not applied (coderabbit_fix=false)" | "Claude /code-review --effort $PR_EFFORT [--fix] — clean after N rounds" | "Claude /code-review --effort $PR_EFFORT — N findings posted (fix=false)" | "skipped (--no-poll)">
```

## Rules

- Never `git push --force`, `git reset --hard`, `git commit --no-verify`, or `gh pr merge --admin`.
- Auto-apply 🔴 and 🟡 findings in the fix-and-iterate loop (Step 7e) when `$PR_CR_FIX == true` (default). Set `[pr_review] coderabbit_fix = false` for presentation-only behavior. Only ⚪ findings are always presented for human judgment.
- All commits anchored to `$TICKET` via `Refs: $TICKET` trailer.
- Review backend: `[pr_review].backend` in `.project-conf.toml`, default `coderabbit`.
- Simplify unavailable → warn + ask (soft prerequisite; not a hard stop).
- CodeRabbit timeout (20 min) → not a failure; continue to Step 8.
- Claude review requires `code-review` skill; unavailable → warn + ask continue/abort.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

For all autonomous prompt-skip decisions (simplify confirmation, test failure, red-findings fix loop, metrics emit):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-autonomous.md`
