---
description: Stage 3 of the slopstop process — orchestrate the fleet against a G2-approved ticket tree, launching one hermetically-sealed worktree agent per leaf, integrating blessed work, and stopping at gate G-final. Medium-tier only. Invoke as /slopstop:run <run-id>.
disable-model-invocation: true
---

# /slopstop:run

Stage 3 of the slopstop process (`design/slopstop-process.md` §7). Runs on the
**medium tier**. Input: the run dir whose ticket tree passed G2. The orchestrator
never implements ticket work itself (single exception: human-authorized salvage) —
it launches, monitors, verifies, integrates, and reports.

> Skeleton scope (BILL-175): tier gate, tree intake, launch ordering, briefing +
> launch, router injection, fleet state. Sibling tickets dock here: monitoring +
> kill authority (BILL-176), handoff verification (BILL-177), failure handling +
> budgets + G4 (BILL-178), integration + final report + G-final (BILL-179).

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `key` (`$PREFIX`),
`[tiers]`, `[fleet.agents]`, `[fleet.monitoring]`, `[fleet.budget]`,
`[fleet.router]`, `tracking_dir`. Missing tables → the CONFIG.md defaults; missing
config file → stop with the standard gh-init message.

## Arguments

`$RUN_ID` — required in effect (handed off by `:tickets`' G2 report). If empty: list
`scratch/runs/*/` and ask; never guess. The run dir must show a G2-passed state in
`run.md`; if not: stop with `"Run $RUN_ID has not passed G2 — run /slopstop:tickets first."`

**Fleet precondition:** the project config must have `[autonomous] enabled = true`
with `branch_type` set. Fleet agents are headless — `:start`'s interactive branch-type
and base-ref prompts (Steps 4b/4c) would stall an agent until monitoring kills it.
If not set: stop with `"Fleet agents require [autonomous] enabled = true and
branch_type in .project-conf.toml — headless agents cannot answer interactive
prompts."`

## Step 1 — Tier gate

Same three-branch gate as `:tickets` (match `[tiers].medium` / hard stop on mismatch /
ask on cannot-determine, recorded in `run.md`). This session holds **autonomous kill
authority** over fleet agents — the gate is why that authority is safe to hold.

## Step 2 — Intake the tree

From `run.md`'s letter→key map and the ticket system: fetch every leaf and umbrella,
their five sections, `Blocked by:` relations, and current states. Build the work
ledger in `scratch/runs/$RUN_ID/fleet-state.md` — **the source of truth for the whole
run**; the conversation window is disposable (context economy, spec §9):

```markdown
# Fleet state — run $RUN_ID
| ticket | version | attempts | agent | worktree | branch | fork SHA | last marker | verdicts | status |
```

Update it on **every event** (launch, marker, kill, verdict, rewrite, merge). Any
wake-up re-reads it from disk before acting.

## Step 3 — Launch order

Compute the dependency-first order — file affinity from the tickets' file maps plus
explicit relations; disjoint maps run in parallel, overlaps serialize onto the
updated tip, explicit dependencies always win:
→ Read `~/.claude/commands/slopstop-run-refs/run-launch-order.md`

## Step 4 — Brief and launch (per leaf, in order)

For each ticket whose blockers are all integrated:

1. **Router check — at each agent launch** (`[fleet.router]`): enabled + healthy
   (`GET /spend?run=$RUN_ID` responds) → launch the agent with `ANTHROPIC_BASE_URL`
   pointed at the router and `$RUN_ID` carried per request (header or `/r/$RUN_ID`
   prefix). Disabled or unreachable → launch direct; note `"cost tracking
   disabled/unavailable"` once per report, never block the launch.
2. **Create the worktree** off the current primary tip:
   `git worktree add <path> -b <TYPE>/<TICKET> <primary>` where `<TYPE>` =
   `[autonomous].branch_type` — the same value the agent's `:start` resolves, so its
   Step 5a finds the branch already checked out and switches cleanly instead of
   inventing a second branch. Record the fork SHA and branch in `fleet-state.md`
   (the branch name later resolves to a *moved* tip; the SHA is the truth).
3. **Post the briefing comment on the ticket** (the contract surface): reporting
   channel = comments on this ticket, every slopstop command + material work unit
   announced. **No briefing comment = not briefed = do not launch.**
4. **Launch the agent** as a **headless CLI session in the worktree**, backgrounded:

   ```bash
   cd <worktree> && ANTHROPIC_MODEL=<[fleet.agents].model> \
     ${ROUTED:+ANTHROPIC_BASE_URL=<router url>} \
     claude -p "<the filled brief>" --permission-mode acceptEdits
   ```

   (via Bash `run_in_background`). The Agent tool is **not** suitable here: it has no
   per-subagent env (router injection would silently not happen), and its worktree
   isolation creates its own temp worktree — monitoring would watch the wrong
   directory. Effort is passed where the CLI supports it; otherwise it's advisory
   (spec §1 caveat). The brief:
   → Read `~/.claude/commands/slopstop-run-refs/run-agent-brief.md`
5. Record the launch (agent pid/task id, worktree, branch, fork SHA) in
   `fleet-state.md`.

One agent ⇄ one ticket ⇄ one branch ⇄ one worktree. Never bundle.

## Step 5 — Monitor: autonomous kill authority

While agents run, poll every `[fleet.monitoring].poll_interval_min` minutes: read new
ticket comments and peek each live worktree, evaluate the four config-bound triggers
(quiet → investigate; silence → kill; loop → kill; file-map violation → instant kill,
or log in `"warn"` mode), and update `fleet-state.md`. Kills are autonomous — they
consume an attempt, get recorded with their reason, and feed the relaunch brief; they
never interrupt the human. Full loop, trigger semantics, and kill procedure:
→ Read `~/.claude/commands/slopstop-run-refs/run-monitoring.md`

## Step 6 — Verify at the handoff (BILL-177)

Two fresh medium-tier subagents (requirements adversary + code reviewer), verdict-only
returns. *Docks here.*

## Step 7 — Failure handling (BILL-178)

Budgets `[fleet.budget]` (3 × 3 × 1), diagnosis, rewrites + big-tier delta checks,
tier escalation, G4. *Docks here.*

## Step 8 — Integrate and report (BILL-179)

Serial `:merge <TICKET>` from the root, umbrella drift checks, the final report + its
big-tier adversary, gate G-final. *Docks here.*

## Rules

- Medium tier only. The orchestrator implements nothing (salvage excepted, §7e).
- Fleet state lives on disk; verdicts and markers, never diffs, enter this context.
- A dead router degrades cost reporting, never a launch.
- Launch nothing that isn't briefed on its ticket; launch nothing whose blockers
  haven't landed.
