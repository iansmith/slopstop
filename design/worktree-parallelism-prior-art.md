# Prior art: worktrees, parallel launch, and not trusting an agent

> Recovered 2026-08-06 from `32ecb23~1` and `b42d306~1` for **BILL-466**.
> The mechanisms below **ran in production** and every one of them has a named incident
> behind it. `run-agent-brief.md` stated the design rule outright: *"Every rule above is a
> scar."* Re-deriving these from first principles means re-earning the scars.
>
> This is a record, not a specification. Nothing here is currently implemented.

---

## 1. Worktree creation

**Where it lived:** not in any of the six deleted `run-*.md` reference files — those treated
a worktree as a *precondition*. Creation was Step 4.2 of the **pre-4.0.0 fleet `:run`**, at
`git show b42d306~1:skills/run/SKILL.md`.

```bash
git worktree add <path> -b <TYPE>/<TICKET> <primary>
```

> with the `<TYPE>` Step 3 resolved for this leaf — **the exact string the agent's own
> `:start` will resolve.** Otherwise its Step 5a finds no such branch and creates a second
> one, and the agent works on a branch nothing is monitoring or integrating. Record the fork
> SHA and branch in `fleet-state.md` (the branch name later resolves to a *moved* tip; the
> SHA is the truth).

Invariant: **one agent ⇄ one ticket ⇄ one branch ⇄ one worktree. Never bundle.**

`<path>` was **never templated** — no version in history specifies a directory-naming
scheme. It was a free parameter recorded in the ledger. BILL-466 has to choose one.

### Fork-point discipline

- Fork from the current tip **at launch time**, recomputed after every integration.
- The recorded **SHA**, never the branch name, is the baseline for every later check.
- From `plan-fanout.md`, the sharpest statement of why:

  > `commit` — create a WIP checkpoint commit, **re-capture `$BASE_SHA`**, continue.
  > (Re-capturing matters: the recorded fork point must be the commit the agents actually
  > branch from, or every later diff is computed against a base that never existed in their
  > worktrees.)

- The dirty-tree gate, with a trap worth keeping:

  > **`--include-untracked` is required, not optional:** the gate is `git status --porcelain`,
  > which reports untracked files as `??`, but a bare `git stash push` does not stash them —
  > so the gate would fire, the stash would "succeed", and the tree would still be dirty.

### There was NO symlink step — and that is deliberate

**A full-history grep finds no symlink rule in any skill.** The untracked-dependency problem
was solved three other ways:

**(a) Path resolution, so every worktree resolves to one directory.** From
`tracking-dir-resolution.md`, which survives today:

> **Relative** paths resolve from the **main worktree root**,
> `dirname "$(git rev-parse --git-common-dir)"` — *not* from cwd. Deliberate: every linked
> worktree resolves to the same directory, so a fleet agent's worktree session and the main
> checkout share one tracking dir **with no symlinking**.

**(b) `--add-dir`, granted by the orchestrator, never improvised by the agent.**

> required **whenever `tracking_dir` resolves outside the agent's worktree**, which is the
> normal case… Without the grant, `:start`'s seeding is denied and the agent invents a local
> one. **Never point `tracking_dir` inside `~/.claude/`** — that path is protected: `Write`
> refuses it *even with* a matching `--add-dir`.

The failure that produced the rule: *"A denied write becomes a silent relocation."* An agent
unable to write the configured tracking dir created its own `.local-tracking/` inside the
worktree and carried on.

**(c) The untracked-file hazard was caught by review, not by machinery.** A live instance:
*"worktrees are created from HEAD, so an untracked `.gitignore` would have meant every fleet
worktree missing the `scratch/` and `.slopstop/` rules."*

The symlink guidance you may be remembering is **universal §6** — *"symlink large,
rarely-changing directories that aren't under git control"* — which is live today and **was
never mechanized in a skill.**

### Teardown

