# Agent effort capability audit (BILL-333)

Answers the open question that shapes BILL-333: which of slopstop's tier-resolved
spawn sites can actually carry a reasoning-effort value, and which cannot. Ground
truth is the tool schemas available to the session doing the spawning — a spawn
site can only pass what its underlying mechanism accepts.

## Verdict summary

| Mechanism | Effort param? | Evidence |
|---|---|---|
| In-session `Agent(...)` tool call | **cannot** carry effort | Tool schema for `Agent` exposes `description`, `isolation`, `model`, `prompt`, `run_in_background`, `subagent_type` — no `effort` field. |
| Fleet CLI launch (`claude -p --model ... --effort ...`) | **can** carry effort | `skills/run/SKILL.md:131-147` — the CLI accepts both `--model` and `--effort`, and this is already enforced today via `[fleet.agents].effort` / `adversary_effort`. |
| `/code-review` via `Skill({skill: "code-review", args: "--effort $PR_EFFORT ..."})` | **can** carry effort | `skills/pr/references/pr-claude-review.md` — the skill invocation already threads a literal `--effort` flag; only its resolution needed the fallback chain (BILL-333 Item 7). |

**Every spawn site in this ticket's file map that spawns via a bare `Agent(...)`
call is incapable of carrying an effort value in the current harness.** This is
not a gap in those skills' implementations — the underlying tool has no effort
parameter to pass. If a future harness version adds one to `Agent`, this audit is
the file to update alongside re-enabling Behavior 5 for the newly-capable sites.

## Per-site verdicts

### `skills/tickets/references/tickets-adversary.md`

Ticket-tree adversary spawn: `"Spawn with the model for the ticket-adversary tier"`
— a bare `Agent(...)` call. **Cannot** carry effort. Resolves `adversary_effort`
through the fallback chain (BILL-333 Item 8) so the *value* is computed correctly
even though it currently has nowhere to go; ready for the day `Agent` gains an
effort parameter.

### `skills/single-ticket/SKILL.md`

Single-ticket adversary orchestration — same shape as `tickets-adversary.md`, a
bare `Agent(...)` call. **Cannot** carry effort.

### `skills/single-ticket/references/single-ticket-adversary.md`

"Spawn with the model for the ticket-adversary tier" — bare `Agent(...)`.
**Cannot** carry effort. Same treatment as `tickets-adversary.md` (Item 8): the
`adversary_effort` chain is resolved and documented even though nothing consumes
it yet.

### `skills/run/references/run-failure-handling.md`

The huge-tier delta check, spawned inline via `Agent(...)` at "the same effort"
as the failed attempt (prose only — no mechanism to actually pass one). **Cannot**
carry effort.

### `skills/run/references/run-final-report.md`

Two spawn points: the umbrella drift check (§8b) and the final-report adversary
(§8d), both bare `Agent(...)` calls at their resolved tier. **Cannot** carry
effort, either one.

### `skills/run/references/run-verification.md`

Per-leaf handoff verifier spawns, run "as orchestrator" (in-session), bare
`Agent(...)`. **Cannot** carry effort.

### `skills/plan/references/plan-investigation.md`

`Agent(subagent_type: "Explore", description: "Investigate $TICKET", prompt:
<template>)` — a literal, visible `Agent(...)` call with the exact same schema as
every other site above. **Cannot** carry effort.

## What Behaviors 4-5 actually do, given this audit

Behavior 4 (the fallback chain) is real, functioning work regardless of this
finding — `[pr_review].effort` and `[fleet.agents].effort`/`adversary_effort` are
resolved *values* consumed by mechanisms (the CLI, `/code-review`) that already
accept effort, or (for `adversary_effort`) computed correctly and ready for the
day the in-session spawn mechanism gains an effort parameter.

Behavior 5 ("every spawn site the audit marks capable passes its resolved
effort") applies to exactly two sites: the fleet CLI launch and `/code-review`,
both already effort-capable and already wired (fleet CLI pre-existing;
`/code-review` fixed by Item 7's chain). The six `Agent(...)` sites above each get
the one-line comment this section anchors: incapable, see this audit.
