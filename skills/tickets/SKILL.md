---
description: Stage 2 of the slopstop process — read the PRD + charter from the run dir, cut the umbrella/leaf ticket tree per the five-section standard, drive the big-tier adversary loop over it, and stop at gate G2. Medium-tier only. Invoke as /slopstop:tickets <run-id>.
disable-model-invocation: true
---

# /slopstop:tickets

Stage 2 of the slopstop process (`design/slopstop-process.md` §6). Runs on the
**medium tier**. Input: the run dir a `/slopstop:design` session produced. Output: an
adversary-approved ticket tree in the project's ticket system, presented at gate
**G2**. This skill never launches implementation agents (Stage 3, `/slopstop:run`)
and never handles rewrites (Stage 3 owns failure-driven rewrites).

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `key` (`$PREFIX`),
`[tiers]` (defaults fable/opus/haiku), `[fleet.router]` (default disabled). Missing
config file: stop with the standard gh-init message. Missing tables → defaults.

## Arguments

`$RUN_ID` — the run to cut tickets for (handed off by `:design`'s G1 report). If
empty: list `scratch/runs/*/` and ask which run; never guess. The run dir must
contain `prd.md` and `charter.md`; if either is missing, stop:
`"Run $RUN_ID has no <file> — Stage 1 didn't complete. Re-run /slopstop:design."`

## Step 1 — Tier gate

Compare the session model against `[tiers].medium` (family-name match, e.g. a session
on Opus matches `medium = "opus"`).

- **Match** → proceed. **Mismatch** → **hard stop**:
  `"Tier gate: /slopstop:tickets requires the medium tier ('<[tiers].medium>'); this session is running '<session model>'. Relaunch on the right model."`
- **Cannot determine** → ask the user to confirm the tier; record the confirmation in
  `run.md`. Never proceed silently.

## Step 2 — Read the artifacts (and nothing else)

Read `scratch/runs/$RUN_ID/prd.md` and `charter.md`. **The stage boundary is
artifact-only:** do not read Stage 1's transcript, do not ask the user to fill PRD
gaps from memory — a gap in the PRD is a Stage 1 defect (note it; if it blocks
ticket-cutting, stop and send the user back to `:design`).

Update `run.md`: `Stage: tickets (G2 pending)`.

## Step 3 — Cut the tree (drafts first, on disk)

Draft the full tree to `scratch/runs/$RUN_ID/ticket-tree-draft.md` **before creating
anything** in the ticket system — the adversary reviews drafts; creation happens only
after the loop passes.

- **Umbrellas**: scope + structure, multiple levels fine. Leaves always have a parent.
- **Leaves**: the five-section standard — every section, sized for a small-model
  consumer. Full standard, template, and the structural checklist:
  → Read `~/.claude/commands/slopstop-tickets-refs/ticket-standard.md`
- Dependencies: `Blocked by:` lines referencing other drafts via **unambiguous
  placeholder tokens** — `%%A%%`, `%%B%%` (never bare letters, which collide with
  prose) — resolved to real ticket keys at creation time (Step 5 / dispatch). A
  dependency summary at the bottom of the draft, including the parallel-safe first
  wave (disjoint file maps).
- Every draft body opens with the provenance header
  (`> Provenance: <model> · <date> · run $RUN_ID · PRD: scratch/runs/$RUN_ID/prd.md`).

Run the standard's **structural checklist** over every leaf yourself before spending
the adversary on it — structure failures are yours to fix for free.

## Step 4 — The big-tier adversary loop (≤3 rounds)

Spawn a **fresh** adversary subagent at `[tiers].big`, fed **only** the artifacts —
`prd.md`, `charter.md`, the draft file — never your narrative. Prompt template:
→ Read `~/.claude/commands/slopstop-tickets-refs/tickets-adversary.md`

The adversary returns PASS, or FAIL with findings that are **specific** (draft ticket,
section, defect, and what would fix it). On FAIL: apply the corrections to the draft,
then send the corrected draft back for re-verification. **At most 3 rounds** (initial
+ 2 corrections). Still failing after round 3 → stop and present the surviving
findings to the human — do not create any tickets.

Rounds and outcomes are recorded in `run.md`.

## Step 5 — Create the tickets

Only after a PASS. Create in dependency-aware order so every `Blocked by:` reference
points at an already-created ticket; link leaves to their umbrellas. Per-system
dispatch (GitHub sub-issues via `gh api .../sub_issues`; Linear parent links; JIRA
epic links):
→ Read `~/.claude/commands/slopstop-tickets-refs/tickets-create-dispatch.md`

Record the draft-letter → ticket-key mapping in `run.md`.

## Step 6 — Gate G2: report and stop

Router line — status only, same as G1: Stage 1–2 traffic (including this session's
adversary subagents) is **unrouted**; only `:run`'s fleet agents get pointed at the
router, so `GET /spend?prefix=$PREFIX&run=$RUN_ID` cannot yet carry a meaningful figure. Present:

```
G2 — ticket tree created for run $RUN_ID

Tree:      <n> umbrellas, <n> leaves — root <key>
           <two-line shape summary>
Adversary: PASS after <n> round(s) — <findings summary: n found, n fixed>
Router:    <"router healthy (status only — Stage 1–2 traffic unrouted)" | "cost tracking disabled" | "cost tracking unavailable">
Launch:    ANTHROPIC_BASE_URL=<router-url> ANTHROPIC_CUSTOM_HEADERS="X-Slopstop-Run: $RUN_ID\nX-Slopstop-Ticket: <ticket>"
           (for Stage 3: metered by default)

Launch the fleet? Next: /slopstop:run $RUN_ID   (medium tier, fresh session)
```

The G2 report itself carries the provenance header (in `run.md`'s G2 entry). Update
`run.md`: `Stage: tickets complete — G2 presented`. **Stop.** No fleet launch, no
implementation, no rewrites.

## Rules

- Medium tier only; adversary always big-tier, always fresh, always artifact-fed.
- Drafts are adversaried; the ticket system only ever receives an approved tree.
- ≤3 adversary rounds, then the human — never create tickets past a failing verdict.
- Every ticket body and the G2 record carry provenance headers.
- Nothing at face value: the adversary sees artifacts, not your summary of them.
