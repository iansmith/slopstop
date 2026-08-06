---
description: Stage 2 of the slopstop process — read the PRD + charter from the run dir, cut the umbrella/leaf ticket tree per the five-section standard, drive the adversary loop over it, write the approved tree to the ticket system, and stop at gate G-tickets. Invoke as /slopstop:tickets <run-id>.
disable-model-invocation: true
---

# /slopstop:tickets

Stage 2 of the slopstop process. **This skill is an orchestrator**: it launches timed work
as agents, and it records every transition in `run.jsonl`. Input: the run dir a
`/slopstop:design` session produced. Output: an adversary-approved ticket tree in the
project's ticket system, presented at gate **G-tickets**.

It never launches implementation work — that is `/slopstop:run`.

## The two shared contracts — read both before doing anything

Both are binding, and neither is restated here (universal §5, one definition):

- **The timing/state file** — schema, sole-writer rule, human-wait bracketing, validation:
  → Read `~/.claude/commands/slopstop-run-refs/run-jsonl.md`
- **The worker launch form** — the single `Agent()` shape, model resolution, the roster:
  → Read `~/.claude/commands/slopstop-run-refs/worker-launch.md`

Two consequences that govern every step below:

- **You are the sole writer of `run.jsonl`**, at `scratch/runs/$RUN_ID/run.jsonl`. No
  worker writes it, no worker resolves a path. A worker returns a result; you stamp it.
- **You are the sole reader of `.project-conf.toml`.** Workers get resolved values as
  arguments and read no config themselves.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `$PREFIX` (`prefix`
field), `[stage_tiers]`, and `[tiers]`. Stop with a clear error if `prefix` is absent, and
stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Missing config file: stop with the
standard gh-init message. Missing tables → documented defaults, never an error.

## Arguments

