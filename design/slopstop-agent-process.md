# slopstop agent process — multi-agent orchestration

The [base process](../design/base-process.md) governs how **one** ticket is taken from start to merge. This document governs how **many** tickets are worked at once by a fleet of agents, and how their contributions are integrated safely.

**Precondition (assumed, not covered here):** the complex task has already been broken down into a ticket tree — a set of tickets, some of which may be umbrellas over sub-tickets, which may themselves have sub-tickets. Decomposition is done. This document starts the moment there are leaf tickets ready to be worked.

## Roles

- **The orchestrator** — the coding agent (the main session). It runs the orchestration **autonomously**: sequencing, monitoring, adjudication, and integration all proceed without prompting. It does not implement ticket work itself — that is delegated to agents — with the single exception of salvage (§6b). It may ask the user for help or approval **whenever it wants**; there are two decision points where it **must** (below), but those are a floor, not a ceiling.
- **The agent** — a spawned subagent, exactly one per leaf ticket, working in isolation. It owns implementation.
- **The user** — the human. **Always** consulted at two mandatory points: (1) the time-boxed continue/kill gates (§4), and (2) the salvage go/no-go after an adversary failure (§6b). The orchestrator is free to consult the user at any other time as well — these two are the asks it must not skip, not the only asks it may make.

---

## 1. The agent contract

Every launched agent is configured **identically**:

| Property | Value | Why |
|---|---|---|
| Isolation | **worktree** | Agents run concurrently and mutate files; a per-agent worktree keeps them from colliding, and gives the orchestrator a clean per-ticket branch to integrate. |
| Model | **sonnet** | The implementation tier. The orchestrator may run richer; the workers are Sonnet. |
| Effort | **medium** | Enough for leaf-ticket implementation; keeps fleet cost bounded. |
| Assignment | **exactly one ticket** | One agent ⇄ one ticket ⇄ one branch. Never bundle tickets into an agent. |

### What the agent does

The agent follows the **full slopstop process** for its ticket — `:start` → `:plan --inline` → work → `:update` → `:pr --inline` — with **one deletion**:

- **`:start` runs normally,** which means the agent **transitions its ticket to In Progress** as part of starting. The status transition is the agent's, via the process — the orchestrator does not set it.
- **No `:merge`.** Merging inside the agent's worktree is pointless: the orchestrator owns integration and does it in a controlled, dependency-ordered pass (§6c). An agent that self-merged would race every other agent to the primary branch.
- **`:pr --inline`, then decline.** The agent runs `:pr --inline` for the code-quality pipeline (simplify → tests → slop gate → code review), because that pipeline is where slop is caught. `--inline` is mandatory: without it, `:pr`'s simplify pass, slop-detection gate, and Claude code-review step each spawn sub-agents whose completion notifications are routed to the top-level main loop rather than back to this agent's context, causing a deadlock. Inline mode runs all three reasoning steps directly in the current context. The agent iterates the review to a **clean** result. Then it **declines its PR — stops without merging** — and is done. The branch stays intact; the PR was only ever a vehicle for the review gates, not the integration mechanism.
- **`:plan --inline`** forces serial execution and runs the adversary and investigation inline. Sub-worktree fanout from inside a worktree agent is not supported; `--inline` prevents `:plan` from attempting it.

**Agent "done" =** clean `:pr` review + PR declined (not merged) + branch pushed. Nothing is integrated yet.

### What the agent reports

The agent posts progress to its ticket (see §3 for where the orchestrator tells it to report). **Every use of a slopstop tool is reported** — `:start`, `:plan`, `:pr`, each review round, PR decline. These tool-use lines are load-bearing: they are the orchestrator's cheapest signal that the agent is progressing through the process rather than hung or looping.

### Fleet agent brief template

Fill in the bracketed values for each leaf ticket. This is the brief the orchestrator posts to the agent — not the within-ticket parallel fanout template in `plan-agent-prompt.md` (which bans `/slopstop` commands).

```
You are a fleet agent working on $TICKET ($TICKET_TITLE).

# Your task

Follow the full slopstop process for this ticket:
  /slopstop:start $TICKET
  /slopstop:plan --inline
  <implement the work>
  /slopstop:update  (checkpoint progress as you go)
  /slopstop:pr --inline

Do NOT run /slopstop:merge. The orchestrator integrates your branch after review.

# Context

Ticket: <ticket URL>
Worktree: <worktree path> (branch: <agent branch>)
Forked from: $BRANCH @ $BASE_SHA

<paste the relevant section of findings.md if investigation has already been done, or leave empty>

# Hard constraints

1. You are in the isolated git worktree shown in Context above.
   You MUST NOT touch files outside this worktree.
2. Do not merge other branches in, do not rebase, and do not push to origin manually — :pr handles the push.
3. --inline is MANDATORY on both :plan and :pr.
4. Commit frequently. Small commits make recovery easier.
5. Each commit message starts with `[$TICKET]`.
6. Report every slopstop tool use as a comment on $TICKET — `:start`, `:plan`, each `:update`, `:pr`, each review round, PR decline. These markers are load-bearing. The orchestrator polls at 30/60/120-minute gates and may terminate you if you appear stuck.
7. When :pr returns clean, decline the PR (do not merge) and stop.
8. If you get stuck and cannot make progress, commit what you have, report what blocked you, and stop.
```

