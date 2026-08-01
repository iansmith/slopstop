---
description: Write the active ticket's Plan — Phase 0 red tests, codebase investigation, client-readable DoD, and parallelism-aware work items. Optional [constraint] arg scopes both investigation and plan. Confirms before fanout commit, agent launch, and merge.
disable-model-invocation: true
---

# /slopstop:plan

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Set `$PREFIX` (`prefix` field), `$SYSTEM` (`system` field). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Only operate on `$PREFIX-\d+` branches.

Resolve `$TRACKING_DIR` and `$ARCHIVE_DIR` **together**, via the shared resolution ladder:
→ Read `~/.claude/commands/slopstop-start-refs/tracking-dir-resolution.md`

Missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

If `[autonomous] enabled = true`: prompts skipped per **Autonomous behavior** at the bottom; otherwise unchanged.

## Arguments

`$ARGUMENTS` is an optional constraint scoping investigation and plan literally. Recorded at top of the Plan section. Empty = full ticket scope.

- `--no-adversary` — skip Step 0f (adversary gap finder). For speed runs where Phase 0 coverage is already trusted.
- `--inline` — run Step 0f and Step 1c inline without sub-agents, and **force serial execution in Step 3** (sub-worktree fanout from inside a delegated worktree agent is not supported). Use when `:plan` runs inside a delegated worktree agent, where sub-agent completion notifications route to the top-level loop instead of back to the spawning context.
- `--ticket-driven` — run the ticket-driven profile (below). Composes with `--inline`; fleet agents pass both.

## Profile selection (before Step 0)

If `--ticket-driven` was passed, **or** `task_plan.md`'s original-description snapshot carries all five sections of the leaf-ticket standard (Observable behaviors, File map, Definition of done, Out of scope, Test expectations), run the **ticket-driven profile** in place of Steps 0c–2 (0c-stub included — TD-3 carries its own stub step). Steps 0a–0b (test command + regression baseline) still run first — Step 3a's commit gates read both:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-ticket-driven.md`

The profile replaces open-ended investigation with checklist execution: the file map is the territory, red tests are transcribed from the ticket's Test expectations, and a wrong ticket triggers the `TICKET UNDERSPECIFIED` halt instead of improvisation. Steps 3+ resume as normal afterward. Absent the flag and the five sections, the default path below is untouched.

## Pre-flight (run in parallel)

- **Resolve the active ticket from the branch.** `$BRANCH = git branch --show-current`; find the first `$PREFIX-\d+` match (case-insensitive on `$PREFIX`, canonical-case the result) → `$TICKET`. No match → stop: `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."` Empty branch → `"No active $PREFIX ticket to plan. Run /slopstop:start first."`
- **In-flight check.** `$TRACKING_DIR/$TICKET/` must exist → else `"$TICKET is not in-flight. Run :start $TICKET first."` `task_plan.md` must exist → else state corruption, stop.
- On the main/master branch: refuse with `"Refusing to plan agent fanout from the main branch. Switch to a feature branch first."`
- `$BASE_SHA` = `git rev-parse HEAD` (the exact fork point if agents launch). `$TICKET_TITLE` = first heading of `task_plan.md`, minus the `# $TICKET — ` prefix.
- If `task_plan.md`'s `## Plan` already has content beyond the seeded `_(fill in as you scope the work)_` placeholder, ask: **replace / augment** (append below) **/ abort**. On `abort`: stop, nothing changed. Empty or seeded → proceed silently.

## Step 0 — Red tests first (TDD)