`$RUN_ID` — the run to cut tickets for (handed off by `:design`'s G-design report). If
empty: list `scratch/runs/*/` and ask which run — bracket that ask in a
`waiting_for_user` span — never guess. The run dir must contain `prd.md` and `charter.md`;
if either is missing, stop:
`"Run $RUN_ID has no <file> — Stage 1 didn't complete. Re-run /slopstop:design."`

## Step 1 — Tier gate

Resolve your own tier in two hops: `[stage_tiers].tickets` names the tier (default
`large`), then `[tiers].<that tier>` — the `[tiers.<tier>]` sub-table — gives `provider`,
`model` (family, `$MODEL`) and optional `version` (`$VERSION`). **`provider` is never
gated on** (router-only; a session cannot verify its own endpoint). If `[tiers].<tier>` is
still the old bare-string form, **hard stop**: `"[tiers].$TIER is the old string form; use
the table form [tiers.$TIER] with provider/model (+ optional version). Migrate
.project-conf.toml."`

Family `$MODEL` must appear in the session model; a pinned `$VERSION` must be a dotted
prefix of the session model's version (`4.8` matches `claude-opus-4-8`); an omitted
version passes any version of the family.

- **Match** → proceed. **Mismatch** → **hard stop**: name the required tier, the required
  model, and the session's actual model, and say to relaunch.
- **Cannot determine** → ask the user to confirm (bracketed as a `waiting_for_user` span);
  record the answer as a `note`. Never proceed silently.

## Step 2 — Open the run log

Open `scratch/runs/$RUN_ID/run.jsonl` (append-only; create if absent). If it already has
lines, this is a resume: **validate it before continuing**, and write a `session_resume`
note. A validation failure means you report no timing at all — name the unclosed spans and
stop.

Then open the run-level span for this stage.

## Step 3 — Read the artifacts, and nothing else

Read `scratch/runs/$RUN_ID/prd.md` and `charter.md`. **The stage boundary is
artifact-only:** do not read Stage 1's transcript, and do not ask the user to fill a PRD
gap from memory. A gap in the PRD is a **Stage 1 defect** — record it as a `note`; if it
blocks ticket-cutting, bracket a `waiting_for_user` span and send the user back to
`:design`.

## Step 4 — Cut the tree (drafts to disk first)

Draft the full tree to `scratch/runs/$RUN_ID/ticket-tree-draft.md` **before creating
anything** in the ticket system. The adversary reviews drafts; creation happens only after
the loop passes. Bracket the drafting work as its own span.

- **Umbrellas**: scope + structure, multiple levels fine. Every leaf has a parent.
- **Leaves**: the five-section standard — every section, sized for a small-model consumer.
  Full standard, template, and structural checklist:
  → Read `~/.claude/commands/slopstop-tickets-refs/ticket-standard.md`
- Dependencies: `Blocked by:` lines referencing other drafts through **unambiguous
  placeholder tokens** — `%%A%%`, `%%B%%` (never bare letters, which collide with prose) —
  resolved to real keys at creation time. Close the draft with a dependency summary,
  including the parallel-safe first wave (disjoint file maps).
- Every draft body opens with the provenance header
  (`> Provenance: <model> · <date> · run $RUN_ID · PRD: scratch/runs/$RUN_ID/prd.md`).

Run the standard's **structural checklist** over every leaf yourself before spending an
adversary round on it — structure failures are yours to fix for free.

## Step 5 — The adversary loop (you own the loop; ≤3 rounds)

The `adversary` worker performs **one round** and returns. It does not loop, and it never
creates or edits anything. Launch it per `worker-launch.md`:

- **Model**: resolve `[stage_tiers].ticket_adversary` (default `huge`) → `[tiers]`. **The
  adversary runs one tier above the work it checks** — `tickets` is `large`,
  `ticket_adversary` is `huge`. That ladder is deliberate; do not flatten it.
- **Arguments**: `--target scratch/runs/$RUN_ID/ticket-tree-draft.md`
  `--goals scratch/runs/$RUN_ID/prd.md,scratch/runs/$RUN_ID/charter.md`
  `--caliber structure,coverage,fidelity,implementability,face-value,provenance,circularity`
  `--round <n>` and, from round 2, `--prior scratch/runs/$RUN_ID/adversary-round-<n-1>.md`.
- **Round 1 is the draft's first sight of a fresh reader.** Never pass your own narrative,
  your summary of the PRD, or the reasoning that produced the tree — only artifact paths.

Bracket each round: write `started` in the same step that launches, and
`finished`/`failed` in the same step that receives the result. Persist the returned
findings yourself to `adversary-round-<n>.md` — the worker writes nothing.

Branch on the verdict line:

| verdict | what it means | what you do |
|---|---|---|
| `ADVERSARY PASS` | nothing survives | close the span `finished`, go to Step 6 |
| `ADVERSARY FAIL: n` | the **tree** is wrong | correct the draft, re-launch as round `n+1` |
| `ADVERSARY GOAL DEFECT: n` | the **PRD or charter** is wrong | stop the loop; escalate |
| `ADVERSARY BLOCKED: …` | you passed a bad argument | fix the argument and relaunch — this does not consume a round |

**On FAIL** (rounds 1 and 2): apply every finding to the draft, then re-verify.
**The argue-don't-ignore rule: a finding you disagree with is argued in the correction
note, never silently dropped.** Write the correction note into `adversary-round-<n>.md`
beside the findings, so round `n+1` reads both the corrected draft and your argument.

**On FAIL at round 3** (the cap): stop. Create no tickets. Present the surviving findings
with the draft to the human, inside a `waiting_for_user` span. The human may overrule
specific findings — record each overrule as a `note` — or send the tree back for a rethink.

**On GOAL DEFECT**: this is a **Stage 1 defect, not a tree defect**, and it is neither
yours nor the adversary's to fix — amending the PRD or charter is a human decision.
Surface it at once inside a `waiting_for_user` span, quoting the goal defects verbatim and
any target findings reported alongside them. Do not correct the draft to route around a
wrong goal, and do not create tickets. If the human amends the artifacts, restart the loop
at round 1 against the amended goals.

## Step 6 — Create the tickets

Only after a PASS. Create in dependency-aware order so every `Blocked by:` reference points
at an already-created ticket, and link leaves to their umbrellas. Per-system dispatch
(GitHub sub-issues, Linear parent links, JIRA epic links):
→ Read `~/.claude/commands/slopstop-tickets-refs/tickets-create-dispatch.md`

This is mechanical work — run it inline, no worker. Bracket it as one span, and record the
placeholder-token → ticket-key mapping as a `note`.

## Step 7 — Gate G-tickets

Present:

```
G-tickets — ticket tree created for run $RUN_ID

Tree:      <n> umbrellas, <n> leaves — root <key>
           <two-line shape summary>
Adversary: PASS after <n> round(s) — <n> found, <n> fixed, <n> argued
Timing:    <wall> wall · <active> active · <human idle> waiting on you
           <unattributed, reported not redistributed>

Next: /slopstop:run $RUN_ID
```

Timing comes from one pass over `run.jsonl` — validate it first, and if validation fails,
report the unclosed spans and **no numbers**. Close the run with a `run_closed` note.
**Stop.** No fleet launch, no implementation, no rewrites.

## Rules

- Drafts are adversaried; the ticket system only ever receives an approved tree.
- ≤3 adversary rounds, then the human — never create tickets past a failing verdict.
- The adversary sees artifacts, never your summary of them.
- Findings you disagree with are argued, never dropped.
- A goal defect goes to the human, unmodified and immediately.
- Every ticket body carries a provenance header.
