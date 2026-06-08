---
description: Replace the active ticket's empty Plan section with a thorough, parallelism-aware plan grounded in real codebase investigation, starting with a Phase 0 that writes RED tests for the expected behavior. Also drafts a client-readable Definition of Done (plain-language observable outcomes) that ends up at the top of the ticket description on archive. Use /slopstop:plan [constraint] — the optional textual constraint scopes BOTH the investigation and the resulting plan literally. Phase 0's red tests anchor each work item's "Done when" criteria. The skill confirms before destructive actions (commit before fanout, agent launch, auto-merge); auto-stops hard-stuck agents (60+ min no commits AND repeating errors); never auto-merges without your explicit yes.
disable-model-invocation: true
---

# /slopstop:plan

Replace `task_plan.md`'s empty `## Plan` section with a thorough plan grounded in actual codebase investigation. Phase 0 writes red tests for the expected behavior FIRST, so the plan's "Done when" criteria are objective (a named test turning green) rather than prose-assertion. When the plan has parallel-safe work items, optionally fan them out across subagents in git worktrees and orchestrate them.

Three explicit confirmation gates: before committing on the user's behalf (if tree is dirty), before launching agents, before auto-merging.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd. Extract `key` (Linear team key, JIRA project key, or GitHub `owner/repo`) and call it `$PREFIX`. Also note `system` (`linear` | `jira` | `github`) for downstream logic.

**Only operate on `$PREFIX`'s tickets. The branch-IS-selection parser only matches `$PREFIX-\d+`, so a branch encoding a different project's prefix correctly fails the no-match check.**

If `.project-conf.toml` is missing in cwd: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill skips interactive prompts by consulting the config instead of asking. If `[autonomous]` is absent or `enabled = false`, behavior is unchanged. See **Autonomous behavior** at the bottom of this file for the per-prompt decisions.

## Arguments

`$ARGUMENTS` is an optional textual constraint that scopes both the investigation and the resulting plan **literally** — out-of-scope work is excluded even if the ticket text suggests it. Examples: `focus on the database layer only`, `minimize changes to existing tests`, `must use the existing config system`. The constraint is recorded at the top of the Plan section. If empty, the plan covers everything implied by the ticket.

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

**Before** any investigation or planning, write failing tests for the **behavior the ticket says we want** — not for the current implementation. This is TDD's RED phase: tests are written based on the expected post-fix behavior and should fail on the current code.

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

