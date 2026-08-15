---
description: Stage 1 of the slopstop process — grill the user to shared understanding, then write the PRD and feature charter into the run dir and stop at gate G-design. Huge-tier only. Invoke as /slopstop:design <topic>.
disable-model-invocation: true
---

# /slopstop:design

Stage 1 of the slopstop process. Runs on the **huge tier**. Output: a run dir under
`scratch/runs/` holding `run.jsonl`, the PRD, and the charter, presented to the human at
gate **G-design**. Never cuts tickets (that is Stage 2, `/slopstop:tickets`) and never
implements anything.

`:design` is an **orchestrator**. It launches almost nothing — subagents cannot talk to
the user, and this stage is a conversation, so the grill runs inline (Step 2) — but it
creates the run dir, so it writes the first lines of `run.jsonl` and owns the run's
records. That makes the bracketing in Step 0c matter more here than anywhere else.

- → Read `skills/run/references/run-jsonl.md` — the schema, the sole-writer rule, the
  human-wait bracketing, the validation invariants. Do not restate or re-invent it.
  **Span or note is decided by the rule there, not per stage**: a worker launch or a loop
  round is a span, a single atomic act is a note, and every `stage` value is one of yours.
- → Read `skills/run/references/worker-launch.md` — the single `Agent()` launch form and
  stage → tier → model resolution, for anything this stage ever launches.

**You are the sole reader of the resolved configuration** — three sets, defaults →
`.project-conf.toml` → gitignored `.project-conf-local.toml`, merged per leaf key.
→ Read `skills/run/references/config-resolution.md`
 Resolve every value here, apply the
documented default for any absent key, pass resolved values as explicit arguments — nothing
you launch reads config.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `$PREFIX` (`prefix`),
`[stage_tiers]`, `[tiers]` (defaults: huge=`fable`, large=`opus`, medium=`sonnet`,
small=`haiku`), `[design] spec` (default: unset — see **Resolving the spec**),
`[design] autonomous` (default: `false` — see **Autonomous mode**), and
`$PUBLISH_ARTIFACTS` ← `[workflow].publish_artifacts` (default: `false` — see **Step 5**).
Stop with
a clear error if `prefix` is absent or doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Missing
config file: stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."`
Missing tables resolve to defaults — never error.

## Arguments

`$ARGUMENTS` is the topic — a feature name or a brain-dump. If empty, ask for one
sentence on what is being designed, then proceed.

`--spec <path>` — **repeatable.** Names an authoritative specification document for this
run. Every decision in the PRD is classified against the resolved spec (Step 3), and the
ticket-tree adversary's check F re-reads it. Pass it once per document.

`--autonomous` — forces autonomous mode on for this run regardless of `[design]
autonomous`. There is no flag to force it *off* against a config default of `true`; if a
project sets that default, running interactively for one topic means passing neither flag
nor waiting for one — config default already covers the common case, and the rare
exception can `sed` the config for one invocation same as any other override.

### Autonomous mode

`$AUTONOMOUS` = `--autonomous` given on this invocation, **or** `[design] autonomous =
true`, either sets it. Governs two things, both stated where they apply rather than here:
resolving the spec (rule 3, immediately below) and the grill (Step 2). **Never governs the
tier gate** (Step 1) — see that step for why.

### Resolving the spec

In order; the first that yields anything wins:

1. every `--spec <path>` given on this invocation (all of them),
2. `[design] spec` in `.project-conf.toml` (a string or an array of strings),
3. a conventional path — `SPEC.md`, then `docs/spec*.md`. Under `$AUTONOMOUS` **adopt it**
   if it resolves; otherwise **propose it and ask** — never adopt one silently. A wrong
   spec is worse than none, because every downstream classification then cites the wrong
   document, which is exactly why `$AUTONOMOUS` only skips the *ask*, never the *existence
   check* two lines below: a conventional path that resolves to nothing still means
   "nothing resolves", not a fabricated adoption.

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
# a span opening — event is "span", the phase is carried by `state`
printf '%s\n' "{\"event\":\"span\",\"stage\":\"grill\",\"state\":\"started\",\"at\":\"$(date -u +%FT%TZ)\"}" >> "$RUNLOG"
# a point-in-time fact — event is "note", and a note never carries `state`
printf '%s\n' "{\"event\":\"note\",\"stage\":\"tier_gate\",\"at\":\"$(date -u +%FT%TZ)\",\"result\":\"…\"}" >> "$RUNLOG"
```

**`event` is `span` or `note`; a span carries `state` (`started` / `finished` / `failed`).**
This example previously showed the flatter `event: started|finished|note` form, which
`run-jsonl.md` records as replaced on 2026-08-06 — a session copying it emitted lines that
disagreed with the schema every validator and `derive.py` reads. The reference owns the
shape; this is only a reminder of it.

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
| conventional-spec adoption prompt (resolution rule 3) | `spec_confirm` — skipped under `$AUTONOMOUS` when a path resolves |
| tier-gate cannot-determine confirmation (Step 1) | `tier_confirm` — **never skipped**, `$AUTONOMOUS` or not |
| **each grill question with no recommended answer** | `grill Q<n>` — under `$AUTONOMOUS`, a question WITH a recommendation is resolved without a bracket at all; see Step 2 |

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
  `"Tier gate: /slopstop:design requires the $TIER tier ('$MODEL', version $VERSION when pinned); this session is running '<session model>'. Relaunch on the right model (or edit [stage_tiers]/[tiers] — bad configs give bad results)."`
- **Cannot determine** (no model self-knowledge, or `$MODEL` matches nothing the session
  knows about itself) → never proceed silently. Bracket the ask (`tier_confirm`):
  `"I can't verify this session's model against the $TIER tier ('$MODEL', version $VERSION when pinned). Confirm this session is running the $TIER tier? (yes / abort)"`
  Record the human confirmation as a `tier_gate` note.

Do not soften this to a warning. A wrong-tier PRD looks right and poisons every gate below it.

**`$AUTONOMOUS` never reaches this step.** Whether the running session's model matches the
configured tier is a fact this session can or cannot verify about itself — not a design
decision with a recommendation to fall back on. "Cannot determine" asks every time,
autonomous mode or not; there is nothing to be autonomous about here, only something to
verify or fail to verify.

## Step 2 — Grill to shared understanding

Open the `grill` span, then invoke the vendored grill inline against the topic —
`Skill({skill: "slopstop:grill", args: ($AUTONOMOUS ? "--autonomous " : "") + $ARGUMENTS})`.
(Desktop-installed sessions name it `slopstop-grill`.) `grill/SKILL.md` owns the actual
autonomous behavior — the `--autonomous ` prefix is the entire handoff, since grill has no
access to `.project-conf.toml` and resolves nothing itself.

**Bracket every question the grill actually asks.** As part of asking, append the
`waiting_for_user` `started` with `result: "grill Q<n>"`; as part of reading the reply,
append the `finished`. Twenty questions leave twenty pairs — the only thing separating
thinking time from a weekend away.

**Under `$AUTONOMOUS`, a question the grill resolves from its own recommendation is not
one it "asks".** No span, because no wait happened — bracketing one would misreport an
autonomous pick as human thinking time, the same fabricated-timing failure `run-jsonl.md`
polices for durations (never print a negative) applied here to spans instead. Only a
question the grill states has no recommended answer gets bracketed and actually waited on.

The grill ends when no unresolved branches remain; close the `grill` span. Its summary —
every decision tagged `AUTO` or `HUMAN` (`grill/SKILL.md`'s "Recording a decision") — is
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

**A standard-mode run can carry `AUTO` decisions.** The grill resolves a branch by exploring
the codebase rather than asking whenever it can, and those are tagged `AUTO` in either mode
because nobody was asked (`grill/SKILL.md`, "Recording a decision"). Do not assume a
non-autonomous run is all `HUMAN`; count the tags.

**Carry the grill's `AUTO`/`HUMAN` tag through, alongside the class above — they are
independent axes.** `SPEC`/`DERIVED`/`UNDERDETERMINED` says whether the *source* settles
the decision; `AUTO`/`HUMAN` says whether a *human* ever saw the pick. A decision can land
anywhere in the resulting grid. Report `UNDERDETERMINED` + `AUTO` — no spec grounding and
no human review — as a **named subset**, not folded into the general `UNDERDETERMINED`
count: nothing grounds that decision and nobody checked it, which is the weakest possible
basis anything in this PRD can rest on, and the uniform count would bury it among
decisions a human at least considered.

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
  first place to look — the list of choices that could have gone the other way. **Mark
  each entry `AUTO` or `HUMAN`**; the `UNDERDETERMINED` + `AUTO` entries are where a review
  belongs first, since neither the spec nor a person ever weighed in on them.
- **`charter.md`** — the broad-stroke rules the implementation must respect for THIS
  feature ("all Twilio calls through one gateway module", "no schema migrations in this
  run"). Rules only — no design detail; that's the PRD's job. The charter complements the
  project's standing rules; it never overrides them.

Neither file is ever committed. **Nothing posts them to the umbrella ticket** — the procedure that did, `skills/document/references/document-archive-artifacts.md`, was deleted with `:document` in `32ecb23` and has no successor. `:archive` posts a *single ticket's* tracking directory to *that* ticket; it never sees the run dir. So both files live only in `scratch/runs/<run-id>/` until it is cleaned at G-final — the known gap recorded by BILL-537.

**`[workflow].publish_artifacts` narrows that gap, and only when a project opts in.** With `$PUBLISH_ARTIFACTS` true, Step 5 publishes both files as private claude.ai pages before it stops. It is not a substitute for the ticket-posting that was lost — it preserves the documents, not their attachment to a ticket — and with the key `false`, which is the default, the gap above is exactly as it was.

## Step 5 — Gate G-design: report and stop

**Validate `run.jsonl` before reporting any number** — every `started` closed, every line
parsing, every line carrying `at`. On failure, name the unclosed spans and report **no
timing at all**; a broken record must not produce a plausible-looking summary.

### Publish the PRD and charter — only when `$PUBLISH_ARTIFACTS` is true

Skip this whole subsection when the key is absent or `false`, which is the default. Nothing is
published, no note is written, and the report block below gains no line.

When it is `true`: publish `prd.md` and `charter.md` as two separate private artifacts, **after
Step 4 has written both files and before the stop below.** Both, or neither — a run that failed
to write the charter publishes nothing, since half a design is worse than a path to a directory.

Write each URL to `run.jsonl` as an artifact note, using the shape
`skills/run/references/run-jsonl.md` defines — `artifact.kind` of `prd` and `charter`
respectively, and **no `ticket` field**: `:design`'s work is run-level, not per-ticket. Do not
invent a second note shape for this; there is one definition and it is that file's.

Then add **one line per artifact** to the report block, leaving its existing lines alone:

```
Artifacts: PRD     https://claude.ai/public/artifacts/…
           Charter https://claude.ai/public/artifacts/…
