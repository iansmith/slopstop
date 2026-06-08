---
description: Write the active ticket's Plan — Phase 0 red tests, codebase investigation, client-readable DoD, and parallelism-aware work items. Optional [constraint] arg scopes both investigation and plan. Confirms before fanout commit, agent launch, and merge.
disable-model-invocation: true
---

# /slopstop:plan

## Project scope

Read `.project-conf.toml`. Set `$PREFIX = key`, `$SYSTEM = system`. Only operate on `$PREFIX-\d+` branches.
Missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

If `[autonomous] enabled = true`: prompts skipped per **Autonomous behavior** section; otherwise unchanged.

## Arguments

`$ARGUMENTS` is an optional constraint scoping investigation and plan literally. Recorded at top of Plan section. Empty = full ticket scope.

The active ticket is parsed from `git branch --show-current` (see Pre-flight). If empty: `"No active $PREFIX ticket to plan. Run /slopstop:start first."` and stop.

## Pre-flight (run in parallel)

- **Resolve active ticket from branch.** Parse `$TICKET` from the current git branch:
  - `$BRANCH = $(git branch --show-current)`
  - Find the first match of `$PREFIX-\d+` in `$BRANCH` (case-insensitive on `$PREFIX`; canonical-case the result).
  - No match → stop with `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."`
  - Match → `$TICKET` (e.g. `MAZ-43`, `BILL-2`).
- **In-flight check.** Verify `~/.claude/ticket-active/$TICKET/` exists. If not: stop with `"$TICKET is not in-flight. Run :start $TICKET first."`
- Verify `~/.claude/ticket-active/$TICKET/task_plan.md` exists. If not: state corruption — stop.
- `$BRANCH` = `git branch --show-current`. If on the main/master branch: refuse with `"Refusing to plan agent fanout from the main branch. Switch to a feature branch first."`
- `$BASE_SHA` = `git rev-parse HEAD` (the exact fork point if we end up launching agents).
- `$TICKET_TITLE` = first heading line of `task_plan.md`, stripped of the `# $TICKET — ` prefix.

Check if `task_plan.md`'s `## Plan` section already has content (anything beyond the seeded `_(fill in as you scope the work)_` placeholder):

- **Empty/seeded** — proceed silently.
- **Non-empty** — ask the user:
  > `## Plan` already has content. Replace, augment (append below the existing plan), or abort?

  On `abort`: stop. No state changed.

## Step 0 — Red tests first (TDD)

Write failing tests for the **expected behavior** before any investigation. Tests must fail on current code.

### 0a. Identify the test command for the project

Look in `task_plan.md` for a `**Test command:**` line. If present, use it. Otherwise auto-detect from the cwd:

| Indicator | Test command |
|---|---|
| `Taskfile.yml` with a `test:` task | `task test` |
| `Makefile` with a `test:` target | `make test` |
| `package.json` with a `"test"` script + `pnpm-lock.yaml` | `pnpm test` |
| `package.json` with a `"test"` script + `yarn.lock` | `yarn test` |
| `package.json` with a `"test"` script (else) | `npm test` |
| `Cargo.toml` | `cargo test` |
| `go.mod` | `go test ./...` |
| `pyproject.toml` with pytest config | `pytest` |

If none match (or multiple plausibly do), ask once: `"What's the test command? (paste it, or 'skip')"`. On a real answer, cache by writing `**Test command:** <cmd>` at the top of `task_plan.md`. On `skip`: warn and continue to Step 1 without Phase 0.

### 0b. Establish the regression baseline and identify expected behaviors

Run the existing test suite first. Record as **regression baseline**: `N passing, M failing, K errors` (pre-existing failures noted separately).

Read `task_plan.md`'s `## Original description`. List expected behaviors, constrained by `$ARGUMENTS`.

### 0c. Write the red tests — prioritize edge cases

Find where existing tests live. Add new tests for the expected behavior. Each test must have a clear name, use existing framework/fixtures, and actually exercise the behavior (no stubs, no skipped tests).

**Write in this priority order** (most commonly missed first): edge/boundary → error/rejection → cross-feature interaction → happy-path. Full guidance with examples:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-red-tests.md`

Record test file path(s) and names (used as Done-when criteria in Step 2).

### 0d. Run the tests; report results

Run the test command from 0a. One of three outcomes:
- **All new tests fail** → RED state established. Print results and continue to Step 1.
- **Some or all pass** → surface to user with revise/continue/abort options.
- **Tests don't run** → stop with captured error output.

For the exact output format templates for each outcome:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-test-results.md`

