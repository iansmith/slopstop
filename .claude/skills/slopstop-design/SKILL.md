---
description: Stage 1 of the slopstop process — grill the user to shared understanding, then write the PRD and feature charter into the run dir and stop at gate G-design. Huge-tier only. Invoke as /slopstop-design <topic>.
disable-model-invocation: true
---

<!-- GENERATED from slopstop fe05629-dirty by install-for-project.sh — do not edit.
     Edit skills/design/ in the slopstop repo and re-run. (universal §5) -->

# /slopstop-design

Stage 1 of the slopstop process. Runs on the **huge tier**. Output: a run dir under
`scratch/runs/` holding `run.jsonl`, the PRD, and the charter, presented to the human at
gate **G-design**. Never cuts tickets (that is Stage 2, `/slopstop-tickets`) and never
implements anything.

`:design` is an **orchestrator**. It launches almost nothing — subagents cannot talk to
the user, and this stage is a conversation, so the grill runs inline (Step 2) — but it
creates the run dir, so it writes the first lines of `run.jsonl` and owns the run's
records. That makes the bracketing in Step 0c matter more here than anywhere else.

- → Read `.claude/skills/slopstop-run/references/run-jsonl.md` — the schema, the sole-writer rule, the
  human-wait bracketing, the validation invariants. Do not restate or re-invent it.
  **Span or note is decided by the rule there, not per stage**: a worker launch or a loop
  round is a span, a single atomic act is a note, and every `stage` value is one of yours.
- → Read `.claude/skills/slopstop-run/references/worker-launch.md` — the single `Agent()` launch form and
  stage → tier → model resolution, for anything this stage ever launches.

**You are the sole reader of the resolved configuration** — three sets, defaults →
`.project-conf.toml` → gitignored `.project-conf-local.toml`, merged per leaf key.
→ Read `.claude/skills/slopstop-run/references/config-resolution.md`
 Resolve every value here, apply the
documented default for any absent key, pass resolved values as explicit arguments — nothing
you launch reads config.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `$PREFIX` (`prefix`),
`[stage_tiers]`, `[tiers]` (defaults: huge=`fable`, large=`opus`, medium=`sonnet`,
small=`haiku`) and `[design] spec` (default: unset — see **Resolving the spec**). Stop with
a clear error if `prefix` is absent or doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Missing
config file: stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop-gh-init or create the file manually with system + key."`
Missing tables resolve to defaults — never error.

## Arguments

`$ARGUMENTS` is the topic — a feature name or a brain-dump. If empty, ask for one
sentence on what is being designed, then proceed.

`--spec <path>` — **repeatable.** Names an authoritative specification document for this
run. Every decision in the PRD is classified against the resolved spec (Step 3), and the
ticket-tree adversary's check F re-reads it. Pass it once per document.

### Resolving the spec

In order; the first that yields anything wins:

1. every `--spec <path>` given on this invocation (all of them),
2. `[design] spec` in `.project-conf.toml` (a string or an array of strings),
3. a conventional path — `SPEC.md`, then `docs/spec*.md`. **Propose it and ask**; never
   adopt one silently. A wrong spec is worse than none, because every downstream
   classification then cites the wrong document.

For each resolved path: confirm it exists (a declared spec that is missing is a hard stop,
not a warning) and compute its `sha256`. Record both in the PRD header, one line each —
`> SPEC: docs/api-contract.md (sha256 3f9a…c21b)`.

If nothing resolves, record exactly `SPEC: none — greenfield` and continue. That is a
legitimate state — most feature work has no external spec — and it means Step 3's
decisions default to `UNDERDETERMINED` unless they derive from the grill itself.

## Step 0 — Mint the run and open `run.jsonl`

The run dir is created **before** the tier gate: that gate's cannot-determine path blocks on
the user, and a block on the user has to be bracketed — which needs the file. `$RUN_ID` =
`<topic-slug>-<UTC yyyymmdd-HHMM>` (e.g. `twilio-20260709-1802`) — unique without a counter.
It tags every artifact this run produces and selects the run dir for Stage 2.

### 0b — Seed `scratch/` and `.slopstop/` at the main worktree root

```bash
ROOT="$(dirname "$(git rev-parse --git-common-dir)")"
mkdir -p "$ROOT/scratch/runs/$RUN_ID" "$ROOT/.slopstop/ticket-active" "$ROOT/.slopstop/ticket-archive"
git -C "$ROOT" check-ignore -q scratch/   || echo 'scratch/'   >> "$ROOT/.gitignore"
git -C "$ROOT" check-ignore -q .slopstop/ || echo '.slopstop/' >> "$ROOT/.gitignore"
RUNLOG="$ROOT/scratch/runs/$RUN_ID/run.jsonl"
```

