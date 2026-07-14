---
description: PR the active ticket branch — simplify → test → commit → push → create PR → review (CodeRabbit, Greptile, or Claude /code-review). Backend via [pr_review] in .project-conf.toml (default coderabbit). Loops on 🔴/🟡 findings (fix → simplify → commit → re-poll) until clean. ⚪ findings presented for human judgment.
disable-model-invocation: true
---

# /slopstop:pr

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Set `$PREFIX` (`prefix` field), `$SYSTEM` (`system` field). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Only operate on `$PREFIX-\d+` branches.

Also read `tracking_dir` (optional): resolve to `$TRACKING_DIR`. If absent or equal to `~/.claude/ticket-active`, default to `~/.claude/ticket-active`. If a relative path (no leading `/` or `~/`), resolve from `dirname "$(git rev-parse --git-common-dir)"`. Absolute paths (starting with `/` or `~/`) are used as-is. **Guard:** if the resolved path lies under `~/.claude/`, warn `"tracking_dir resolves under ~/.claude, a protected path — headless agents cannot write there even with a matching --add-dir. Set a project-local path (e.g. \".slopstop/ticket-active\")."` and continue. The legacy default works interactively; it silently breaks fleet agents.

Missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

If `[autonomous] enabled = true`: prompts skipped per **Autonomous behavior** section; otherwise unchanged.

## Arguments