### 0e. Commit the red tests

Commit Phase 0 tests in their RED state as a separate commit before moving on.

```
git add <test-files-from-0c>
git commit -m "[$TICKET] Phase 0: red tests for <one-line summary of behaviors>" \
           -m "These tests describe the expected post-fix behavior. They fail on current code." \
           -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

If the working tree had unrelated uncommitted changes before Phase 0 ran, do NOT include them in this commit — only stage the red-test files explicitly by path.

## Step 1 — Investigation

Goal: map the codebase relative to the ticket, scoped by `$ARGUMENTS`. Writes findings to `findings.md`.

### 1a. Read existing context

- `task_plan.md`'s `## Original description (snapshot at start)` section.
- `findings.md` — any prior investigation. Read but don't duplicate it.
- (Optional) Re-fetch the ticket fresh from Linear/JIRA for the current description, if it may have been edited since start.

### 1b. Apply the constraint

If `$ARGUMENTS` non-empty: hard scope — excluded areas MUST NOT be investigated. Note in findings header.

### 1c. Map the relevant code

Use the `Explore` subagent for the heavy lifting (keeps orchestrator context clean):

```
Agent(subagent_type: "Explore", description: "Investigate $TICKET", prompt: <see template below>)
```

For the full Explore prompt template (5-question investigation format scoped to the ticket + constraint):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-explore-prompt.md`

If `Explore` is unavailable, fall back to inline `Grep`/`Glob`/`Read` on the same five questions.

### 1d. Write findings

Append to `findings.md`:

```markdown
## Investigation <UTC timestamp>

**Constraint:** $ARGUMENTS (or "none — full ticket scope")

### Relevant modules
### Entry points
### Dependencies
### Constraints to honor
### Risks
```

## Step 2 — Draft the Definition of Done and the technical plan

### 2a. Draft the Definition of Done (client-readable)

Plain language, observable outcomes. Write ABOVE `## Original description` (shows at top of ticket after `:archive`).

Format:

```markdown
## Definition of Done

This ticket will be considered complete when ALL of the following are true and observable:

1. **<plain-language outcome — what changes from the client's perspective>**
   How to verify: <a concrete check the client can do without reading code>

2. **<plain-language outcome>**
   How to verify: <observable check>

If any of these aren't true at delivery, the ticket isn't done.
```

Guidelines: observable outcomes only — no code symbols, test names, or jargon. "How to verify" must be executable without code knowledge. 2–5 items. Reflect any `$ARGUMENTS` scope drop.

### 2b. Draft the technical Plan

Write into `task_plan.md`'s `## Plan` section (replacing or augmenting per pre-flight choice). Detailed enough a separate session can execute items cold.

Format:

```markdown
## Plan

**Constraint:** $ARGUMENTS (or "none — full ticket scope")

### Work items

1. <descriptive name>
   - **Files:** <files this item creates, modifies, or deletes>
   - **Depends on:** <ids of items that must complete first, or "none">
   - **Parallel-safe with:** <ids it can run alongside; explain why>
   - **Detailed steps:**
     a. <concrete sub-step>
   - **Done when:** <verification criteria — preferably red tests from Phase 0 turning green>

### Parallelism analysis

- **Items eligible for parallel execution:** <list>
- **Sequential dependencies:** <list>
- **Recommended execution:** <"serial" | "parallel: N agents covering items [list]; serial integration after">
```

Two items with overlapping files are NOT parallel-safe even if logically independent. "Parallel-safe with" must reflect actual file-level disjointness.

## Step 3 — Decide: serial or parallel?

Look at the parallelism analysis from Step 2:

- **Fewer than 2 items are parallel-safe with each other** → serial path.

  **Non-autonomous:** Print:
  ```
  Serial execution — no agents needed.
  Plan written to ~/.claude/ticket-active/$TICKET/task_plan.md.
  Run /slopstop:update as you go to checkpoint progress; /slopstop:pr when ready.
  ```
  Stop.

  **Autonomous** (`[autonomous] enabled = true`): do NOT stop. Continue to Step 3a — serial implementation.

- **2 or more items are parallel-safe** → continue to Step 4 (parallel path).

