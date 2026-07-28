---
description: Stage 1 of the slopstop process — grill the user to shared understanding, then write the PRD and feature charter into the run dir and stop at gate G-design. Huge-tier only. Invoke as /slopstop:design <topic>.
disable-model-invocation: true
---

# /slopstop:design

Stage 1 of the slopstop process (`design/slopstop-process.md` §5). Runs on the **huge
tier**. Output: a run dir under `scratch/runs/` holding the PRD and feature charter,
presented to the human at gate **G-design**. This skill never cuts tickets (Stage 2,
`/slopstop:tickets`) and never implements anything.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `$PREFIX` (`prefix` field),
`[tiers]` (defaults: huge=`fable`, large=`opus`, medium=`sonnet`, small=`haiku`),
`[fleet.router]` (default: `enabled = false`) and `[design] spec` (default: unset — see
**Resolving the spec** below). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Missing config file: stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."` Missing tables resolve to defaults —
never error.

## Arguments

`$ARGUMENTS` is the topic — a feature name or a brain-dump. If empty, ask for one
sentence on what is being designed, then proceed.

`--spec <path>` — **repeatable.** Names an authoritative specification document for
this run. Every decision in the PRD is classified against the resolved spec (Step 5),
and the ticket-tree adversary's check F re-reads it. Pass the flag once per document
when a run has several.

### Resolving the spec

In order; the first that yields anything wins:

1. every `--spec <path>` given on this invocation (repeatable — all of them),
2. `[design] spec` in `.project-conf.toml` (a string or an array of strings),
3. a conventional path — `SPEC.md`, then `docs/spec*.md`. **Propose it and ask**;
   never adopt one silently. A wrong spec is worse than none, because every
   downstream classification then cites the wrong document.

For each resolved path: confirm it exists (a declared spec that is missing is a hard
stop, not a warning) and compute its `sha256`. Record path and hash in the PRD header:

```markdown
> SPEC: docs/api-contract.md (sha256 3f9a…c21b)
```

If nothing resolves, record exactly `SPEC: none — greenfield` and continue. That is a
legitimate state — most feature work has no external spec — and it means Step 5's
decisions default to `UNDERDETERMINED` unless they derive from the grill itself.

## Step 1 — Tier gate

Resolve the required model in two hops: `[stage_tiers].design` names the tier for this
stage (default `huge` if `[stage_tiers]` or the key is absent), then read the
`[tiers].<that tier>` table — the `[tiers.<tier>]` sub-table — for its `provider`,
`model`, and optional `version`. Call the resolved tier `$TIER`, the model family
`$MODEL`, and the pinned version (if any) `$VERSION`. **`provider` is never gated on** —
it is carried for the router only; a session cannot verify its own endpoint, so gating
on it would make every gate "cannot determine".

**Reject the old string form.** If `[tiers]` still carries the pre-cutover string form —
`[tiers].<tier>` as a bare string (e.g. `huge = "fable"`) rather than a `[tiers.<tier>]`
table — **hard stop**: `"[tiers].$TIER is the old string form; slopstop requires the
table form: [tiers.$TIER] with provider/model and optional version. Migrate
.project-conf.toml."`

Compare the session model against the spec. The session knows its own model
(e.g. `claude-fable-5`):
- **`$MODEL` (family)** must match — the family name appears in the session model
  (`claude-fable-5` matches `model = "fable"`).
- **`$VERSION`**, when the spec pins one, must match as a **dotted prefix** of the
  session model's version: spec `4.8` matches `claude-opus-4-8`, spec `5` matches
  `claude-fable-5`. An **omitted** `version` passes any version of the family.

- **Match** (family matches, and version prefix-matches or is omitted) → proceed.
- **Mismatch** → **hard stop**:
  `"Tier gate: /slopstop:design requires the $TIER tier ('$MODEL', version $VERSION when pinned); this session is running '<session model>'. Relaunch on the right model (or edit [stage_tiers]/[tiers] — bad configs give bad results)."`
