---
description: Stage 1 of the slopstop process — grill the user to shared understanding, then write the PRD and feature charter into the run dir and stop at gate G1. Big-tier only. Invoke as /slopstop:design <topic>.
disable-model-invocation: true
---

# /slopstop:design

Stage 1 of the slopstop process (`design/slopstop-process.md` §5). Runs on the **big
tier**. Output: a run dir under `scratch/runs/` holding the PRD and feature charter,
presented to the human at gate **G1**. This skill never cuts tickets (Stage 2,
`/slopstop:tickets`) and never implements anything.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Missing from both: stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."`

Read `[tiers]` (defaults: big=`fable`, medium=`opus`, small=`haiku`) and
`[fleet.router]` (default: `enabled = false`). Missing tables resolve to defaults —
never error.

## Arguments

`$ARGUMENTS` is the topic — a feature name or a brain-dump. If empty, ask for one
sentence on what is being designed, then proceed.

## Step 1 — Tier gate

Compare the model this session is running on against `[tiers].big`. The session knows
its own model; match on the family name (e.g. a session on `claude-fable-5` matches
`big = "fable"`).

- **Match** → proceed.
- **Mismatch** → **hard stop**:
  `"Tier gate: /slopstop:design requires the big tier ('<[tiers].big>'); this session is running '<session model>'. Relaunch on the right model (or edit [tiers] — bad configs give bad results)."`

Do not soften this to a warning. A wrong-tier PRD looks right and poisons every
downstream stage.

## Step 2 — Mint the run and seed scratch/

1. Mint the run-id: `$RUN_ID` = `<topic-slug>-<UTC yyyymmdd-HHMM>` (e.g.
   `twilio-20260709-1802`) — unique per run without needing a counter. The run-id
   tags every artifact this run produces and (router on) every API request.
2. Seed (at the main worktree root, same resolution as `:gh-init` Step 8b):

```bash
ROOT="$(dirname "$(git rev-parse --git-common-dir)")"
mkdir -p "$ROOT/scratch/runs/$RUN_ID"
git -C "$ROOT" check-ignore -q scratch/ || echo 'scratch/' >> "$ROOT/.gitignore"
```

3. Write `scratch/runs/$RUN_ID/run.md` — the run state file:

```markdown
# Run $RUN_ID

Stage: design (G1 pending)
Model: <session model>   Tier: big
Started: <UTC timestamp>
Topic: $ARGUMENTS
Router: <enabled+healthy | disabled | unreachable>
```

## Step 3 — Router check ([fleet.router])

- `enabled = false` (default) → `$ROUTER = "disabled"`. Skip the check.
- `enabled = true` → `curl -fsS -m 3 "http://<host>:<port>/spend?run=$RUN_ID"` (defaults
  `127.0.0.1:8484`). `GET /spend?run=<id>` is the only endpoint §10 defines — a response
  means the proxy is live; there is no separate health path.
  - Healthy → `$ROUTER = "healthy"`. Subsequent router-bound requests carry `$RUN_ID`
    (header or `/r/$RUN_ID` path prefix — the Phase-1 router is **passive**; there is
    no registration call).
  - Unreachable → `$ROUTER = "unreachable since <time>"`. **Proceed** — a dead router
    never blocks a run.

Record `$ROUTER` in `run.md`. The G1 report's spend line is `"cost tracking
disabled"` / `"cost tracking unavailable (<since>)"` unless healthy.

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
  the PRD is the only thing that crosses the stage boundary.
- **`charter.md`** — the broad-stroke rules the implementation must respect for THIS
  feature ("all Twilio calls through one gateway module", "no schema migrations in
  this run"). Rules only — no design detail; that's the PRD's job. The charter
  complements the project's standing rules; it never overrides them.

Neither file is ever committed — they archive to the umbrella ticket at run
completion (`design/slopstop-process.md` §4).

## Step 6 — Gate G1: report and stop

Update `run.md` (`Stage: design complete — G1 presented`). Present:

```
G1 — design complete for run $RUN_ID

PRD:      scratch/runs/$RUN_ID/prd.md      (<n> decisions, <n> deferrals)
Charter:  scratch/runs/$RUN_ID/charter.md  (<n> rules)
Spend:    <from router | "cost tracking disabled" | "cost tracking unavailable (<since>)">

Go ahead with ticket breakdown? (/slopstop:tickets — medium tier, fresh session)
```

**Stop.** Do not cut tickets, do not launch anything. The human drives the stage
transition; Stage 2 reads the artifacts, not this transcript.

## Rules

- Big tier only; the tier gate is a hard stop, and its result is recorded in `run.md`.
- Everything this stage produces carries the provenance header.
- The stage boundary is artifact-only: Stage 2 must be able to run from `prd.md` +
  `charter.md` alone.
- A dead router degrades cost reporting, never the run.