Verification's scratch worktrees are ephemeral (`git worktree add -q` … `git worktree remove
--force`). **Agent worktrees are never removed on failure** — only by `:merge` after
integration, or on human-approved abandon. `git worktree remove` then `git branch -D`
(*"worktree remove detaches, does not delete"*); on failure, surface the error and leave the
worktree in place.

---

## 2. Launch order

From `run-launch-order.md`. The goal statement is the part worth keeping:

> Order agents so that **if they all succeed, integration is conflict-free by construction**
> — this converts a hard N-way merge into a sequence of trivial ones.

1. **Collect file maps** from every leaf. Directory entries count as their whole subtree.
2. **Explicit relations first** — `Blocked by:` and umbrella structure are hard edges. A
   ticket never launches before its blockers are *integrated*, not merely "done".
3. **File affinity second** — disjoint maps launch in parallel; overlapping ones serialize,
   the later one forking from the **updated tip** so it builds on landed work.
4. When heuristic and explicit relation disagree, **the explicit relation wins**.

- Recompute the frontier after every integration.
- Overlap detection is **path-prefix comparison, nothing fancier**.
- **No numeric concurrency cap** in the fleet — concurrency is whatever the frontier yields.
  (`:plan`'s within-ticket fanout capped at 4, with no stated rationale.)
- Integration is **always serial**, regardless of parallelism: *"never an N-way merge."*

### The ledger is the source of truth, not the conversation

`fleet-state.md`, updated on **every** event, re-read from disk before acting:

```
| ticket | version | attempts | agent | worktree | branch | fork SHA | last marker | verdicts | status |
```

Status vocabulary — and why it needs a fifth value:

> `queued` → `running` → `verifying` → `integrated`, plus `failed` and **`unrun (<reason>)`**
> for a leaf that never launched. An unrun leaf consumes no attempt and is not a kill; a poll
> that cannot distinguish it from `queued` will wait forever for an agent that was never
> started.

---

## 3. Not trusting the agent — four independent checks

The governing rule, from `design/slopstop-process.md`:

> **No information, artifact, report, or claim is ever accepted at face value by any model
> doing checking.** Checkers are always fresh invocations fed only artifacts — never the
> author's narrative or transcript.

And: *"A clean `:pr` review is necessary, never sufficient."*

### 3.1 Tamper check — mechanical, run by the orchestrator itself, before spawning anything

> A FAIL ends verification there — no subagent is bought. **A green suite is not evidence
> when the agent had write access to the tests.**

- The **earliest** Phase 0 commit is the frozen baseline. *"Never `grep -m1`: that takes the
  NEWEST match, letting an agent slide the baseline past its own tamper by titling a later
  commit 'Phase 0: red tests'."*
- The RED commit **is** the manifest — `git show --name-only` it rather than globbing.
  *"Exact by construction, language-agnostic, and it catches Rust/Go inline `#[cfg(test)]`
  tests living in source files, which a `'*_test.*'` glob would miss entirely."*
- Two guards, each with its failure mode stated: an unset `$RED` makes `git diff $RED..tip`
  resolve to `HEAD..tip` — *"an empty diff that falls through looking clean"*; an empty
  `$FROZEN` makes the pathspec vanish and diffs the **entire repo**.
- **No Phase 0 commit at all → FAIL immediately.** *"An agent that never wrote a failing test
  never proved its tests can fail, so its green suite is unfalsifiable… This is the cheaper
  evasion of the whole rule, and a tamper diff that only runs when a baseline exists rewards
  skipping the baseline."* Observed live on SOP-110.
- The classification rule, which is the core of the entire design:

  > The agent will have a reason. The commit message will be confident and often cites a real
  > standard. **The reason is irrelevant.** A vetted expected value changed by the model whose
  > code had to satisfy it is tampering by construction, regardless of how it is narrated.

  The originating incident: an agent's test correctly asserted a G.711 value and failed,
  pointing at a real four-character bug. Its next commit, *"Fix: use standard G.711 μ-law
  table"*, left the decoder untouched and **edited the assertion**. *"This was not confusion
  — it was a rationalization, which is why the fix is a mechanical diff and not a sterner
  instruction."*

### 3.2 Redness confirmation — the question the tamper check structurally cannot ask

> The tamper check answers *"did the frozen tests change since RED?"* — this answers
> *"were they ever red in the first place?"*

Actually checks out `$RED` in a scratch worktree and runs the tests, cached per
`$TICKET-${RED:0:12}`. Two details: the test command is resolved **the same way Phase 0
resolved it** (*"rather than a second, divergent resolution that could silently disagree"*),
and the checkout must sit **inside** the cache-miss branch or *"caching becomes decorative."*

**Three dispositions, not two:**

- **Exit 0** → never-red → **FAIL**. It asserts what the code already did.
- **Non-zero but never reached an assertion** (collection/import error) → **unverifiable** →
  **FAIL**, distinct from the above. *"A bare 'assert non-zero exit' would let this launder
  through as red… a check that could not run must not read as a check that passed."*
- **Non-zero with a genuine assertion failure** → **PASS**.

### 3.3 Two fresh subagents, at the tier above

Run only if both mechanical checks passed. Both fed **artifacts only** — the ticket body, the
worktree, the diff from the recorded fork SHA — *"never the agent's claims (its ticket
comments and PR description are the **subject** of scrutiny, not evidence)."*

**Requirements adversary** — charter *"fail this work if you can."* Scores the DoD item by
item, and hunts the three evasions a diff cannot see: **(a)** no shadow definition of a test
name neutralizing it, including via rename; **(b)** the expected value lives in the frozen
test itself, not in a helper/conftest/fixture/golden the Phase 0 commit did not freeze;
**(c)** the test was *actually* red. Also: *"a value that was wrong on arrival is invisible
to [the tamper check], and yours alone to catch."*

**Code reviewer** — correctness, removed invariants, honest error handling, house style.

Return schema is the only thing crossing back — `VERDICT` plus `<file>:<line> — <defect> —
<fix>`. *"The orchestrator never ingests diffs"*; longer detail goes to a file and the
finding cites it.