- **Cannot determine** (no model self-knowledge, or `$MODEL` matches nothing the session
  knows about itself) → never proceed silently: ask the
  user — `"I can't verify this session's model against the $TIER tier ('$MODEL', version $VERSION when pinned). Confirm this session is running the $TIER tier? (yes / abort)"` — and record the
  human confirmation in `run.md`.

Do not soften this to a warning. A wrong-tier PRD looks right and poisons every
downstream stage.

## Step 2 — Mint the run and seed scratch/ and .slopstop/

1. **Adopt or mint the run-id:** Check `ANTHROPIC_CUSTOM_HEADERS` for an existing
   run-id (the `X-Slopstop-Run` header). If present, adopt it: `$RUN_ID = <extracted
   value>`. Else mint a new one: `$RUN_ID` = `<topic-slug>-<UTC yyyymmdd-HHMM>`
   (e.g. `twilio-20260709-1802`) — unique per run without needing a counter. The
   run-id tags every artifact this run produces and (router on) every API request.
   When minting (fallback case), record in `run.md`: "Stage 1 unmetered".
2. Seed (at the main worktree root, same resolution as `:gh-init` Step 8b):

```bash
ROOT="$(dirname "$(git rev-parse --git-common-dir)")"
mkdir -p "$ROOT/scratch/runs/$RUN_ID" "$ROOT/.slopstop/ticket-active" "$ROOT/.slopstop/ticket-archive"
git -C "$ROOT" check-ignore -q scratch/   || echo 'scratch/'   >> "$ROOT/.gitignore"
git -C "$ROOT" check-ignore -q .slopstop/ || echo '.slopstop/' >> "$ROOT/.gitignore"
```

`:design` is a seeding path, so it ignores **both** directories, exactly as `:gh-init`
Step 8b does. Creating `.slopstop/` is also what activates tier-2 tracking-dir resolution
for every other skill — no config key needed (→ Read
`~/.claude/commands/slopstop-start-refs/tracking-dir-resolution.md`) — so the gitignore
entry has to land in the same run: a project bootstrapped through `:design` with a live
`.slopstop/` and no gitignore entry would have every tracking dir swept into the first PR
by `:pr`'s `git add -A`. On a project that had been resolving to `~/.claude/`, this flips
it to tier 2 — the next `:start` reports that as a layout mismatch.

3. Write `scratch/runs/$RUN_ID/run.md` — the run state file:

```markdown
# Run $RUN_ID

Stage: design (G-design pending)
Model: <session model>   Tier: huge
Started: <UTC timestamp>
Topic: $ARGUMENTS
Router: pending (set by Step 3: healthy | disabled | unreachable since <time>)
```

## Step 3 — Router check ([fleet.router])

- `enabled = false` (default) → `$ROUTER = "disabled"`. Skip the check.
- `enabled = true` → `curl -fsS -m 3 "http://<host>:<port>/spend?prefix=$PREFIX&run=$RUN_ID"` (defaults
  `127.0.0.1:8484`). `GET /spend?prefix=$PREFIX&run=<id>` is the only endpoint §10 defines — a response
  means the proxy is live; there is no separate health path.
  - Healthy → `$ROUTER = "healthy"`. Recorded for the later stages: `:run` points
    fleet agents at the router (`ANTHROPIC_BASE_URL`) with `$RUN_ID` carried per
    request (header or `/r/$RUN_ID` prefix — the Phase-1 router is **passive**; there
    is no registration call). **Stage 1's own traffic is not routed** — a session
    cannot re-point itself mid-flight — so the G-design report line is *status only*, never
    a dollar figure.
  - Unreachable → `$ROUTER = "unreachable since <time>"`. **Proceed** — a dead router
    never blocks a run.

Record `$ROUTER` in `run.md` (replacing the `pending` placeholder). The G-design report's
router line is one of: `"router healthy (status only — Stage 1 traffic unrouted)"` /
`"cost tracking disabled"` / `"cost tracking unavailable (<since>)"`.

## Step 4 — Grill to shared understanding

Invoke the vendored grill against the topic:

```
Skill({skill: "slopstop:grill", args: $ARGUMENTS})
```