```

**If publication cannot happen while the key is `true`, say so** — `Artifacts: publication
unavailable — files remain at scratch/runs/$RUN_ID/`. Naming only the path is not enough: the
block already prints both paths two lines above, so a path-only line repeats what is on screen
and tells the reader nothing went wrong. Key-on-but-failed must never look like key-off.

Then append the closing note — `{"event":"note","stage":"run_closed",…}` — and present
(report unattributed time; never redistribute it):

```
G-design — design complete for run $RUN_ID

Spec:     <path> (sha256 <short>) | none — greenfield
PRD:      scratch/runs/$RUN_ID/prd.md      (<n> decisions — <n> SPEC, <n> DERIVED, <n> UNDERDETERMINED; <n> deferrals)
          (<n> AUTO, <n> HUMAN; <n> of the UNDERDETERMINED set are also AUTO) — omit this line only when the AUTO count is zero, which is the case where it says nothing
Charter:  scratch/runs/$RUN_ID/charter.md  (<n> rules)
Artifacts: <one line per published artifact — omitted entirely when publish_artifacts is off>
Timing:   <wall> wall · <human idle> waiting on you · <active> active · <unattributed> unattributed
Plugin:   /plugin install slopstop@slopstop   (load the slopstop plugin in the next session)

Go ahead with ticket breakdown?
Next: /slopstop:tickets $RUN_ID   (large tier, fresh session — the run-id
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
