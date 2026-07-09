# slopstop process — the three-tier pipeline

> **Framing:** this is THE slopstop process — how a feature travels from brain-dump to
> merged code via three tiers of models with adversarial verification at every handoff.
> The per-ticket loop each implementation agent runs is the **base process**, specified
> in [base-process.md](base-process.md); this document never restates it, only points
> at it. Config reference: `CONFIG.md` (`[tiers]`, `[fleet.*]`).
>
> Spec of record for the stage-skill tickets under umbrella
> [#162](https://github.com/iansmith/slopstop/issues/162). Source PRD:
> `docs/prd-slopstop-v3-agent-process.md` (untracked by design; archived to the
> umbrella ticket at run completion).

**The prime rule: no information, artifact, report, or claim is ever accepted at face
value by any model doing checking.** Checkers are always fresh invocations fed only
artifacts (documents, tickets, git state) — never the author's narrative or transcript.

## 1. Tiers

Models come from `[tiers]` in `.project-conf.toml` (defaults shown):

| Tier | Default | Runs |
|---|---|---|
| **big** | `fable` | `:design`; every big-tier check: ticket-tree adversary, rewrite delta checks, umbrella drift checks, final-report adversary |
| **medium** | `opus` | `:tickets`, `:run` (orchestrator), handoff reviewer/adversary subagents, failure-driven ticket rewrites |
| **small** | `haiku` | fleet implementation agents (launch parameters in `[fleet.agents]`) |

- **Tier gate:** each stage skill compares the session's model against its declared
  tier and **hard-stops on mismatch**, naming the required model. Subagent tiers are
  set explicitly by the spawning code — never inherited by accident.
- **Same-size adversary rule:** any agent launching an adversary uses its **own tier**.
  A small agent's inner `:plan`/`:pr` adversaries run small (at
  `[fleet.agents].adversary_effort`); the orchestrator's checks run medium; big checks
  big. Small adversaries are a cheap first filter — the real net is the next tier up
  at the handoff.
- **Provenance headers:** every produced artifact (PRD, charter, tickets, reports)
  opens with a header naming the model, date, and run-id that produced it. Config
  substitutions are always visible, if inadvisable.

## 2. Which tier runs which commands

| Command | Tier | Role |
|---|---|---|
| `/slopstop:design` | big | Stage 1 — grill → PRD + feature charter |
| `/slopstop:grill` | big | invoked by `:design`; usable standalone |
| `/slopstop:tickets` | medium | Stage 2 — cut the ticket tree; drive the big adversary loop |
| `/slopstop:run` | medium | Stage 3 — orchestrate the fleet; integrate; report |
| `:start` `:plan` `:update` `:pr` | small (fleet agents) | the base-process inner loop, one ticket each |
| `:merge` `:archive` `:document` | medium (orchestrator, from the root checkout) | integration and end-state writes — fleet agents never run these |
| `:gh-init` `:create-gh` `:doc-sync` `:update-ticket` | any (human-driven utilities) | outside the pipeline |

## 3. Stages and gates

Each tier is a separate session; the only things that cross a stage boundary are
artifacts. The **human drives stage transitions** with a minimal number of prompts —
each gate is a report (+ artifacts) followed by "go ahead?".

| Gate | After | Human receives | Human decides |
|---|---|---|---|
| **G1** | `:design` finishes grill + PRD + charter | the PRD and charter | proceed to ticket breakdown? |
| **G2** | `:tickets` cuts the tree AND the big-tier adversary passes it (≤3 correction rounds) | tree summary + adversary verdict + spend line | launch the fleet? |
| **G-final** | ALL umbrellas complete | the full report, already adversaried by big | accept the run? |
| **G4** (exception, any time) | a ticket exhausts its budget, or a tier impasse | failure ledger with specific evidence + per-ticket spend | more attempts / another rewrite / salvage / abandon |

There is **no per-umbrella human gate** — automation (umbrella drift checks, §7g) plays
that role. While a G4 pends, the fleet keeps running every ticket that doesn't depend
on the stuck one.