(Plugin-namespaced skills use the qualified form; in a Desktop-installed session the
name is `slopstop-grill`. One question at a time, recommended answers, explore the
codebase instead of asking where possible.) The grill ends when no unresolved branches remain;
its consolidated summary is the raw material for Step 5.

## Step 5 — Write the PRD and the feature charter

Both files go in `scratch/runs/$RUN_ID/`, both opening with the provenance header:

```markdown
> Provenance: <model> · <UTC date> · run $RUN_ID
```

- **`prd.md`** — the decisions from the grill, organized: thesis, every resolved
  decision with its rationale, explicit deferrals with owners, and the scope boundary.
  Write it so Stage 2 can cut tickets from it without access to this conversation —
  the PRD is the only thing that crosses the stage boundary. Open it with the `SPEC:`
  header line(s) resolved in Arguments.

- **`charter.md`** — the broad-stroke rules the implementation must respect for THIS
  feature ("all Twilio calls through one gateway module", "no schema migrations in
  this run"). Rules only — no design detail; that's the PRD's job. The charter
  complements the project's standing rules; it never overrides them.

### Every decision carries a provenance classification

A decision is only as good as the thing it is derived from, and the PRD is ground
truth for every gate below it — Stage 2's adversary checks the *tree against the PRD*,
Phase 0 tests are transcribed from tickets, code review checks code against tickets.
Nothing downstream re-reads the source. So the PRD has to say, per decision, what the
decision rests on:

| Class | Means | Must record |
|---|---|---|
| **`SPEC`** | the source settles it | the exact quoted source text, and which spec it came from |
| **`DERIVED`** | it follows from quoted source text by reasoning | the quote **and** the reasoning step |
| **`UNDERDETERMINED`** | the source does not settle it | the alternative reading(s), and why this one was chosen |

**Classify honestly — `UNDERDETERMINED` is not a failure.** A specification that
does not answer every question is normal; a PRD that *pretends* it did is the
failure mode. If the quoted text does not distinguish your reading from a
plausible alternative, the decision is `UNDERDETERMINED` however well-argued it is.

**A decision may not rest solely on another decision from this same PRD.** Two
decisions that support each other are internally consistent and jointly unfounded —
cite the source, or classify as `UNDERDETERMINED`.

The PRD carries a mandatory `## Underdetermined decisions` section listing every
decision in that class with its alternatives. When behaviour later turns out wrong,
that section is the first place to look: it is the list of choices that could have
gone the other way.

Neither file is ever committed — they are posted to the umbrella ticket at run
completion by the archiving procedure in
`skills/document/references/document-archive-artifacts.md`.

## Step 6 — Gate G-design: report and stop

Update `run.md` (`Stage: design complete — G-design presented`). Present:

```
G-design — design complete for run $RUN_ID

Spec:     <path> (sha256 <short>) | none — greenfield
PRD:      scratch/runs/$RUN_ID/prd.md      (<n> decisions — <n> SPEC, <n> DERIVED, <n> UNDERDETERMINED; <n> deferrals)
Charter:  scratch/runs/$RUN_ID/charter.md  (<n> rules)
Router:   <"router healthy (status only — Stage 1 traffic unrouted)" | "cost tracking disabled" | "cost tracking unavailable (<since>)">
Launch:   ANTHROPIC_BASE_URL=<router-url> ANTHROPIC_CUSTOM_HEADERS=$'X-Slopstop-Run: '"$RUN_ID"
          (for Stage 2+: metered by default)
Plugin:   /plugin install slopstop@slopstop   (load the slopstop plugin in the next session)

Go ahead with ticket breakdown?
Next: /slopstop:tickets $RUN_ID   (large tier, fresh session — the run-id
selects the run dir; without it Stage 2 would have to guess among runs)
```

**Stop.** Do not cut tickets, do not launch anything. The human drives the stage
transition; Stage 2 reads the artifacts, not this transcript.

## Rules

- Huge tier only; the tier gate is a hard stop, and its result is recorded in `run.md`.
- Everything this stage produces carries the provenance header.
- The stage boundary is artifact-only: Stage 2 must be able to run from `prd.md` +
  `charter.md` alone.
- A dead router degrades cost reporting, never the run.
