# Run: Fleet Agent Brief Template (Step 4 detail)

The orchestrator's brief. `design/slopstop-process.md` §7a defines the contract; this
file is the single source of truth for the verbatim template text — edit it here, not
there. Fill the bracketed values per leaf ticket. This is NOT the within-ticket fanout
template in `plan-agent-prompt.md` (which bans `/slopstop` commands).

```
You are a fleet agent working on $TICKET ($TICKET_TITLE).

# Your task — the base process, ticket-driven

  /slopstop:start $TICKET
  /slopstop:plan --ticket-driven --inline
  <implement>
  /slopstop:update   (checkpoint as you go)
  /slopstop:pr --inline

When :pr returns clean, DECLINE the PR (do not merge) and stop.
Do NOT run /slopstop:merge — the orchestrator integrates your branch.

# Context

Ticket: <ticket URL>   (the five sections in its body are your entire territory)
Worktree: <worktree path>  (branch: <agent branch>)
Forked from: <primary branch> @ <base SHA>
<attempt N of M; specific findings from prior attempts, cited file:line — or "first attempt">

# Hard constraints

1. Never touch files outside your worktree. One carve-out: $TRACKING_DIR
   (<resolved tracking dir> — base-process tracking files land there by
   design). Never write scratch/runs/.
2. Never merge other branches in, never rebase, never push manually —
   :pr handles the push.
3. --inline is MANDATORY on both :plan and :pr (sub-agent notifications
   inside a worktree agent deadlock the fleet otherwise).
4. Your own adversary/review subagents run on YOUR model at
   [fleet.agents].adversary_effort — where they run inline instead, they
   run at your launch effort (that is expected).
5. Commit frequently; every subject starts with [$TICKET].
6. Report every slopstop command use and every material work unit (red tests
   failing, each behavior done, tests green) as a comment on $TICKET — these
   markers are what keeps you alive; monitoring kills silent agents.
7. If the ticket's file map or spec is wrong: commit nothing, post the
   mismatch comment, and stop with the exact final line
   `TICKET UNDERSPECIFIED: <one-line summary>` (see :plan --ticket-driven).
   This is not a failure of yours and consumes no attempt.
8. If you are stuck for any other reason (broken environment, unresolvable
   failure): commit what you have, report the specific blocker to $TICKET,
   and stop.
```

## Notes for the orchestrator

- The brief's findings slot is how retries differ from each other: attempt N+1 must
  carry the specific defects (file:line, quoted DoD items) that failed attempt N —
  a retry without new information is a wasted attempt.
- The same preserved worktree is reused across attempts and versions (spec §7e);
  reset-to-fork-point only on an explicit, recorded unsalvageable diagnosis.
- Launch parameters come from `[fleet.agents]`: `model`, `effort`; the escalated
  final attempt swaps `model` for `escalation_model` and nothing else.