`:design` is a seeding path, so it ignores **both** directories, exactly as `:gh-init` Step
8b does. Creating `.slopstop/` activates tier-2 tracking-dir resolution for every other
skill, so the gitignore entry must land in the same run — otherwise a later `git add -A`
sweeps every tracking dir into the first PR.

**There is no `run.md`.** `run.jsonl` is the run state file, and it is the only one — two
state files for one run is a §5 violation waiting to drift.

### 0c — How this stage writes `run.jsonl`

Append with `>>`, one JSON object per line, every line carrying `at`:

```bash
printf '%s\n' "{\"stage\":\"grill\",\"event\":\"started\",\"at\":\"$(date -u +%FT%TZ)\"}" >> "$RUNLOG"
```

Open the log with a `note` recording topic, session model, resolved tier, and the resolved
spec paths with their hashes.

**Bracket every block on the user.** This stage is mostly human conversation, so the
bracketing carries the whole timing model here: a user can walk away for a weekend
mid-grill, and wall clock without these spans is meaningless. Open the `waiting_for_user`
span in the same step that asks, close it in the same step that receives the answer —
never as a separate thing to remember. The sites:

| site | `result` field |
|---|---|
| empty-`$ARGUMENTS` topic question | `topic` |
| conventional-spec adoption prompt (resolution rule 3) | `spec_confirm` |
| tier-gate cannot-determine confirmation (Step 1) | `tier_confirm` |
| **each grill question** (Step 2) | `grill Q<n>` |

Also bracket your own substantive phases so they are measurable: `grill`, `classify`,
`prd`, `charter`. Those are run-level spans — omit `ticket`.

**Never open a span you cannot close.** The G-design gate ends the session, so it is not a
`waiting_for_user` span; it is bounded by `run_closed` here and `session_resume` in `:tickets`.

## Step 1 — Tier gate

Resolve the required model in two hops: `[stage_tiers].design` names the tier (default
`huge` if the table or key is absent), then the `[tiers.<that tier>]` sub-table gives
`provider`, `model`, and optional `version` — call them `$TIER`, `$MODEL`, `$VERSION`.
**`provider` is never gated on**: a session cannot verify its own endpoint, so gating on
it would make every gate "cannot determine".

**Reject the old string form.** If `[tiers].<tier>` is a bare string (`huge = "fable"`)
rather than a `[tiers.<tier>]` table — **hard stop**:
`"[tiers].$TIER is the old string form; slopstop requires the table form: [tiers.$TIER] with provider/model and optional version. Migrate .project-conf.toml."`

Compare the session model against the spec (the session knows its own model,
e.g. `claude-fable-5`):

- **`$MODEL` (family)** must match — the family name appears in the session model
  (`claude-fable-5` matches `model = "fable"`).
- **`$VERSION`**, when pinned, must match as a **dotted prefix** of the session model's
  version: `4.8` matches `claude-opus-4-8`, `5` matches `claude-fable-5`. An **omitted**
  `version` passes any version of the family.
- **Match** → proceed; append a `tier_gate` note with `$TIER`, `$MODEL`, `$VERSION`.
- **Mismatch** → **hard stop**:
  `"Tier gate: /slopstop-design requires the $TIER tier ('$MODEL', version $VERSION when pinned); this session is running '<session model>'. Relaunch on the right model (or edit [stage_tiers]/[tiers] — bad configs give bad results)."`
- **Cannot determine** (no model self-knowledge, or `$MODEL` matches nothing the session
  knows about itself) → never proceed silently. Bracket the ask (`tier_confirm`):
  `"I can't verify this session's model against the $TIER tier ('$MODEL', version $VERSION when pinned). Confirm this session is running the $TIER tier? (yes / abort)"`
  Record the human confirmation as a `tier_gate` note.

Do not soften this to a warning. A wrong-tier PRD looks right and poisons every gate below it.

## Step 2 — Grill to shared understanding

Open the `grill` span, then invoke the vendored grill inline against the topic —
`Skill({skill: "slopstop-grill", args: $ARGUMENTS})`. (Desktop-installed sessions name it
`slopstop-grill`. One question at a time, recommended answers, explore the codebase
instead of asking where possible.)

**Bracket every question.** As part of asking, append the `waiting_for_user` `started`
with `result: "grill Q<n>"`; as part of reading the reply, append the `finished`. Twenty
questions leave twenty pairs — the only thing separating thinking time from a weekend away.

The grill ends when no unresolved branches remain; close the `grill` span. Its summary is
the raw material for Step 3.

## Step 3 — Classify every decision against the spec