Write failing tests for the **expected behavior** before any investigation; they must fail on current code. **Prose-only changes are exempt** — a test asserting an English sentence appears in a markdown file pins wording, not behavior, and makes every later reword a red suite; structural invariants (a mirrored file matching its reference, a gate's derivation still present) are the narrow exception. Sub-steps 0a (test command) → 0b (regression baseline + expected behaviors) → 0c (write them) → 0c-stub (stubs for not-yet-existing surface, own commit — only when needed) → 0d (run and classify) → 0e (commit and **freeze**):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-phase0-mechanics.md`

**These two invariants stay in the spine deliberately** (BILL-278) — every known evasion works by never reading the file that states them:

- **Only tests observed FAILING at 0d may enter this commit.** Redness is a property of the baseline, not a knob: `on_phase0_tests_pass` governs what you do *next* and can never authorize freezing a green test. If nothing failed at 0d there is no Phase 0 commit — do not manufacture one. A green test frozen as the baseline makes every downstream diff clean by construction, which is the cheaper evasion than editing an assertion.
- **This commit freezes the tests.** Add tests freely; never change an expected value, loosen an assertion, skip or delete one, or amend/rebase the commit. `:pr` Step 2d and `:run`'s tamper check both read it as their baseline. If the ticket's expected value is itself wrong, take the `TICKET UNDERSPECIFIED` halt (TD-4a) — it consumes no attempt and is the only sanctioned alternative to editing the test.

### Step 0f — Adversary gap finder

Skipped only by `--no-adversary`.

With `--inline`, Step 0f still runs — via the inline fallback (work the six attack vectors yourself) rather than a spawned agent.

Otherwise spawn an adversary agent against the Phase 0 suite. In autonomous mode, `[autonomous] on_test_gaps` decides add-all / skip / ask. Agent prompt, attack vectors, inline fallback, RED verification, commit format:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-adversary-gaps.md`

## Step 1 — Investigation

Map the codebase relative to the ticket, scoped by `$ARGUMENTS`; write to `findings.md`. Sub-steps 1a (read existing context) → 1b (apply the constraint as a hard scope) → 1c (map the code, via `Explore` unless `--inline`) → 1d (write findings):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-investigation.md`

## Step 2 — Draft the Definition of Done and the technical plan

2a: a **client-readable** DoD — observable outcomes, no code symbols, each with a "How to verify" a non-coder can run. 2b: the technical Plan, detailed enough for a cold session, with per-item Files / Depends on / Parallel-safe with / Detailed steps / Done when, plus the parallelism analysis Step 3 reads. Both templates and their guidelines:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-dod-and-plan.md`

**Two items with overlapping files are NOT parallel-safe**, even when logically independent — Step 3 branches on this, so an optimistic answer produces conflicting worktrees. (Repeated from the reference deliberately: Step 3 reads the field, and a session that never opens the reference still has to get this right.)

## Step 3 — Decide: serial or parallel?

**If `--inline` was passed:** always serial, regardless of the parallelism analysis. Record the parallel-safe items in `task_plan.md` as planned, with `"serial execution (--inline mode)"` in Recommended execution.

**Otherwise**, read Step 2's parallelism analysis:

- **Fewer than 2 items parallel-safe with each other** → serial path.
  - **Non-autonomous:** print the serial hand-off (plan location, `:update` / `:pr` next steps). Committing during implementation is fine — `:pr` Step 1 and Step 2e scope to the branch diff, not the working tree. Template:
    → Read `~/.claude/commands/slopstop-plan-refs/plan-serial-impl.md`
    Then stop.
  - **Autonomous:** do NOT stop — continue to Step 3a.
- **2 or more parallel-safe** → continue to Step 4.

## Step 3a — Serial implementation (autonomous only)

Execute each work item in order, running the full suite after each. Commit only when the item's own Done-when tests are green **and** nothing in the regression baseline has regressed. Per-item loop, completion summary, WIP commit fallback:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-serial-impl.md`

## Step 4 — Pre-conditions for parallel fanout

Three hard gates before any worktree exists: **4a** clean working tree (commit / stash / abort), **4b** confirm the fork point `$BRANCH @ $BASE_SHA`, **4c** if the plan recommends **more than 4** agents (merge / proceed / abort):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-fanout.md`

## Step 5 — Draft per-agent prompts

For within-ticket fanout agents, draft a self-contained prompt from the template:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-agent-prompt.md`

For **fleet** agents (one agent per leaf ticket) use the Fleet agent brief in `design/slopstop-process.md` §7a instead — they run the base process through `:pr` (`:plan --ticket-driven --inline`, `:pr --inline`, decline the PR, never `:merge`), whereas the within-ticket template bans `/slopstop` commands outright.

## Step 6 — Confirm and launch

Present the plan plus per-agent decomposition and take **one** confirmation for the entire fanout: `yes` / `save-only` / `abort`. On `yes`, continue to Step 7.
→ Read `~/.claude/commands/slopstop-plan-refs/plan-fanout.md`

## Step 7 — Launch agents

Spawn one background worktree agent per parallel item (`isolation: "worktree"` is the enforcement mechanism, not a description), then record every agent's task id, worktree, and branch in `$TRACKING_DIR/$TICKET/.agents.json`. Exact invocation and state-file fields:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-fanout.md`

## Step 8 — Monitor (15-minute cadence; auto-stop hard-stuck)

Background monitor via the `Monitor` tool, polling every 15 min per agent: commits since the fork point, time since last commit, recent output for repeating errors. Auto-stop only when **both** 60+ min without commits **and** the same error 3+ times; a single condition is a warning. Full polling script and auto-stop logic:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-monitor-loop.md`

## Step 9 — Final report and auto-merge (with confirmation)

When all agents reach a terminal state, print per-agent status (done / stopped / errored, commit count, worktree, branch) and offer `merge all` / `merge specific <list>` / `skip` / `abort`. Dependency-order merge sequence, conflict-stop logic, merge command format:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-parallel-complete.md`

## Step 10 — Final confirm

Report what landed, what was skipped, and what the human still owns. Same reference as Step 9 (already loaded there):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-parallel-complete.md`

## Stage end — resume state and Next:

Before finishing — whether by the serial hand-off (Step 3, non-autonomous), the Step 3a completion summary (autonomous serial), or Step 10 (parallel fanout) — write resume state to `progress.md` and `task_plan.md` in `$TRACKING_DIR/$TICKET/` (resolved per `tracking-dir-resolution.md`, never re-derived here) and verify the write before printing the `Next:` line, in that order (C7). This is **advisory, not a gate** (D2): nothing above blocks or prompts, and running `:plan` again in a session that already ran it proceeds normally with no warning; the fleet's single headless process running `:plan` → `:pr` end to end continues to work with no required session boundary between stages (C6) — the advice is for a human picking the work back up cold, not a checkpoint the process itself must cross. On entry (Pre-flight), this stage rehydrates from `$TRACKING_DIR/$TICKET/` — `task_plan.md`, `progress.md`, `gates.json` — rather than from conversation state.
`Next: /slopstop:pr (fresh session)`.

## Rules

- Phase 0 mandatory unless the user says `skip` on the test command; passing unexpectedly → surface with `revise / continue / abort`, never proceed silently.
- `$ARGUMENTS` is literal; out-of-scope areas excluded from research and plan alike.
- Agents MUST use `isolation: "worktree"`.
- No auto-merge without an explicit `yes` in Step 9; stop on the first conflict, never `--force`.
- Plan saved before any agent launches — even if Steps 4 or 6 abort.
- `--inline` or `Explore` unavailable → inline `Grep`/`Glob`/`Read`.
- Step 4a commit fails → print hook output, abort fanout. Never `--no-verify`.
- Step 7 launch fails → stop; mark already-spawned agents as orphan in the state file.
- Monitor poll fails → retry next tick. Auto-merge conflict → stop, surface conflicted files and the remaining merge commands.

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`. Per-prompt decisions (`on_phase0_tests_pass`, `on_parallel_agents`, metrics emit):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-autonomous.md`