## Step 3a — Serial implementation (autonomous only)

Execute each work item in order, running the full test suite after each. Commit only when both the item's own Done-when tests are green AND no regression-baseline tests have regressed.

For the complete per-item loop, completion summary format, and WIP commit fallback:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-serial-impl.md`

## Step 4 — Pre-conditions for parallel fanout

Before doing anything that requires worktrees, three hard gates:

### 4a. Clean working tree

`git status --porcelain`. If non-empty, offer three choices: `commit` (create a WIP checkpoint commit, re-capture `$BASE_SHA`, continue), `stash` (`git stash push -m "$TICKET pre-fanout"`, remind user to pop after), or `abort`.

### 4b. Confirm the fork point

Ask: `"Agents will fork from $BRANCH @ $BASE_SHA in isolated worktrees. Is this the right base? (yes / abort)"` On `abort`: stop.

### 4c. Agent count cap

If the plan recommends >4 parallel agents, offer: `merge` (combine items into ≤4 units), `proceed` (run all K), or `abort`.

## Step 5 — Draft per-agent prompts

For each parallel item, draft a self-contained prompt using the template at:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-agent-prompt.md`

The template covers: task slice, context from investigation, hard worktree constraints, verification criteria, and reporting instructions.

## Step 6 — Confirm and launch

Present the full plan + per-agent decomposition: ticket, item count, per-agent name/files/done-when summary, fork point. **One confirmation** for the entire fanout: `yes` (create worktrees, launch agents, monitor), `save-only` (plan saved; execute manually), or `abort` (plan still saved).

On `save-only` or `abort`: stop with appropriate message. On `yes`: continue to Step 7.

## Step 7 — Launch agents

For each parallel item, spawn a background worktree agent:

```
Agent(subagent_type: "general-purpose", isolation: "worktree", run_in_background: true,
      description: "Agent <id> on $TICKET", prompt: <per-agent prompt from Step 5>)
```

Capture each agent's task ID and resolved worktree path. Record state in `~/.claude/ticket-active/$TICKET/.agents.json` with fields: `id`, `task_id`, `worktree`, `branch`, `items`, `status` (`running`), `started_at`, `last_check_at`, `last_commit_at`, `commits`, `stop_reason`.

Print launch confirmation with agent worktree paths, branches, and task IDs.

## Step 8 — Monitor (15-minute cadence; auto-stop hard-stuck)

Run a background monitor via the `Monitor` tool. Polls every 15 min per agent: count commits since fork point, time since last commit, recent output for repeating errors.

Auto-stop only when BOTH: (a) 60+ min without commits AND (b) same error repeated 3+ times. Single condition = warning only.

For the complete polling script and auto-stop logic:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-monitor-loop.md`

## Step 9 — Final report and auto-merge (with confirmation)

When all agents reach terminal state, print per-agent status (done/stopped/errored, commit count, worktree, branch). Offer `merge all / merge specific <list> / skip / abort`.

For agent dependency-order merge sequence, conflict-stop logic, and merge command format:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-parallel-complete.md`

## Step 10 — Final confirm

→ Read `~/.claude/commands/slopstop-plan-refs/plan-parallel-complete.md` (Step 10 is included there)

## Rules

- Phase 0 mandatory unless user says `skip` on test command.
- Phase 0 passes unexpectedly → surface with `revise / continue / abort`; don't proceed silently.
- Auto-stop: BOTH 60+ min no commits AND same error 3+ times. Single condition = warning only.
- `$ARGUMENTS` is literal; out-of-scope excluded from research and plan.
- Agents MUST use `isolation: "worktree"` — the `Agent(isolation: "worktree")` parameter is the enforcement mechanism, not just a description.
- No auto-merge without explicit yes in Step 9; stop on first conflict, never `--force`.
- Plan saved before any agent launches — even if Steps 4/6 abort.
- `Explore` unavailable → fall back to inline `Grep`/`Glob`/`Read`.
- Step 4a commit fails → print hook output, abort fanout. Never `--no-verify`.
- Step 7 agent launch fails → stop; mark already-spawned as orphan in state file.
- Monitor poll fails → retry on next tick.
- Auto-merge conflict → stop, surface conflicted files and remaining merge commands.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

For per-prompt decisions (on_phase0_tests_pass, on_parallel_agents, metrics emit):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-autonomous.md`
