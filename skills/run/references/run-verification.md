# Run: Handoff Verification (Step 6 detail)

A clean `:pr` review is necessary, never sufficient (`design/slopstop-process.md`
§7d): the agent's own pipeline hunts bugs and quality; the handoff hunts
**conformance** and **acceptability**, from the outside, at the medium tier.

## The two subagents

Both are **fresh** (no orchestrator conversation history), run on `[tiers].medium`,
and read the **actual artifacts** — the ticket body, the worktree, the diff between
the recorded fork SHA and the branch tip — **never the agent's claims** (its ticket
comments and PR description are the *subject* of scrutiny, not evidence).

Run both in parallel — they are independent, and because they only **read** (no
worktree of their own, no router env) they are spawned directly as orchestrator
subagents, not via the fleet's headless-CLI launch (Step 4's mechanism is for the
implementation agent, which writes).

### 1. Requirements adversary

Charter: *fail this work if you can.* Score the diff against the ticket's
**Definition of done** item by item, and each **Observable behavior**:

- criteria met only on paper (asserted in comments, absent in code),
- **vacuous tests** — transcribed red tests that pass without pinning the behavior
  (weakened assertions, testing the implementation instead of the expectation),
- **scope violations** — work outside the file map or the Out of scope fences
  (mechanically pre-checked by monitoring; judged here for substance),
- regressions in behavior the ticket said must stay green.

### 2. Code reviewer

Is the implementation acceptable — correctness of the changed code, no removed
invariants, honest error handling, house-style conformance. (The agent already ran
`:pr`'s inline review at the small tier; this is the medium-tier second opinion.)

## Verdict schema — the only thing that returns

Each subagent's final message is exactly:

```
VERDICT: PASS | FAIL
FINDINGS:                    (omit when PASS)
1. <file>:<line> — <specific defect> — <what would fix it>
...
```

**The orchestrator never ingests diffs** — findings and verdicts enter this context;
code does not (context economy, spec §9). If a finding needs more detail than a
file:line line can carry, the subagent writes it to
`scratch/runs/$RUN_ID/verdicts/<TICKET>-attempt<N>.md` and the finding cites that
file.

## On failure — the relaunch handoff

Either subagent FAILs → the attempt is spent:

1. Record both verdicts in `fleet-state.md` and post a verdict marker on the ticket.
2. Relaunch the agent (Step 4's mechanism) **in the same preserved worktree** — never
   a fresh clone; the code under correction is the starting point.
3. The new brief's findings slot carries the **specific findings verbatim**
   (file:line, quoted DoD items). A retry without new information is a wasted
   attempt — if there are no specific findings, something is wrong with the verdict,
   not the agent.
4. Budget accounting and the 2-failure diagnosis fork (rewrite vs escalation) are
   Step 7's — verification only verifies, records, and hands off.

Both PASS → the ticket is **blessed** and queues for Step 8 integration. Blessing binds
to a specific commit: record the branch **tip SHA at verdict time** in `fleet-state.md`
(the `verdicts` cell, e.g. `PASS@<sha>`) alongside the two verdicts. Step 8 re-checks the
tip before integrating — if it has advanced past the recorded blessed SHA (a relaunch,
rewrite, or salvage commit landed on the branch), the blessing is void and this handoff
verification re-runs on the new tip. Nothing else moves a preserved branch's tip (agents
never merge or rebase, §7a), so a sibling's serial integration never voids a blessing.