Optional `--base <branch>` to override the PR target branch (default: the repo's default branch — usually `master` or `main`).
Optional `--no-simplify` to skip Step 1's simplify pass.
Optional `--no-test` to skip Step 2's pre-commit test run **and** Step 2d's slop-detection gate.
Optional `--no-poll` to skip the review step entirely (both backends).
Optional `--no-adversary` to skip Step 2d's slop-detection gate.
Optional `--inline` to run simplify (Step 1), slop detection (Step 2d), and Claude code review (Step 6-claude) without spawning sub-agents — all reasoning executes in the current context. Use when `:pr` runs inside a delegated worktree agent where sub-agent completion notifications are routed to the top-level loop rather than back to the spawning context. Has no effect on CodeRabbit polling (Step 6-cr), CC gate, or pre-PR health gate.

The active ticket is parsed from `git branch --show-current` (see Pre-flight). If empty: `"No active $PREFIX ticket to PR."` and stop.

## Pre-flight (run in parallel)

- **Resolve active ticket from branch.** Parse `$TICKET` from the current git branch:
  - `$BRANCH = $(git branch --show-current)`
  - Find the first match of `$PREFIX-\d+` in `$BRANCH` (case-insensitive on `$PREFIX`; canonical-case the result).
  - No match → stop with `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."`
  - Match → `$TICKET` (e.g. `MAZ-43`, `BILL-2`).
- **In-flight check.** Verify `$TRACKING_DIR/$TICKET/` exists. If not: stop with `"$TICKET is not in-flight. Run :start $TICKET first."`
- `$BRANCH` = `git branch --show-current`. If on the main/master branch: refuse with `"Refusing: on the main branch, not a feature branch."`
- `$DIRTY` = `git status --porcelain` (used in Step 1 and Step 2).
- `$DEFAULT_BRANCH` = `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name` (cache for Step 4c).
- `$BASE` = `--base` argument if given, else `base-branch` from `.project-conf.toml` if present, else `$DEFAULT_BRANCH`.
- **`[pr_review]` config** — read from `.project-conf.toml` (all fields optional):
  - `$PR_BACKEND` = `pr_review.backend` if present, else `"coderabbit"`. Valid values: `"coderabbit"`, `"greptile"`, `"claude"`.
  - `$PR_EFFORT`  = `pr_review.effort`  if present, else `"high"` (Claude only).
  - `$PR_FIX`     = `pr_review.fix`     if present, else `false`  (Claude only).
  - `$PR_CR_FIX`  = `pr_review.coderabbit_fix` if present, else `true` (CodeRabbit only — set to `false` for presentation-only behavior, reverting to the old never-auto-apply mode).
  - `$PR_GR_FIX`  = `pr_review.greptile_fix`   if present, else `true` (Greptile only — set to `false` for presentation-only behavior).
- **Remote config** — read from `.project-conf.toml` (both optional, default `"origin"`):
  - `$PR_REMOTE`     = `pr-remote` if present, else `"origin"`. Feature branches are pushed to this remote.
  - `$ORIGIN_REMOTE` = `origin-remote` if present, else `"origin"`. PR is opened against this remote's repo.
- **GitHub repo** — read from `.project-conf.toml` (optional, falls back to `key`):
  - `$OWNER` and `$REPO` = `pr-repo` if present (e.g. `"iansmith/lyos"`), else parse from `key` (e.g. `"iansmith/slopstop"` → `$OWNER=iansmith`, `$REPO=slopstop`).

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

Snapshot diff before and after; compare. Identical → continue silently. Different → show delta and ask `continue / abort`.

`--inline`: inline simplify procedure. Otherwise: invoke code-simplifier agent.

For the snapshot commands, Agent invocation block, inline procedure, and before/after diff comparison logic:
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

Skip this step if `--no-adversary` or `--no-test` was passed.

**Do NOT skip on a clean working tree.** `$DIRTY` being empty means nothing is *uncommitted* — not that nothing was *done*. Test tampering is committed work, so a clean tree is precisely when this gate must still run.

The gate has two halves:

- **2d-i — Red-test tamper diff.** Mechanical, runs first, and runs **regardless of `$DIRTY`**. Diffs the test files across the commit range since the Phase 0 red-test commit (`:plan` Step 0e). A changed expected value, a removed or skipped test, or **no Phase 0 commit at all** is 🔴.
- **2d-ii — Slop-pattern review.** Judgment, runs second, over the uncommitted diff. Skip only this half if `$DIRTY` is empty. `--inline`: run inline (uses `$INLINE_DIFF` from Step 1 if `--no-simplify` was not passed; otherwise re-runs `git diff HEAD`). Otherwise: spawn a slop-detection agent.

For the tamper-diff shell, the full slop-pattern catalog, inline procedure, 🔴/🟡 classification, override record format, and autonomous path:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-slop-detection.md`

**Gate behavior summary:**
- 🔴 findings (test manipulation, expectation inversion, test deletion, red-test assertion changed after the RED commit, no RED commit at all): hard stop. Require explicit `override` from user with a reason. Record to `pipeline.json`. In autonomous mode, consult `[autonomous] on_slop_findings`.
- 🟡 findings (implementation testing, tautological tests, scope creep, fake error handling): surface and warn. User can proceed without override.
- Clean: silent pass, proceed to Step 3.

This gate runs in the agent's **own** session, so it is a self-check: an agent that already rationalized rewriting an assertion will rationalize reviewing it. That is why 2d-i is a mechanical diff rather than a judgment, and why `:run` re-checks it from outside at Gate 0 (`run-verification.md`).

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

MCP: call the create-pull-request tool with `owner=$OWNER, repo=$REPO` (the canonical repo from `pr-repo` if set, else `key`). CLI: use HEREDOC with `$GH pr create --repo $OWNER/$REPO` so the PR targets the canonical repo even when `$PR_REMOTE` (the push remote) points at a personal fork. Capture `$PR` and `$PR_URL`. Print: `"PR created: $PR_URL (target: $BASE)"`.

### 5c. Trigger review bot (CodeRabbit / Greptile backend only)

Skip if `$PR_BACKEND == "claude"` or `--no-poll`.

If `$BASE != $DEFAULT_BRANCH`: post the backend-specific trigger comment (`@coderabbitai review` for CodeRabbit, `@greptile review` for Greptile). On failure: warn and continue.

Skipping the trigger (auto-review repos) is NOT the same as skipping the poll. Step 6-cr / Step 6-greptile run regardless — auto-review is not self-verifying.

## Step 6 — Review pass (backend-dependent)

**Skip entirely if `--no-poll` was passed.** Continue to Step 8.

Dispatch on `$PR_BACKEND`:
- **`"coderabbit"`** → Step 6-cr (runs regardless of 5c trigger), then Step 7.
- **`"greptile"`** → Step 6-greptile (runs regardless of 5c trigger), then Step 7.
- **`"claude"`** → Step 6-claude, then Step 8.

---

## Step 6-cr — Poll for CodeRabbit feedback

**This step runs unconditionally** — whether or not the `@coderabbitai review` trigger was posted in Step 5c. Auto-review is not self-verifying.

Poll for a `coderabbitai[bot]` walkthrough comment referencing `$HEAD_SHA` (the reliable completion signal for both first and incremental reviews). Poll every 60 s, up to 20 iterations.

For the complete polling implementation (shell script, first-vs-incremental trap explanation, timeout handling, clean-incremental-pass note):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-cr-polling.md`

## Step 6-greptile — Poll for Greptile feedback

**This step runs unconditionally** — whether or not the `@greptile review` trigger was posted in Step 5c. Auto-review is not self-verifying.

Poll for a `greptile-dev[bot]` review referencing `$HEAD_SHA` (completion signal: a submitted PR review by that bot). Poll every 60 s, up to 20 iterations.

For the complete polling implementation (shell script, execution model, timeout handling, post-loop findings routing):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-greptile-polling.md`

## Step 6-claude — Claude code review

`--inline`: run the code review inline (see pr-claude-review.md). Otherwise: build args `--effort $PR_EFFORT --comment` (add `--fix` if `$PR_FIX == true`) and invoke `Skill({skill: "code-review", args: ...})`.

For the full invocation blocks, inline procedure, and `--fix` commit/push flow:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-claude-review.md`

---

## Step 7 — Verify, classify, and present bot review findings

**(CodeRabbit or Greptile backend. Claude path skips to Step 8.)**

Set `$BOT_NAME` = `coderabbitai[bot]` (CodeRabbit) or `greptile-dev[bot]` (Greptile). Set `$BOT_FIX` = `$PR_CR_FIX` (CodeRabbit) or `$PR_GR_FIX` (Greptile).

For each inline comment from `$BOT_NAME`: read the actual code at the cited line, verify the premise, classify (🔴 Should fix / 🟡 Could fix / ⚪ Skip), and present with the bot's quoted text.

For the full process (7-pre zero-findings fast path, fetch commands, premise-check table, decision tree, present format, 7d-clean format):
→ CodeRabbit: Read `~/.claude/commands/slopstop-pr-refs/pr-verification-classification.md`
→ Greptile: Read `~/.claude/commands/slopstop-pr-refs/pr-greptile-polling.md` (Step 7 section)

After presenting: if `$BOT_FIX == true` (default) and 🔴/🟡 findings exist → proceed to Step 7e (fix-and-iterate loop). If `$BOT_FIX == false`: stop after presenting. ⚪ findings are always for human judgment. Continue to Step 8 when the bot returns clean or the loop limit is reached.

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
Review:     <Bot (CodeRabbit/Greptile): "{Bot} — {outcome}" where outcome ∈ {"clean ✅ (1 round)" | "clean ✅ after N rounds" | "N ⚪ findings presented (no 🔴/🟡 to apply)" | "loop limit reached after 5 rounds, N finding(s) remain" | "timed out after 20 min" | "N 🔴/🟡 findings presented, not applied ({backend}_fix=false)"}. Claude: "Claude /code-review --effort $PR_EFFORT [--fix] — clean after N rounds" | "Claude /code-review --effort $PR_EFFORT — N findings posted (fix=false)". Or: "skipped (--no-poll)">
```

## Rules

- Never `git push --force`, `git reset --hard`, `git commit --no-verify`, or `gh pr merge --admin`.
- Auto-apply 🔴 and 🟡 findings in the fix-and-iterate loop (Step 7e) when `$PR_CR_FIX == true` (CodeRabbit) or `$PR_GR_FIX == true` (Greptile). Set `coderabbit_fix = false` or `greptile_fix = false` for presentation-only behavior. Only ⚪ findings are always presented for human judgment.
- All commits anchored to `$TICKET` via `Refs: $TICKET` trailer.
- Review backend: `[pr_review].backend` in `.project-conf.toml`, default `coderabbit`. Valid: `coderabbit`, `greptile`, `claude`.
- Simplify unavailable → warn + ask (soft prerequisite; not a hard stop).
- CodeRabbit / Greptile timeout (20 min) → not a failure; continue to Step 8.
- Claude review requires `code-review` skill; unavailable → warn + ask continue/abort.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

For all autonomous prompt-skip decisions (simplify confirmation, test failure, red-findings fix loop, metrics emit):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-autonomous.md`