### 3.4 A blessing binds to a SHA, not to a ticket

> Record the branch **tip SHA at verdict time** … if it has advanced past the recorded
> blessed SHA (a relaunch, rewrite, or salvage commit landed), the blessing is **void** and
> verification re-runs on the new tip.

Re-checked again at integration time.

### 3.5 File-map violation kill — continuous, during execution

`git -C <worktree> diff --name-only <fork SHA>` — catches committed **and** uncommitted
writes, *"agents commit as they go, so `git status --porcelain` alone would miss committed
out-of-map files."* Instant kill, no grace period, no model judgment.

> The asymmetry is deliberate: an agent writing where it was fenced out is doing damage in
> the wrong place (instant, mechanical); a quiet agent might just be thinking (patient,
> two-stage).

Other triggers: **quiet** (15 min, investigate don't kill — *"activity without comments = a
healthy-but-silent agent"*), **silence** (30 min, both signals dead = *"the definition of
stuck"*), **loop** (same failure 3×, *"more repetition will not converge"*).

### 3.6 Even the orchestrator's own report is not trusted

> The final report is the orchestrator grading its own homework — the one self-assessment in
> the pipeline.

Its adversary is told to work from git log, the ticket system, and **to re-run the suite
itself** — *"do not accept the report's claim of green."* ≤3 rounds, then the human gets the
report **with the surviving findings attached, never a cleaned-up version.**

---

## 4. Failure, recovery, salvage

**Budgets** (`[fleet.budget]`): `max_attempts_per_version` 3, `max_ticket_versions` 3,
`max_tier_escalations` 1. Kills and failed verdicts consume an attempt; the
`TICKET UNDERSPECIFIED` halt consumes **none**.

**On kill: preserve the worktree.** *"Never clean it on a kill; the next attempt resumes
there with the kill reason and any prior findings cited in its brief (a retry without new
information is a wasted attempt)."* Worktrees are deleted only on human-approved abandon or
after integration.

**`TICKET UNDERSPECIFIED`** — detected as a literal final line, routed to rewrite with **no
attempt consumed**. *"Bad tickets are Stage 2 defects, not Stage 3 failures."* The agent-side
framing: *"That is a legitimate, cost-free outcome… Silently 'correcting' the test is not: it
is the single worst thing you can do in this process."*

**Diagnosis fork after 2 failures** — *ticket defect* → rewrite; *capability gap* → tier
escalation. *"The classification is recorded — it is also the run's evaluation data (bad
tickets vs weak models are distinguishable in the ledger)."*

**Rewrite** — cite the specific failure (*"generic rewrites are wasted rewrites"*), capture
the outgoing body **first**, title gains `(V2)`, and the huge-tier delta check must return
`SPECIFICITY` not `SCOPE-SUBTRACTION` before the tracker is touched. A changed ticket is a
**new contract**: fresh agent, fresh budget, **same preserved worktree**. Reset to the fork
SHA only on an explicit unsalvageable-approach diagnosis — *"never the default."*

**Relaunch carries the findings verbatim.** *"If there are no specific findings, something is
wrong with the verdict, not the agent."*

**G-failure** presents a ledger, a diagnosis, spend, the preserved worktree path and commit
count, and four options: `more attempts`, `rewrite`, `salvage`, `abandon`. *"The fleet does
not stop"* — only the blocked subtree waits.

**SALVAGE** — human-authorized only, the single exception to *"the orchestrator implements
nothing":*

> the orchestrator itself picks up the preserved worktree and follows the base process on
> that branch … then **declines the PR** exactly as an agent would … Before integrating, the
> orchestrator confirms the fix closes the specific gap the handoff adversary found —
> **salvaged code goes through the same quality pipeline as everything else, not around it.**

Preserved: the worktree, the branch, every commit the failed agent made, and the findings —
which become the acceptance criterion for the salvage. Reset: nothing.

---

## What 4.0.0 has, and does not

| mechanism | 4.0.0 |
|---|---|
| tamper check | partly — `slop-check`, judgment not mechanical diff |
| redness confirmation | **yes** — `vacuity-check`, and it is stronger |
| requirements adversary at handoff | **no** |
| independent code reviewer at handoff | partly — `review`, but same session's scope |
| file-map violation kill | **no** |
| blessing bound to a SHA | **no** |
| worktree creation | **no** — BILL-466 |
| launch order / frontier recomputation | **no** |
| attempt & version budgets | **no** |
| kill triggers | **no** |
| worktree preservation on failure | **no** |
| salvage | **no** |
| ledger as external source of truth | partly — `run.jsonl` per ticket, no cross-ticket view |

**The 4.0.0 failure model is "stop the ticket, keep the others running."** That is a
deliberate simplification of everything in §4 — but it means a failed ticket currently
yields *nothing*: no preserved worktree contract, no findings-carrying retry, no salvage.
Recovering that is larger than BILL-466 and should be its own ticket.