## 4. Artifacts and layout

| Location | Git | Contents |
|---|---|---|
| `scratch/runs/<run-id>/` | gitignored | run state, PRD, feature charter, fleet-state file, verdicts, umbrella + final reports |
| `scratch/tickets/` | gitignored | per-ticket tracking dirs (via `tracking_dir = "scratch/tickets"`) |
| `design/` | committed | durable, human-curated design docs (this file) |

- **Process rules ship with the plugin** — they are not per-run documents.
- The **feature charter** (per-run broad-stroke rules the big model writes, e.g. "all
  Twilio calls through one gateway module") lives in scratch for the run and is
  **archived to the umbrella ticket** at completion, with the PRD. Nothing per-feature
  is ever committed — no stale landmines for future sessions.
- A **run-id** is minted by `:design` and tags every artifact and (when the router is
  on) every API request.

## 5. Stage 1 — `/slopstop:design` (big)

1. Tier gate; mint run-id; seed `scratch/runs/<run-id>/`.
2. Run the grill (`/slopstop:grill`) with the user to shared understanding.
3. Write the **PRD** and **feature charter** to the run dir, provenance headers on.
4. Report at **G1** and stop.

## 6. Stage 2 — `/slopstop:tickets` (medium)

1. Tier gate; read PRD + charter from the run dir — artifacts only.
2. Cut the tree: umbrella tickets (multiple levels fine) with leaf work items linked
   to their parent. Every leaf follows the **five-section standard** — observable
   behaviors (2–5), file map, definition of done, out-of-scope list, test
   expectations — sized for a small-model consumer: what isn't in the ticket doesn't
   exist. (Full standard + template: the `:tickets` skill's references.)
3. **Big-tier adversary review** of the tree — fresh invocation, sees only PRD +
   charter + tickets. Mechanical structural check first (five sections present), then
   conformance (omissions, scope drift, implementability, face-value traps). Findings
   are specific (ticket, section, defect); medium corrects; **≤3 rounds**; exhaustion
   goes to the human.
4. Report at **G2** (tree summary + adversary verdict + spend line) and stop.

Ticket-title version convention: rewrites append `(V2)`, `(V3)`.

## 7. Stage 3 — `/slopstop:run` (medium orchestrator)

### 7a. Agent contract

One agent ⇄ one ticket ⇄ one branch ⇄ one worktree. Every fleet agent brief includes:

- Follow the **base process**: `:start` → `:plan --ticket-driven --inline` → work →
  `:update` → `:pr --inline` → **decline the PR** → stop. Never `:merge` — integration
  is the orchestrator's (§7f). `--inline` is mandatory on both `:plan --inline` and
  `:pr --inline`: sub-agent completion notifications inside a worktree agent route to
  the top-level loop and deadlock the fleet otherwise (`--ticket-driven` selects the
  profile; `--inline` selects the execution mode — they compose).
- **`:plan --ticket-driven`** (auto-selected when the ticket has the five sections):
  no free investigation — the file map is the territory. Red tests are transcribed
  from the ticket's test expectations and shown failing before implementation. If the
  map/spec is wrong: the **"ticket underspecified" stop** — commit nothing, report the
  specific mismatch to the ticket, halt. Routes to a Stage-2-style rewrite **without
  consuming attempts**: bad tickets are Stage 2 defects, not Stage 3 failures.
- **Hermetic seal:** never touch files outside the worktree, with one carve-out —
  `$TRACKING_DIR` (base-process tracking files land there by design). `scratch/runs/`
  belongs to the orchestrator; agents never write it.
- **Reporting protocol:** one ticket comment per base-process command, plus a progress
  comment per material work unit (red tests failing, each behavior done, tests green).
  These markers are load-bearing — they are what monitoring reads.
- **Same-size adversaries** at `[fleet.agents].adversary_effort` (§1).
- Commit subjects start with `[$TICKET]`; commit small and often.

### 7b. Launch order — dependency-first, merge-safety-driven

Order agents so that if they all succeed, integration is conflict-free by
construction. Driven by **file affinity** — the tickets' file maps — plus explicit
relations (blocked-by, umbrella structure):

- **Disjoint file maps → parallel.** Overlapping → serialize; the later agent branches
  off the tip that already contains the earlier one's landed work.
- **Explicit dependencies always win** over the file heuristic.

### 7c. Monitoring — autonomous kill authority

The orchestrator polls per `[fleet.monitoring]` (defaults: 5-minute cadence) reading
ticket comments and peeking worktrees (`git status`, file mtimes). Triggers:

| Signal | Action |
|---|---|
| quiet ≥ `quiet_investigate_min` | investigate the worktree — activity without comments is a nudge, not a kill |
| silence ≥ `silence_kill_min` (no comments AND no activity) | kill |
| same failure across `loop_kill_reports` consecutive reports | kill |
| **file-map violation** (worktree changed-files vs ticket file map) | kill **instantly** when `filemap_violation = "kill"`; log-only in `"warn"` mode (use while evaluating small models) |

Kills are autonomous, consume an attempt, are recorded in fleet state with the reason,
and the relaunch brief cites it. No human interrupts — kills surface in reports.

**Fleet state is externalized** to `scratch/runs/<run-id>/fleet-state.md` (ticket →
agent, attempt, version, last marker, verdicts), updated on every event. The file is
the source of truth; the orchestrator's conversation history is disposable.

### 7d. Handoff verification

When an agent reports done, the orchestrator trusts nothing. Two **fresh medium-tier
subagents** read the actual worktree/diff — never the agent's claims — and return
verdict-only structured results (pass/fail + file:line findings); the orchestrator
context never ingests diffs:

1. **Adversary** — requirements conformance against the ticket's DoD and behaviors:
   missing criteria, vacuous tests, scope violations, criteria met only on paper.
2. **Code reviewer** — is the implementation acceptable.

Either fails → relaunch the agent **in the same preserved worktree** with the specific
findings in the brief (consumes an attempt).

### 7e. Failure handling — budgets, rewrites, escalation

Budgets from `[fleet.budget]`: **3 attempts per ticket version × 3 versions × 1 tier
escalation.** After 2 failed attempts, medium diagnoses:

- **Ticket defect → rewrite.** The rewrite cites the specific code and the specific
  instruction that failed (file:line, quoted DoD item). A changed ticket is a **new
  contract**: fresh agent, fresh attempt budget, title gains `(V2)`/`(V3)` — in the
  **same preserved worktree** (an explicit, recorded reset-to-branch-point is allowed
  when the approach is unsalvageable; never the default). **Every rewrite passes a
  fresh big-tier delta check before relaunch:** did it add specificity or subtract
  scope? Rewrite-under-failure-pressure is the most drift-prone moment in the
  pipeline; scope subtraction is rejected, or surfaced to the human if the scope
  genuinely was wrong.
- **Capability gap → tier escalation.** Attempt 3 runs on
  `[fleet.agents].escalation_model`. Autonomous, recorded, max one per ticket.

Worktrees are never discarded on failure — deletion only at (human-approved) abandon
or after integration. Budget exhausted → **G4**, with the failure ledger and per-ticket
spend: **grant more attempts / authorize another rewrite (delta check still applies) /
salvage (the orchestrator implements in the preserved worktree — human-authorized
only, never autonomous) / abandon.** The fleet keeps running independent tickets
while G4 pends.

The diagnosis routing doubles as evaluation data: bad-ticket failures vs capability
failures are distinguishable in the ledger.

### 7f. Integration — `:merge` from the root

Blessed work (adversary pass, or human-approved salvage confirmed) integrates
**serially, in the §7b dependency order**, via `:merge <TICKET>` run from the root
checkout on the primary branch — never a hand-rolled git merge:

- `:merge <TICKET>` resolves the PR from the ticket key, **reopens the declined PR**,
  merges, fires the ticket transitions, pulls the root forward (`--ff-only`), and
  cleans up the agent worktree and branch.
- Conflicts are rare by construction; when they occur, the orchestrator resolves and
  re-runs the suite before accepting.

### 7g. Umbrella completion — drift checks

When an umbrella's leaves are all integrated, medium writes an **umbrella report** to
the run dir and a **fresh big-tier drift check** runs it against the PRD + charter —
the automation that replaced the per-umbrella human gate. Failures come back as
specific findings; medium reconciles or escalates to G4.

## 8. Final report and G-final

Medium assembles the report (provenance header on):

1. **Outcome table** — per umbrella/leaf: status, version reached, attempts,
   escalations, kills with reasons.
2. **Deviation ledger** — every rewrite + its delta verdict, scope questions,
   abandonments.
3. **Verification state** — suite result on the integrated tip, adversary verdicts,
   the whole-run drift check vs PRD + charter.
4. **Spend** — total, per tier, per ticket (or the degraded-mode line).
5. **Archive confirmation** — PRD + charter attached to the umbrella ticket.

Then the pipeline's most important adversary: a **fresh big-tier pass** whose charter
is *"given the PRD, charter, and the G2 tree, prove this report wrong or
**incomplete**."* The final report is medium grading its own homework — the one
self-assessment in the pipeline — so the adversary hunts **omissions** (unreported
kills, quietly dropped tickets, aggregate scope shrinkage across rewrites), works from
ground truth (git log, actual ticket states, router spend records), and **re-runs the
test suite itself**. Findings → medium corrects (the report, or the work) → ≤3 rounds
→ human. The report reaches **G-final** already adversaried, verdict attached.

## 9. Context economy

1. **Stage boundaries carry artifacts, not transcripts** (§3).
2. **Fleet state lives on disk** (§7c) — compaction-safe.
3. **Verdict-only structured returns** from every subagent; no narratives, no diffs.
4. **Diff reading happens in throwaway subagent contexts** (§7d) — the orchestrator
   holds only the tree, the state table, and verdicts.
5. Stage skills load only their own stage's references — `:run` never loads grill
   material.

## 10. Router — metering (Phase 1)

Optional infrastructure, `[fleet.router]`, shipped `enabled = false` (agents talk to
the API directly; reports carry "cost tracking disabled"). When enabled:

- A local **transparent proxy** speaks Anthropic Messages format on both sides,
  forwards verbatim (streaming and auth headers intact), reads the run-id (header or
  `/r/<run-id>` path prefix), meters the `usage` block of each response against a
  price table, and serves `GET /spend?run=<id>`. Per-run attribution stays correct
  under concurrent runs.
- `:design` health-checks it at run start; `:run` health-checks it at **each agent
  launch**, pointing agents at it via `ANTHROPIC_BASE_URL`. Unreachable → that agent
  falls back to direct API access and reports note "cost tracking unavailable (since
  <time>)" — **a dead router never blocks a run.**
- Spend lines appear in every report: G2, every G4 ledger, and the final report
  (per-tier and per-ticket — the small-model evaluation data).
- Phase 2 (model-name routing to local models, OpenAI-format translation) is
  deliberately out of scope here; nothing in Phase 1 constrains it.

## Rules

- **Nothing at face value** — checkers are fresh, artifact-fed, and ground-truthed.
- **Human gates are G1, G2, G-final, G4 — nothing else.** Kills, escalations, and
  drift checks are autonomous and reported, not asked.
- **One agent, one ticket, one branch, one worktree.** Agents never merge; the
  orchestrator never implements (except human-authorized salvage).
- **A clean `:pr` review is necessary, never sufficient** — the handoff adversary
  gates integration.
- **Every rewrite is delta-checked** by big before any relaunch.
- **Worktrees are preserved** across attempts and rewrites.
- **Budgets are hard:** 3 × 3 × 1, then a human decides.
- All base-process safety rules (no force-push, no `--no-verify`, ticket-anchored
  commits) bind every tier — see [base-process.md](base-process.md).