If none match (or multiple plausibly do), ask the user once: `"What's the test command for this project? (paste it, or 'skip' to skip Phase 0)"`. On a real answer, **cache it** by writing a `**Test command:** <cmd>` line into `task_plan.md` (top of the file's frontmatter block, before `## Original description`). On `skip`: warn and continue to Step 1 without Phase 0.

### 0b. Establish the regression baseline and identify expected behaviors

**First — run the existing test suite** before writing any new tests. Record the result as the **regression baseline**: `N passing, M failing, K errors`. Any tests already failing are _pre-existing failures_ — note them separately. Only tests passing NOW can regress.

**Then** read `task_plan.md`'s `## Original description` carefully. List the behaviors the ticket claims should hold. If `$ARGUMENTS` constrains the scope, only include behaviors within the constraint.

### 0c. Write the red tests — prioritize edge cases

Find where existing tests live. Add new tests for the expected behavior. Each test must have a clear name, use existing framework/fixtures, and actually exercise the behavior (no stubs, no skipped tests).

**Write in this priority order** (most commonly missed first): edge/boundary → error/rejection → cross-feature interaction → happy-path. Full guidance with examples:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-red-tests.md`

Record the test file path(s) and test names — they're referenced in the plan in Step 2 as the verification criteria for work items.

### 0d. Run the tests; report results

Run the test command from 0a. One of three outcomes:
- **All new tests fail** → RED state established. Print results and continue to Step 1.
- **Some or all pass** → surface to user with revise/continue/abort options.
- **Tests don't run** → stop with captured error output.

For the exact output format templates for each outcome:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-test-results.md`

### 0e. Commit the red tests

Once Phase 0's tests are in their RED state, commit them as a separate commit *before* moving on. This locks in the behavioral specification.

```
git add <test-files-from-0c>
git commit -m "[$TICKET] Phase 0: red tests for <one-line summary of behaviors>" \
           -m "These tests describe the expected post-fix behavior. They fail on current code." \
           -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

If the working tree had unrelated uncommitted changes before Phase 0 ran, do NOT include them in this commit — only stage the red-test files explicitly by path.

## Step 1 — Investigation

Goal: understand the codebase as it relates to the ticket's outcome, scoped by `$ARGUMENTS`. Writes findings to `findings.md`. Phase 0's red tests anchor what "done" means — investigation should keep them in mind.

### 1a. Read existing context

- `task_plan.md`'s `## Original description (snapshot at start)` section.
- `findings.md` — any prior investigation. Read but don't duplicate it.
- (Optional) Re-fetch the ticket fresh from Linear/JIRA for the current description, if it may have been edited since start.

### 1b. Apply the constraint

If `$ARGUMENTS` is non-empty, treat it as a hard scope. Areas explicitly excluded MUST NOT be investigated. Note the constraint in the investigation header so the next reader understands what's out of scope.

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

Two related artifacts get written to `task_plan.md`: a client-readable **Definition of Done** (Step 2a) followed by the detailed technical **Plan** (Step 2b). Both come from the same source — ticket description + Phase 0 red tests + Phase 1 investigation — but they speak to different audiences.

### 2a. Draft the Definition of Done (client-readable)

Audience: the person who filed the ticket and anyone reading it later. **Plain language, observable outcomes**, not implementation criteria. Write it ABOVE `## Original description` so it appears at the top of the ticket description after `:archive` pushes the body.

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

Guidelines: items describe what the client will observe, not what the engineer builds. Each `How to verify:` must be executable without code knowledge. No jargon, no test names, no internal class names. 2–5 items typical. If `$ARGUMENTS` drops scope, the DoD must reflect that explicitly.

### 2b. Draft the technical Plan

Write into `task_plan.md`'s `## Plan` section. The plan must be detailed enough that a separate Claude session could pick up an item without re-reading the codebase.

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

- **Phase 0 is mandatory** unless the user explicitly says `skip` when asked for the test command. The "Done when" criteria in the Step-2 plan are anchored to red tests turning green — without them, the plan loses its objective verification.
- **`task_plan.md` ends up with two complementary artifacts**: the client-readable Definition of Done (Step 2a) and the technical Plan (Step 2b). The DoD is what the client reads; the Plan is what the engineer reads.
- **Phase 0 surprises matter**: if the red tests pass on current code, surface that to the user. Either the bug is already fixed, or the tests aren't exercising the right behavior.
- **Three confirmation gates**: Step 4 (clean tree + base SHA + agent count), Step 6 (launch agents), Step 9 (auto-merge). The user can abort at any of them.
- **Worktree isolation is the contract**: agents are told the constraint in their prompt, and `Agent(isolation: "worktree")` enforces it at the tool level.
- **Conservative auto-stop**: 60+ min no commits AND repeating errors. **Both** must be true. Single-condition signals flag but don't auto-stop.
- **`$ARGUMENTS` is literal**: out-of-scope work is excluded from both research and plan. The constraint is recorded at the top of the Plan section.
- **No auto-merge without explicit yes** in Step 9. Stops cleanly on first conflict and never `--force`s.
- **Plan is always saved before agents launch** — even if Steps 4 / 6 abort or all agents fail.

### Failure handling

- **Pre-flight fails**: stop with reason. No state changed.
- **Phase 0 test command unknown** (user said `skip`): warn and continue without Phase 0.
- **Phase 0 tests pass unexpectedly**: surface to user with `revise / continue / abort` prompt. Don't proceed silently.
- **Phase 0 tests don't run**: stop. User fixes the test harness and re-runs.
- **Phase 0 commit fails**: print hook output, stop.
- **Investigation `Explore` subagent unavailable**: fall back to inline `Grep`/`Glob`/`Read`.
- **Plan write fails**: stop. Plan must be persisted before anything else.
- **Step 4a commit fails**: print hook output, abort the fanout flow. Never `--no-verify`.
- **Step 7 agent launch fails**: stop, mark already-spawned agents as orphan in state file.
- **Monitor poll fails**: retry on next tick. Don't crash the monitor.
- **Agent auto-stop**: log the reason in state, emit a notification, continue monitoring others.
- **Auto-merge conflict**: stop merge sequence, surface conflicted files and remaining merge commands.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

For per-prompt decisions (on_phase0_tests_pass, on_parallel_agents, metrics emit):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-autonomous.md`
