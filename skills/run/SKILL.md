---
description: Stage 3 of the slopstop process — orchestrate the fleet against a G2-approved ticket tree, launching one hermetically-sealed worktree agent per leaf, integrating blessed work, and stopping at gate G-final. Medium-tier only. Invoke as /slopstop:run <run-id>.
disable-model-invocation: true
---

# /slopstop:run

Stage 3 of the slopstop process (`design/slopstop-process.md` §7). Runs on the
**medium tier**. Input: the run dir whose ticket tree passed G2. The orchestrator
never implements ticket work itself (single exception: human-authorized salvage) —
it launches, monitors, verifies, integrates, and reports.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `$PREFIX` (`prefix` field),
`[tiers]`, `[fleet.agents]`, `[fleet.monitoring]`, `[fleet.budget]`,
`[fleet.router]`, `tracking_dir`. Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Missing tables → the CONFIG.md defaults; missing
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
   (`GET /spend?prefix=$PREFIX&run=$RUN_ID` responds) → launch the agent with `ANTHROPIC_BASE_URL`
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
   cd <worktree> && ${ROUTED:+ANTHROPIC_BASE_URL=<router url>} \
     ${ROUTED:+ANTHROPIC_CUSTOM_HEADERS=$'X-Slopstop-Run: '"$RUN_ID"$'\nX-Slopstop-Ticket: '"$TICKET"} \
     claude -p "<the filled brief>" \
       --model <[fleet.agents].model> \
       --effort <[fleet.agents].effort> \
       --permission-mode auto \
       --allowedTools <[fleet.agents].allowed_tools> <ticket's test-command grants> \
       ${OUTSIDE_TRACKING_DIR:+--add-dir <resolved tracking dir>}
   ```

   (via Bash `run_in_background`). The Agent tool is **not** suitable here: it has no
   per-subagent env (router injection would silently not happen), and its worktree
   isolation creates its own temp worktree — monitoring would watch the wrong
   directory.

   Each flag is load-bearing; a missing one fails the agent silently, not loudly:

   - `--model` / `--effort` — this CLI supports both, so effort is **enforced**, not
     advisory. (Supersedes the old `ANTHROPIC_MODEL=` recipe and the spec §1 caveat.)
   - `--permission-mode auto` — `acceptEdits` auto-approves *file edits only*. It does
     not approve `Bash`, so under it the agent cannot read its ticket, transition it,
     comment, or push. `auto` alone is **also** insufficient: it still gates `gh`.
   - `--allowedTools` — the scoped grant that makes `auto` workable. The base list comes
     from `[fleet.agents].allowed_tools` (default `Bash(gh:*)`, `Bash(git:*)`: the ticket
     read/transition/comment/PR path, plus commits). **Append the ticket's own test
     command**, read from the `Test command:` line of its **Test expectations** section —
     `cd router && go test ./...` yields `Bash(go:*)`, `python3 -m pytest` yields
     `Bash(python3:*)`. Omitting it denies the agent's test step, which monitoring sees
     only as an agent gone quiet. Prefer widening this list over reaching for
     `bypassPermissions` — a fleet agent should not hold a blanket shell grant.
   - `--add-dir <resolved tracking dir>` — required **whenever `tracking_dir` resolves
     outside the agent's worktree**, which is the normal case: a relative `tracking_dir`
     resolves from the *main* worktree root (`dirname "$(git rev-parse --git-common-dir)"`),
     so every agent's tracking dir is outside its own tree. Without the grant, `:start`'s
     seeding is denied and the agent invents a local one.
   - **Never point `tracking_dir` inside `~/.claude/`.** That path is protected: the
     `Write` tool refuses it *even with* a matching `--add-dir`. See CONFIG.md.

   The brief:
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

## Step 6 — Verify at the handoff

When an agent reports done (clean `:pr`, PR declined), trust nothing: spawn two fresh
medium-tier subagents — a **requirements adversary** (conformance vs the ticket's DoD
and behaviors) and a **code reviewer** (implementation acceptability). Both read the
actual worktree and diff; both return verdict-only structured results. Either fails →
relaunch in the same preserved worktree with the findings cited (consumes an attempt).
Prompts, verdict schema, and the relaunch handoff:
→ Read `~/.claude/commands/slopstop-run-refs/run-verification.md`

## Step 7 — Failure handling: budgets, rewrites, escalation, G4

Every kill and every failed handoff verdict consumes an attempt against
`[fleet.budget]`. After two failures on a ticket, diagnose: ticket defect → rewrite
(with the mandatory huge-tier delta check before any relaunch); capability gap →
one escalated-model attempt. Budget exhaustion → gate **G4** (the human's
more-attempts / rewrite / salvage / abandon call) while the fleet keeps running
every independent ticket. Full rubric, delta-check prompt, and G4 template:
→ Read `~/.claude/commands/slopstop-run-refs/run-failure-handling.md`

## Step 8 — Integrate, drift-check, report, G-final

Blessed tickets integrate **serially, in dependency order**, via `:merge <TICKET>`
from the root checkout — after re-checking each blessing's `PASS@<sha>` against the
branch tip. Each completed umbrella gets a report + a fresh large-tier drift check.
When everything lands: the final report (PRD §10), its omission-hunting huge-tier
adversary, and the **G-final** stop. Full procedure and templates:
→ Read `~/.claude/commands/slopstop-run-refs/run-final-report.md`

## Rules

- Medium tier only. The orchestrator implements nothing (salvage excepted, §7e).
- Fleet state lives on disk; verdicts and markers, never diffs, enter this context.
- A dead router degrades cost reporting, never a launch.
- Launch nothing that isn't briefed on its ticket; launch nothing whose blockers
  haven't landed.
