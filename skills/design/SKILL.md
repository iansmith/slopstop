---
description: Stage 1 of the slopstop process — grill the user to shared understanding, then write the PRD and feature charter into the run dir and stop at gate G1. Huge-tier only. Invoke as /slopstop:design <topic>.
disable-model-invocation: true
---

# /slopstop:design

Stage 1 of the slopstop process (`design/slopstop-process.md` §5). Runs on the **huge
tier**. Output: a run dir under `scratch/runs/` holding the PRD and feature charter,
presented to the human at gate **G1**. This skill never cuts tickets (Stage 2,
`/slopstop:tickets`) and never implements anything.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `$PREFIX` (`prefix` field),
`[tiers]` (defaults: huge=`fable`, large=`opus`, medium=`sonnet`, small=`haiku`) and
`[fleet.router]` (default: `enabled = false`). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Missing config file: stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."` Missing tables resolve to defaults —
never error.

## Arguments

`$ARGUMENTS` is the topic — a feature name or a brain-dump. If empty, ask for one
sentence on what is being designed, then proceed.

## Step 1 — Tier gate

Resolve the required model in two hops: `[stage_tiers].design` names the tier for this
stage (default `huge` if `[stage_tiers]` or the key is absent), then `[tiers].<that
tier>` names the model. Call the resolved tier `$TIER` and model `$MODEL`. Compare the
model this session is running on against `$MODEL`; the session knows its own model, so
match on the family name (e.g. a session on `claude-fable-5` matches `huge = "fable"`).

- **Match** → proceed.
- **Mismatch** → **hard stop**:
  `"Tier gate: /slopstop:design requires the $TIER tier ('$MODEL'); this session is running '<session model>'. Relaunch on the right model (or edit [stage_tiers]/[tiers] — bad configs give bad results)."`
- **Cannot determine** (no model self-knowledge, or `$MODEL` matches nothing the session
  knows about itself) → never proceed silently: ask the
  user — `"I can't verify this session's model against the $TIER tier ('$MODEL'). Confirm this session is running the $TIER tier? (yes / abort)"` — and record the
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
Step 8b does. A project bootstrapped through `:design` with an active
`tracking_dir = ".slopstop/ticket-active"` but no `.slopstop/` gitignore entry would have
every tracking dir swept into the first PR by `:pr`'s `git add -A` — the footgun that
keeps both keys commented out in `.project-conf.toml.example`.

3. Write `scratch/runs/$RUN_ID/run.md` — the run state file:

```markdown
# Run $RUN_ID

Stage: design (G1 pending)
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
    cannot re-point itself mid-flight — so the G1 report line is *status only*, never
    a dollar figure.
  - Unreachable → `$ROUTER = "unreachable since <time>"`. **Proceed** — a dead router
    never blocks a run.

Record `$ROUTER` in `run.md` (replacing the `pending` placeholder). The G1 report's
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
Router:   <"router healthy (status only — Stage 1 traffic unrouted)" | "cost tracking disabled" | "cost tracking unavailable (<since>)">
Launch:   ANTHROPIC_BASE_URL=<router-url> ANTHROPIC_CUSTOM_HEADERS=$'X-Slopstop-Run: '"$RUN_ID"$'\nX-Slopstop-Ticket: <ticket>'
          (for Stage 2+: metered by default)

Go ahead with ticket breakdown?
Next: /slopstop:tickets $RUN_ID   (medium tier, fresh session — the run-id
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
