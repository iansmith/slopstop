# Run: Integration, Drift Checks, Final Report, G-final (Step 8 detail)

`design/slopstop-process.md` §7f–§7g and §8. The run's exit path: land the work,
verify nothing drifted, report — then have the report itself adversaried before the
human sees it.

## 8a. Integration — serial, from the root

Integrations run **one at a time, in the §7b dependency order** — never an N-way
merge. For each blessed ticket:

1. **Re-check the blessing:** the branch tip must equal the recorded `PASS@<sha>`
   (fleet-state `verdicts` cell). Tip advanced → the blessing is **void**; re-run
   Step 6 verification on the new tip before integrating.
2. Run **`:merge <TICKET>` from the root checkout** on the primary branch — never a
   hand-rolled git merge. `:merge` resolves the PR from the ticket key, **reopens the
   declined PR**, merges, fires the ticket transitions, pulls the root forward
   (`--ff-only`), and removes the agent worktree + branch.
3. Conflicts are rare by construction (§7b); when one occurs: resolve it, **re-run
   the full test suite**, and only then accept the merge.
4. Record the integration in `fleet-state.md`; recompute the launch frontier
   (newly-unblocked tickets fork from the new tip).

## 8b. Umbrella completion — the drift check

When an umbrella's last leaf integrates:

1. Write `scratch/runs/$RUN_ID/umbrella-<KEY>.md` — outcome per leaf (version,
   attempts, escalations, kills), deviations, suite state at the umbrella's tip.
2. Spawn a **fresh big-tier drift check** — the automation that replaced the
   per-umbrella human gate — fed the PRD, charter, and the umbrella report, verifying
   against ground truth (git log, ticket states): does the landed whole still match
   what the PRD + charter asked for, or did the leaves individually pass while the
   umbrella collectively drifted?
3. Failures come back as specific findings → reconcile (fix-forward tickets, report
   corrections) or escalate to G4 if reconciliation needs human scope decisions.

## 8c. The final report — after ALL umbrellas

Assembled into `scratch/runs/$RUN_ID/final-report.md`, provenance header on top:

1. **Outcome table** — per umbrella/leaf: status, version reached, attempts,
   escalations, kills with reasons.
2. **Deviation ledger** — every rewrite + its delta verdict, scope questions raised,
   abandonments, G4 decisions taken.
3. **Verification state** — full suite result on the integrated tip, both handoff
   verdicts per ticket, every drift-check verdict.
4. **Spend** — total, per tier, per ticket, from `GET /spend?prefix=$PREFIX&run=$RUN_ID` (or the
   degraded-mode line). Per-ticket spend is the small-model evaluation data.
5. **Archive confirmation** — `prd.md` + `charter.md` **attached to the umbrella
   ticket** (posted as comments or attachments per system), and the run dir marked
   ready to clean.

## 8d. The final adversary — the report is not believed

The final report is the orchestrator grading its own homework — the one
self-assessment in the pipeline. Spawn a **fresh big-tier adversary**:

```
Given the PRD, the charter, and the ticket tree approved at G2, prove this
final report WRONG or INCOMPLETE. Hunt omissions above all: unreported kills,
quietly dropped tickets, aggregate scope shrinkage across rewrites that
individually passed delta checks, suites skipped, worktrees never integrated.
Work from ground truth — git log on the integrated tip, the ticket system's
actual states and comments, the router's spend records — and RE-RUN THE TEST
SUITE yourself; do not accept the report's claim of green. VERDICT: PASS or
FAIL with specific findings.
```

Findings → correct the report (or the work, if the gap is real) → re-verify with the
same adversary. **≤3 rounds**; still failing → the human gets the report *with* the
surviving findings attached — never a cleaned-up version.

## 8e. Gate G-final — and only then, cleanup

Present the adversaried report:

```
G-final — run $RUN_ID complete

Report:    scratch/runs/$RUN_ID/final-report.md  (adversary: PASS after <n> rounds)
Integrated: <n> tickets across <n> umbrellas onto <primary>
Suite:     <adversary's own re-run result>
Spend:     <total | degraded-mode line>

Accept the run?
```

**Stop.** `scratch/runs/$RUN_ID/` is cleaned **only after the human accepts — never
before**; on acceptance, the PRD + charter live on in the umbrella ticket and the run
dir is deleted. Per-ticket tracking dirs under `$TRACKING_DIR` are *not* touched at
G-final — each terminal ticket's `:merge` already archived its own inline (§8a → `:merge`
Step 10) during integration.