Open the `classify` span. The PRD is ground truth for every gate below it — Stage 2's
adversary checks the *tree against the PRD*, red tests come from tickets, review checks
code against tickets — and nothing downstream re-reads the source. So the PRD must say,
per decision, what that decision rests on:

| Class | Means | Must record |
|---|---|---|
| **`SPEC`** | the source settles it | the exact quoted source text, and which spec it came from |
| **`DERIVED`** | it follows from quoted source text by reasoning | the quote **and** the reasoning step |
| **`UNDERDETERMINED`** | the source does not settle it | the alternative reading(s), and why this one was chosen |

**Classify honestly — `UNDERDETERMINED` is not a failure.** A spec that does not answer
every question is normal; a PRD that *pretends* it did is the failure mode. If the quoted
text does not distinguish your reading from a plausible alternative, the decision is
`UNDERDETERMINED` however well-argued it is.

**A decision may not rest solely on another decision from this same PRD.** Two decisions
that support each other are internally consistent and jointly unfounded — cite the source,
or classify as `UNDERDETERMINED`. Close the span with the counts as its `result`.

> **Stamp each span from the clock, at the moment.** `date -u +%FT%TZ` when the work
> starts, and again when it ends — never several stamps reconstructed at the end of the
> stage. The first real run of this skill wrote `classify`-finished, `prd`-started,
> `prd`-finished, `charter`-started and `charter`-finished at one identical timestamp, so
> an 11.6 KB PRD and a 3.8 KB charter both measured zero seconds. The file validated and
> looked complete. Writing the PRD and the charter is the most substantial machine work
> this stage does, and it is the work whose cost is now unknown.

## Step 4 — Write the PRD and the feature charter

Both files go in `scratch/runs/$RUN_ID/`, each written inside its own span (`prd`, then
`charter`), both opening with `> Provenance: <model> · <UTC date> · run $RUN_ID`.

- **`prd.md`** — thesis, every resolved decision with its rationale and its Step 3
  classification, explicit deferrals with owners, the scope boundary. Open it with the
  `SPEC:` header line(s) resolved in Arguments. Write it so Stage 2 can cut tickets from it
  without access to this conversation — the PRD is the only thing crossing the boundary. It
  carries a mandatory `## Underdetermined decisions` section listing every decision in that
  class with its alternatives; when behaviour later turns out wrong, that section is the
  first place to look — the list of choices that could have gone the other way.
- **`charter.md`** — the broad-stroke rules the implementation must respect for THIS
  feature ("all Twilio calls through one gateway module", "no schema migrations in this
  run"). Rules only — no design detail; that's the PRD's job. The charter complements the
  project's standing rules; it never overrides them.

Neither file is ever committed; both are posted to the umbrella ticket at run completion by `skills/document/references/document-archive-artifacts.md`.

## Step 5 — Gate G-design: report and stop

**Validate `run.jsonl` before reporting any number** — every `started` closed, every line
parsing, every line carrying `at`. On failure, name the unclosed spans and report **no
timing at all**; a broken record must not produce a plausible-looking summary.

Then append the closing note — `{"event":"note","stage":"run_closed",…}` — and present
(report unattributed time; never redistribute it):

```
G-design — design complete for run $RUN_ID

Spec:     <path> (sha256 <short>) | none — greenfield
PRD:      scratch/runs/$RUN_ID/prd.md      (<n> decisions — <n> SPEC, <n> DERIVED, <n> UNDERDETERMINED; <n> deferrals)
Charter:  scratch/runs/$RUN_ID/charter.md  (<n> rules)
Timing:   <wall> wall · <human idle> waiting on you · <active> active · <unattributed> unattributed
Plugin:   /plugin install slopstop@slopstop   (load the slopstop plugin in the next session)

Go ahead with ticket breakdown?
Next: /slopstop-tickets $RUN_ID   (large tier, fresh session — the run-id
selects the run dir; without it Stage 2 would have to guess among runs)
```

**Stop.** Do not cut tickets, do not launch anything. The human drives the stage
transition; Stage 2 reads the artifacts, not this transcript. If the conversation
continues here anyway (revisions instead of moving on), append a `session_resume` note,
bracket the further exchanges as in Step 0c, and close with a fresh `run_closed`.

## Rules

- Huge tier only; the tier gate is a hard stop, and its result is a `run.jsonl` note.
- `run.jsonl` is append-only and you are its sole writer. Never rewrite, compact, or
  delete a line — both endpoints are needed for every duration.
- Everything this stage produces carries the provenance header.
- The stage boundary is artifact-only: Stage 2 must be able to run from `prd.md` +
  `charter.md` alone — plus `run.jsonl`, which it continues rather than replaces.
