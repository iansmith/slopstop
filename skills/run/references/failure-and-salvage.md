# Failure, recovery, and salvage — the one definition

4.0.0's failure model is *"stop the ticket, keep the others running."* That is a good
simplification of a bad situation, but on its own it means **a failed ticket yields
nothing**: the work is discarded and the attempt is unrepeatable. This file is what a
stopped ticket leaves behind, and what can be done with it.

Recovered for BILL-467 from the pre-4.0.0 machinery. Its governing sentence:

> A retry without new information is a wasted attempt.

## What a stopped ticket preserves — all of it, always

A ticket stops for a `GOAL DEFECT`, a 🔴 gate, a `TAMPER FAIL`, a `FILEMAP FAIL`, a
`HANDOFF FAIL`, a `REVIEW BLOCKED`, a capped review loop, or a blocked DoD. Whichever it is,
**nothing is cleaned up**:

- **The branch stays.** Never deleted, never reset, never force-updated.
- **Every commit the failed attempt made stays.** Reset to the fork SHA **only** on an
  explicit human diagnosis that the approach itself is unsalvageable — *never the default*.
- **The worktree stays**, where the run uses one. *"Never clean it on a kill."* Worktrees are
  removed only after integration or on human-approved abandon. `git worktree remove` detaches
  without deleting the branch, so the teardown order is `remove` then `branch -D` — and on a
  failure neither runs.
- **The tracking dir stays**, with `run.jsonl` closed `failed` and the reason on the span.
- **The findings stay, verbatim.** Not a summary. The exact text the check returned.

Record the preserved location as a `note` so the next session finds it without searching:

```json
{"ticket":"BILL-501","event":"note","stage":"preserved","at":"…",
 "branch":"feat/BILL-501","fork_sha":"<sha>","tip_sha":"<sha>",
 "worktree":"<path or null>","commits":4,"reason":"HANDOFF FAIL: 2"}
```

The branch name later resolves to a *moved* tip; **the SHA is the truth**. Record both.

## A retry carries the prior findings verbatim

A relaunch brief contains the previous attempt's findings, quoted, not paraphrased and not
summarised. Paraphrasing a finding is how a retry ends up re-solving a problem that was
already understood.

> If there are no specific findings, something is wrong with the verdict, not the agent.

A verdict that stopped a ticket and cannot say what to fix is itself the defect. Treat an
empty finding list as a reason to re-run the check, not as a reason to retry the work.

## Two failures is a diagnosis point, not a third attempt

`:run` already stops a ticket that fails implementation twice and says it may be a **ticket**
defect rather than a code defect. That rule is the attempt budget, and it now covers
verification failures too — a handoff that fails twice is the same signal.

**No new config key.** The pre-4.0.0 `[fleet.budget]` table (`max_attempts_per_version`,
`max_ticket_versions`, `max_tier_escalations`) is **not** reintroduced: it was deleted with
the fleet launcher, and reintroducing a `[fleet.*]` table would resurrect vocabulary for
machinery that no longer exists. The cap that matters is already behaviour.

At the diagnosis point, fork on **why**:

- **Ticket defect** → `/slopstop:tickets --rewrite <TICKET>`. Bad tickets are a ticket-stage
  defect, not an implementation failure. A `TICKET UNDERSPECIFIED` result — detected as a
  literal final line from a worker — routes straight here and **consumes no attempt at all**.
  The agent-side framing is worth restating in any brief: *"That is a legitimate, cost-free
  outcome. Silently 'correcting' the test is not — it is the single worst thing you can do in
  this process."*
- **Capability gap** → escalate the tier for the next attempt, once.

**Record the classification.** It is also the run's evaluation data: bad tickets and weak
models look identical in a failure count and completely different in a ledger that says
which one it was.

A rewritten ticket is a **new contract** — fresh agent, fresh budget, **the same preserved
branch**. The rewrite itself belongs to `:tickets`, which captures the outgoing body first
and runs a mandatory `scope-subtraction` delta check before the ticket system is touched. The
orchestrator does not author tickets.

## Reporting a stopped ticket

Never fold it in with the completed ones. Present, per stopped ticket:

- the verdict that stopped it, and the findings verbatim;
- the diagnosis (ticket defect / capability gap / undiagnosed);
- the preserved branch, fork SHA, tip SHA, worktree path, and commit count;
- what it needs from the human: `more attempts`, `rewrite`, `salvage`, `abandon`.

**The run does not stop** — only the blocked subtree waits. Every independent ticket keeps
going, and the stopped set is reported together at the end.

## SALVAGE — human-authorized only

The single exception to *"the orchestrator implements nothing."* It requires an explicit
human instruction naming the ticket; it is never entered autonomously, and never inferred
from a report.

The orchestrator picks up the **preserved branch** and follows the normal base process on it:

1. Read the preserved findings. **They are the acceptance criterion** — the salvage is done
   when it closes the specific gap the handoff adversary named, not when the suite is green.
2. Work the branch as the process requires. The frozen tests are still frozen; `$FROZEN` is
   still the original Phase 0 commit. **A salvage may not edit a frozen test** — that
   restriction does not relax because a human authorised the salvage.
3. Then **decline the PR exactly as an agent would**, and send the branch back through the
   whole pipeline: gates, review, and handoff verification again.

> Salvaged code goes through the same quality pipeline as everything else, not around it.

Because the salvage lands commits, the branch tip advances — so any earlier blessing is void
by construction and handoff verification re-runs. That is the mechanism working, not an
inconvenience to route around.

**Preserved into a salvage:** the branch, every commit the failed attempt made, and the
findings. **Reset:** nothing.
