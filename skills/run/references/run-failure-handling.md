# Run: Failure Handling (Step 7 detail)

Budgets, diagnosis, rewrites, escalation, and the G4 gate
(`design/slopstop-process.md` §7e). Everything here is autonomous **except** the G4
decision itself and salvage execution — those are the human's.

## Budgets — `[fleet.budget]`, enforced hard

- `max_attempts_per_version` (default 3) — kills and failed handoff verdicts each
  consume one; the `TICKET UNDERSPECIFIED` halt consumes **none**.
- `max_ticket_versions` (default 3) — V1 plus two failure-driven rewrites.
- `max_tier_escalations` (default 1) — escalated-model attempts per ticket.

Track all three per ticket in `fleet-state.md`. Exhausting attempts on the final
version, or needing a fourth version, → G4.

## The diagnosis fork — after 2 failed attempts on a version

Read the attempt evidence (kill reasons, handoff findings, the agent's markers) and
classify:

- **Ticket defect** — the failures trace to the contract: wrong file map, ambiguous
  behavior, impossible expectation, missing information. → **Rewrite.**
- **Capability gap** — the ticket is right; the model couldn't do it (findings show
  correct understanding, failed execution). → **Tier escalation.**

The classification is recorded in `fleet-state.md` — it is also the run's
evaluation data (bad tickets vs weak models are distinguishable in the ledger).

A **`TICKET UNDERSPECIFIED`** halt from the agent skips the fork: it is already a
ticket-defect diagnosis, made from inside the territory. → Rewrite, **no attempt
consumed** (bad tickets are Stage 2 defects, not Stage 3 failures).

## Rewrite — a new contract

1. **Draft** the new ticket body citing the **specific** code and instruction that
   failed: file:line of what the agent produced, the quoted DoD item or file-map entry
   that didn't survive contact. Generic rewrites are wasted rewrites. Capture the
   **outgoing body** first (snapshot it in `fleet-state.md` or the run dir) — the delta
   check compares against it, and a scope-restore has nothing to restore from without
   it. The tracker is not touched yet: the new body and `(V2)`/`(V3)` title marker are
   published only once the delta check passes (step 3), so a rejection needs no undo.
2. Title gains the version marker: `<title> (V2)`, then `(V3)` — the run ledger
   self-documents in every ticket list.
3. **The huge-tier delta check — mandatory before ANY relaunch.** Spawn a fresh
   subagent at the rewrite-delta-check tier — `[stage_tiers].rewrite_delta_check`
   (default `huge`) → `[tiers].<that tier>` — fed the PRD, charter, the captured
   outgoing body, and the drafted new body:

   ```
   You are a huge-tier delta checker. A ticket was rewritten after implementation
   failures — the most drift-prone moment in the pipeline. Compare old vs new
   against the PRD + charter and answer exactly one question: did this rewrite
   ADD SPECIFICITY, or did it SUBTRACT SCOPE (shrink the DoD to make the ticket
   passable)? VERDICT: SPECIFICITY | SCOPE-SUBTRACTION, with the subtracted
   items quoted if any.
   ```

   `SCOPE-SUBTRACTION` → rejected: restore the scope, or — if the scope genuinely
   was wrong — take it to the human (amending the PRD is never autonomous).
4. A changed ticket is a **new contract**: fresh agent, fresh attempt budget, next
   version — in the **same preserved worktree**. Reset to the fork SHA only on an
   explicit unsalvageable-approach diagnosis, recorded in `fleet-state.md` and the
   ticket; never the default.

## Tier escalation — the capability answer

The final attempt on the current version runs on `[fleet.agents].escalation_model`
instead of `model`. When that key is absent, `escalation_model` defaults to the model
**resolved from `[tiers].medium`** (family + optional version pin composed into a model
id, exactly as the fleet `model` defaults to `[tiers].small`); an explicit
`[fleet.agents].escalation_model` overrides it. Nothing else about the launch changes
(same effort, same brief shape, same worktree). **Autonomous, recorded, at most
`max_tier_escalations` per ticket** (default: once). If the escalated attempt also fails, the remaining path is
rewrite (if versions remain) or G4. If a capability gap is diagnosed on a later
version with escalations already spent, the final attempt simply runs on the base
model — its failure routes to rewrite or G4 as usual.

## G4 — the human's budget decision

Triggered by exhaustion (attempts on the final version, versions, or escalations with
nothing left to try). Post the ledger to the ticket and present to the human:

```
G4 — <TICKET> exhausted its budget (run $RUN_ID)

Ledger:   <per-attempt lines: version, model, outcome, kill/verdict reason>
Diagnosis: <ticket-defect | capability-gap history>
Spend:    <per-ticket figure from the router | "cost tracking disabled/unavailable">
Worktree: <path> (preserved — <n> commits since fork)

Options:
  more attempts <n>  — same version, same tier rules
  rewrite            — a further version beyond the cap: the `(Vn)` marker keeps
                       incrementing (`(V4)`, …); delta check still applies
  salvage            — I implement in the preserved worktree (base process, no
                       --inline, decline the PR, re-verify) — human-authorized only
  abandon            — worktree deleted, ticket back to the backlog, recorded
```

**The fleet does not stop:** while G4 pends, every independent ticket — anything not
depending on the stuck one — keeps launching, verifying, and integrating. Only the
blocked subtree waits.

Salvage, when authorized, follows the spec §7e procedure exactly — the orchestrator
works the preserved branch through the base process (no `--inline`; it runs from the
root, so no deadlock), iterates the review clean, declines the PR, and the handoff
verification re-runs before integration. Salvaged code goes through the pipeline,
never around it.