---

## 2. Launch order — dependency-first, merge-safety-driven

The orchestrator launches agents in an order chosen so that, **if they all succeed, integrating their work is trivial or conflict-free.** This is the single most important thing the orchestrator does up front, because it converts a hard N-way merge into a sequence of easy ones.

The ordering is driven by **file affinity** — which files each ticket is expected to touch — plus any explicit ticket relations (`blockedBy`, umbrella/sub-ticket structure). Determining the file sets is usually simple: read the ticket, name the files.

- **Disjoint file sets → launch in parallel.** Two tickets that touch no common file can never conflict; run their agents concurrently.
- **Overlapping file sets → serialize.** If ticket B touches files ticket A also touches, do **not** run them at once. Launch A's agent first; only after A is integrated onto the primary branch (§6c) launch B's agent, **branched off the updated tip**. B's worktree then already contains A's landed work, so B builds on it instead of colliding with it.
- **Explicit dependencies always win.** A `blockedBy` relation or an umbrella that must land before its siblings overrides the file heuristic.

The payoff: each agent branches off the current tip of the primary branch (plus everything integrated so far), so by construction its diff sits cleanly on top of what's already landed.

---

## 3. Ticket preparation — tell agents where to report

Before (or as) each agent launches, the orchestrator **checks the ticket and adds a comment** that tells the agent:

1. **Where to report progress** — the reporting channel for this run (typically: comments on this ticket). One consistent place per ticket so the orchestrator can poll it.
2. **To announce every slopstop tool use** — each `:start` / `:plan` / `:pr` / review-round / PR-decline gets a one-line marker comment. This is a hard expectation, not a nicety.

(The ticket's move to In Progress is handled by the agent's own `:start`, not this comment.) These comments are the contract surface between orchestrator and agent. If the ticket has no such comment, the agent hasn't been briefed — don't launch it yet.

---

## 4. Monitoring — time-boxed continue/kill gates

A hung agent or a dead loop burns wall-clock and money silently. The orchestrator guards against this with **mandatory check-in gates** at three elapsed-time thresholds per agent — one of the two points (with salvage) where the orchestrator **must** ask the user, though it is free to ask about anything else whenever it wants:

| Elapsed | Orchestrator action |
|---|---|
| **30 min** | Pause and **ask the user** whether this agent should continue. |
| **60 min** | Ask again. |
| **120 min** | Ask again. |

At each gate the orchestrator summarizes what the agent has done (from its slopstop-tool-use markers and last progress report) so the user can decide **continue / kill / investigate** on evidence. The gates exist specifically to catch the agent that is stuck — an agent making visible progress through the slopstop stages is usually an easy "continue," but the question is still asked.

The orchestrator tracks elapsed wall-clock per agent (the check-ins are per agent, not global) and schedules its own wake-ups to hit the thresholds even while other work is in flight.

---

## 5. Completion — adversary review against the ticket

When an agent reports done, the orchestrator does **not** trust it. It spawns an **adversary agent** whose job is to review the produced code and commits **against the ticket's requirements** and try to fail them.

This is distinct from the code review the agent already ran inside `:pr`:

- `:pr`'s review hunts for **bugs and quality** in the diff.
- The **adversary** hunts for **requirements conformance**: did the work actually satisfy the ticket's acceptance criteria / definition of done? Missing criteria, tests that pass vacuously, scope violations, regressions in untouched behavior, criteria "met" only on paper.

The adversary returns a verdict: **pass** (the work meets the ticket) or **fail** (it does not, with specific reasons).

---

## 6. Adjudication and integration

```
agent done ─▶ adversary review
                  │
        ┌─────────┴─────────┐
       pass               fail
        │                   │
        │       orchestrator EXPLORES the worktree,
        │       assesses what would make it provide
        │       value, and asks the USER before acting
        │                   │
        │             ┌─────┴─────┐
        │          salvage      abandon
        │             │             │
        │   orchestrator fixes   drop worktree,
        │   it AS an agent       ticket unmerged
        │   (slopstop, no merge, ─▶ back to backlog
        │    decline PR clean)
        │             │
        └──────┬──────┘  (pass, or salvaged-and-confirmed)
               ▼
        :merge  from the root worktree, on the primary branch
        (merges the work AND fires the ticket transitions/archive)
```

