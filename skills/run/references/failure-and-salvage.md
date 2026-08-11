# Failure, recovery, and salvage — the one definition

4.0.0's failure model is *"stop the ticket, keep the others running."* That is a good
simplification of a bad situation, but on its own it means **a failed ticket yields
nothing**: the work is discarded and the attempt is unrepeatable. This file is what a
stopped ticket leaves behind, and what can be done with it.

Recovered for BILL-467 from the pre-4.0.0 machinery. Its governing sentence:

> A retry without new information is a wasted attempt.

## What a stopped ticket preserves — all of it, always

A ticket stops for a `GOAL DEFECT`, a 🔴 gate, a `TAMPER FAIL`, a `FILEMAP FAIL`, a
an exhausted attempt cap after a `HANDOFF DROP`, a `REVIEW BLOCKED`, a capped review loop, or
a blocked DoD. Whichever it is,
**nothing is cleaned up**:

- **The branch stays.** Never deleted, never reset, never force-updated.
- **Every commit the failed attempt made stays.** Reset to the fork SHA **only** on an
  explicit human diagnosis that the approach itself is unsalvageable — *never the default*.
- **The worktree stays.** *"Never clean it on a kill."* Worktrees are removed only after
  integration or on human-approved abandon. `git worktree remove` detaches without deleting
  the branch, so the teardown order is `remove` then `branch -D` — and on a failure neither
  runs.

  This said *"where the run uses one"* until 2026-08-11. BILL-535 made worktrees
  **unconditional** — every ticket, including a single serial one — so the qualifier named a
  case that no longer exists, and it named it in the one file that runs when something has
  already gone wrong. A preservation rule holding itself open to "unless there wasn't a
  worktree" is exactly the kind an orchestrator reaches for while explaining a stop.

  **Lock it, in the same step that records the stop:**

  ```bash
  git worktree lock <path> --reason "slopstop: preserved failed attempt <TICKET> — <verdict>"
  ```

  Not belt-and-braces. Claude Code runs a periodic sweep over worktrees it created, and the
  documented guarantee is narrow: it *"never releases a lock you set yourself with `git
  worktree lock`."* Its other skip condition — that it *"skips a worktree that still holds
  work: changed or untracked files, or unpushed commits"* — reads like it already covers us,
  and for most stops it does. **It does not cover the stops that happen late.** A ticket that
  fails at a capped review loop, a `HANDOFF DROP`, or a bot finding has already had its
  commits pushed by the orchestrator and holds no uncommitted changes, so every skip condition
  is satisfied and the worktree is sweepable. The rule above says *never* clean it; without
  the lock, *never* depends on the attempt having failed early enough.

  Take the lock even where the sweep would not currently reach — the lock is one command and
  costs nothing, and the alternative is a preservation rule whose correctness rests on an
  implementation detail of somebody else's cleanup schedule. **Release it only on the
  human-approved abandon** that also removes the worktree, and it changes the teardown order
  above. A locked worktree cannot be removed by `git worktree remove`, and **`--force` alone
  does not override it** — measured:

  ```
  git worktree remove wt          -> fatal: cannot remove a locked working tree
  git worktree remove --force wt  -> fatal: cannot remove a locked working tree,
                                     use 'remove -f -f' to override or unlock first
  ```

  So the abandon sequence is **`unlock` → `remove` → `branch -D`**, three steps, in that
  order. `git worktree remove -ff` also works and is the wrong habit: it discards the lock
  without ever reading its reason, which is the one thing recording the reason was for.
- **The tracking dir stays**, with `run.jsonl` closed `failed` and the reason on the span.
- **The findings stay, verbatim.** Not a summary. The exact text the check returned.

Record the preserved location as a `note` so the next session finds it without searching:

```json
{"ticket":"BILL-501","event":"note","stage":"preserved","at":"…",
 "branch":"feat/BILL-501","fork_sha":"<sha>","tip_sha":"<sha>",
 "worktree":"<path>","commits":4,"reason":"HANDOFF DROP: 2 (attempt 3 of 3)"}
```

The branch name later resolves to a *moved* tip; **the SHA is the truth**. Record both.

## A retry carries the prior findings verbatim

A relaunch brief contains the previous attempt's findings, quoted, not paraphrased and not
summarised. Paraphrasing a finding is how a retry ends up re-solving a problem that was
already understood.

> If there are no specific findings, something is wrong with the verdict, not the agent.

A verdict that stopped a ticket and cannot say what to fix is itself the defect. Treat an
empty finding list as a reason to re-run the check, not as a reason to retry the work.

## Three attempts, and the second failure is still a diagnosis point

> **REVISED 2026-08-10 (BILL-535).** This section was headed *"Two failures is a diagnosis
> point, not a third attempt."* The budget is now **three**; the diagnosis point stays exactly
> where it was. The heading was the thing that changed, not the fork.

**The budget is three attempts: one on a clean brief, then two carrying findings.** The
diagnosis fork below still fires after the **second** failure, and the third attempt
**follows** it rather than replacing it.

That ordering is the whole point, and picking the other one would have been the mistake. The
old rule refused a third attempt because a third *blind* attempt just repeats the second —
same brief, same model, same result, three times the cost. An attempt launched **after** the
fork is not blind: it carries the 10b findings verbatim, and it launches into whichever branch
the fork chose — an escalated tier for a capability gap, or a rewritten ticket for a ticket
defect. So the third attempt is the fork's *output*, not a bypass of it.

`:run` already stops a ticket that fails implementation twice. That rule is the attempt
budget, and it covers verification failures too — a handoff that fails twice is the same
signal.

**`TICKET UNDERSPECIFIED` still consumes no attempt**, and that survives the larger budget
deliberately: it is the one honest outcome the process actively wants, and a budget that
charged for it would punish the behaviour it is trying to buy.

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

## SALVAGE — entered on a 10b verdict, or by a human

The single exception to *"the orchestrator implements nothing."*

> **REVERSED 2026-08-10 (BILL-535).** This section read: *"It requires an explicit human
> instruction naming the ticket; it is never entered autonomously, and never inferred from a
> report."* That rule now has exactly one exception, and the file states one answer rather
> than leaving both readings in the tree.

**A `HANDOFF SALVAGE` verdict enters salvage autonomously. Nothing else does.** A human
instruction naming the ticket still works and still enters it.

**Why the old rule does not cover this case.** It was written against *a report* — an agent's
own account of its work, which is exactly what this process refuses to trust anywhere. A 10b
verdict is the opposite artifact by construction: a **fresh** context at the **tier above**,
fed **artifacts only** and never the agent's claims, scoring the DoD item by item, bound to a
tip SHA. Treating that as equivalent to an agent's self-report would make the entire handoff
stage pointless — its whole purpose is to be the judgement a human would otherwise have to
make. The alternative is a human decision on every partially-good worktree, which is the
stall this process exists to avoid.

**What does NOT relax.** Autonomous entry changes who decides, and nothing else:

- frozen tests stay frozen; `$FROZEN` is still the original Phase 0 commit;
- the repaired branch goes back through the **whole pipeline**, not around it, and re-enters
  at 10b for a fresh verdict;
- the orchestrator never self-certifies a repair — a salvage that ends without a new 10b
  verdict is not finished, it is abandoned mid-repair;
- an empty finding list is not a salvage brief. See the numbered-findings rule below.

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