### 6a. Adversary passes

Proceed straight to integration (§6c).

### 6b. Adversary fails — the orchestrator salvages

The orchestrator **explores the worktree** to understand exactly what is missing or wrong and what a targeted fix would take. It presents that assessment and **asks the user for a go/no-go** — this is a genuine pause point:

- **Salvage** — the **orchestrator itself does the fix**, acting as an agent: it picks up the existing worktree where the agent left off and follows the normal slopstop process on that branch — `:plan`/work as needed, then `:pr` — iterating the review to a clean report. It does **not** merge, and it **declines the PR** on a clean report, exactly as an agent would. The orchestrator runs from the root checkout (not inside a delegated worktree agent), so the sub-agent deadlock does not apply: run `:pr` and `:plan` without `--inline` during salvage. Once the salvage is complete and the orchestrator has confirmed it closes the gap the adversary found, proceed to integration.
- **Abandon** — drop the worktree; the ticket stays unmerged and returns to the backlog for re-scoping or a fresh attempt.

The user makes the salvage-vs-abandon call — that is the moment where "throw more effort at it" versus "cut losses" needs a human. The orchestrator's exploration is what makes that call informed; it always explores and proposes before asking.

### 6c. Integration — `:merge` from the root

When the work is blessed — adversary passed, **or** salvaged and confirmed — the orchestrator integrates it by running **`:merge <TICKET>` from the root worktree**, on the primary branch. It does **not** hand-roll a git merge:

- `:merge <TICKET>` performs the merge **and** fires the appropriate ticket-related actions — advancing the ticket's state and archiving on a terminal state. This is the `:merge` the agent deliberately skipped; the orchestrator runs it once, itself, at integration time.
- The orchestrator is on the root checkout (the primary branch). It names the target ticket explicitly; `:merge` resolves the PR from the ticket key, reopens it if the agent declined/closed it, and merges.
- After merge, `:merge` advances the root checkout with `git pull --ff-only` and cleans up the agent's worktree (`git worktree remove` + `git branch -D`).
- Integrations run **one at a time, in the dependency order from §2** — never a simultaneous N-way merge. Each `:merge` lands on a tip that already contains its predecessors, and the next serialized agent is branched from the new tip.
- Conflicts are rare by construction (that is the whole point of the launch order); when they occur, the orchestrator resolves them and re-runs the suite before accepting.

---

## Rules

- **The orchestrator runs autonomously,** and may ask the user for help or approval whenever it wants. Two decisions are **mandatory** asks it must never skip: the 30/60/120-minute continue/kill gates (§4) and the salvage go/no-go (§6b). Everything else it may decide on its own — or raise with the user if it wants a second opinion.
- **The orchestrator delegates implementation to agents** — it does not write ticket code itself, **except during salvage**, where it acts as an agent on the existing worktree (slopstop process, no merge, decline the PR on a clean report).
- **One agent, one ticket, one branch, one worktree.** No bundling.
- **Agents never merge.** `:pr` yes; `:merge` never. Integration is the orchestrator's, run as `:merge <TICKET>` from the root — targeting the ticket — onto the primary branch, in dependency order.
- **Agents set their own ticket status** to In Progress via `:start`. The orchestrator does not transition it on the way in; `:merge` transitions it on the way out.
- **A clean `:pr` review is necessary but not sufficient.** The adversary requirements-review gates integration; a clean code review alone does not.
- **Nothing integrates without a blessing** — an adversary pass, or a user-approved salvage that the orchestrator has confirmed closes the gap.
- **Every slopstop tool use is reported to the ticket.** Missing markers are themselves a signal to investigate.

---

## `:merge` capabilities required by this process

Both capabilities below shipped in **BILL-133** and are available now.

1. **Target a ticket explicitly, from the root checkout.** Pass the ticket key as a positional argument: `:merge <TICKET>`. The orchestrator runs on master/primary; `:merge` resolves the PR and branch from the ticket key rather than from `git branch --show-current`. Running `:merge` from master without a target still refuses (existing guard); with an explicit target it is allowed.

2. **Operate on a declined (closed) PR.** Because agents decline their PR on a clean review rather than merging, `:merge` detects the closed PR, reopens it via `gh pr reopen`, and proceeds to merge. An already-MERGED PR (idempotent re-run) skips the merge step and continues with ticket transition and archive.

### Known gap — BILL-134 (not yet fixed)

If `:merge` is somehow called from **inside** a per-ticket worktree (not from the root), Step 8a's `git switch <primary>` will fail because the primary branch is already checked out in the main checkout. The merge and ticket transition still complete (Step 8 is non-fatal); finish cleanup from the root:

```
git -C <root> pull --ff-only origin <primary>
git worktree remove <worktree-path>
```

This should not occur in the orchestrator flow (which always runs from the root), but is noted here for completeness.
