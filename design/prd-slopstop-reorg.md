# PRD — slopstop reorganization

> Provenance: Claude · 2026-08-06 · `/slopstop:grill` session · branch `minor_fix`
> Status: design settled, no open branches. Not produced by `:design` — this reorg
> deliberately does not run slopstop's process on itself.
>
> **Lives in tracked `design/`, not gitignored `docs/`, by Ian's decision 2026-08-06.**
> These three files — this PRD, `charter-slopstop-reorg.md`, and `reorg-carveouts.md` —
> are the entire design record for a change that deletes ~5,600 lines and rewrites every
> skill. `reorg-carveouts.md` is a hard blocker on phase 3. A `git clean -xdf` against
> `docs/` would have erased all of it with no trace in the branch, which is the same
> hazard that had `baseline/` moved out of `scratch/` once before.
> Delete them deliberately when the reorg lands — do not let them rot in `design/`.

---

## 1. Premise

slopstop's **goal does not change**: stop AI slop before it goes in, via TDD and scope
up front, then simplify and review. The *implementation* of that goal changes
substantially.

The problem being solved is recursive self-testing. slopstop is a tool made of markdown
skills, and it has been built test-first — which produced a suite that asserts on the
*content of its own prose*. That is where the complexity became silly: ~980 lines of
Python whose job is to check that markdown says what it said yesterday. It pins wording,
proves no behavior, and cannot catch the failures that actually occur.

slopstop is designed for use by **other** repos. There are nine of them. Those are the
test harness.

---

## 2. Goals

- **G1** — Delete the self-testing machinery and the derived-metrics apparatus built to
  measure a process that never emitted anything.
- **G2** — Replace derived timing with recorded timing, computable in one pass over one
  file, and able to distinguish machine-active time from a human who walked away.
- **G3** — Collapse four bespoke agent-launch dialects into one documented mechanism used
  everywhere.
- **G4** — Preserve the process: TDD, scope up front, adversary passes, clean-context
  review. These survive as first-class skills.

### Non-goals

- Changing what slopstop asks of consuming repos. TDD stays mandatory **there**.
- Preserving per-ticket token or cost measurement. See D2 and §10.
- Refactoring `router/` as a program.

---

## 3. Decisions

### D1 — Delete the markdown-assertion tests and the collector tests; keep `router/`'s Go tests

The suite is three separable bodies, not one:

| body | size | disposition |
|---|---|---|
| markdown / config / installer assertions | ~980 lines | **delete** |
| `tools/metrics/` collector tests | ~2,150 lines | **delete** (subject is going too) |
| `router/` Go tests | 3,551 lines | **keep** |

`router/` is a real 1,801-line network proxy with conventional Go tests. It is not part
of the recursion problem, the tests cost nothing to carry, and deleting them would be
deleting the only genuine test coverage in the repo.

There is currently **no CI running any test**, which is worth stating plainly: the suite
has not been a gate for some time.

### D2 — Delete `tools/metrics/` entirely

All nine modules (~1,100 lines; three were already permanent stubs). Timing moves to
direct recording (D5). Token counts and USD spend are **given up** — see §10.

### D3 — Unwire the metering router from every skill

Remove `[fleet.router]` handling from `:design`, `:run`, `:start`, `:tickets`,
`:single-ticket`, and delete `skills/focus/` entirely (its only purpose is router
re-tagging). `router/` survives as a standalone Go program; no skill references it.

This is what unblocks D4: the sole documented reason `:run` refused the Agent tool was
that it could not inject per-agent env vars for router attribution.

### D4 — One launch mechanism: `Skill()` with `context: fork`

**This decision was made twice.** The first version — "use the `Agent()` tool everywhere
and drop `context: fork` as redundant" — was **wrong**, and was corrected by checking the
official docs at Ian's request. Recording both, because the error is the third of its kind
in this repo (see §10, R3).

What the docs establish:

- Skill frontmatter documents `model`, `effort`, `context: fork`, `background`, and
  `agent` (which subagent type runs the fork).
- `context: fork` runs a skill as an isolated subagent — separate context window, no
  access to the invoking conversation, skill body becomes the prompt. `background: false`
  waits for a result.
- Subagent frontmatter documents `effort` too — so the repo's existing "effort comes from
  the subagent definition's frontmatter" caveat was **correct all along** and must not be
  deleted.

**A third correction followed, on different grounds.** The `Skill()` tool accepts only
`skill` and `args` — **there is no model parameter**. So a forked skill's model comes from
its static frontmatter and the caller cannot override it. But `[tiers]` is *per-project
runtime config* and genuinely varies (`~/lyos/mobile-v2` and `~/ticket-plugin` carry
different tables today), and `CONFIG.md:301` states the design intent explicitly:
*"Re-tiering a stage is a one-line edit here, with no skill rewrite."*

Hardcoding `model:` into worker frontmatter would make worker tiers fleet-wide constants,
killing per-project tier experiments for every worker stage. **Per-project configuration
can only reach what is passed at call time, and `model:` is passable on `Agent()` but not
on `Skill()`.** Note this is a different argument from the discarded first version, which
wrongly claimed `context: fork` was *redundant*.

Therefore:

> **Orchestrators resolve stage → tier → model from `.project-conf.toml` and launch each
> worker with `Agent(subagent_type: <worker type>, model: <resolved>, prompt: <invoke the
> worker skill>)`.** Worker skills declare **no** `model`, `effort`, or `context` — only
> `description` and `disable-model-invocation`.

- **Model** is caller-controlled and per-project. Documented `Agent()` parameter.
- **Effort** comes from a small set of subagent definitions in `.claude/agents/`
  (`slopstop-worker-high`, `slopstop-worker-medium`), where `effort` is documented.
  Per-project *effort* tuning for workers is given up; per-project *model* tuning — the
  thing the live tier experiment varies — is preserved, as is the checker-above-doer ladder.
- Worker skills declare no `model`, so the undocumented skill-vs-subagent model precedence
  gap is never exercised.

**Constraint from a documented gap:** whether a `context: fork` skill can be invoked from
*inside* a subagent is **not documented**. Only the top-level case is specified. So:
**orchestrators run at top level; workers never launch workers.** Nothing nests.

`skills/review/` is still the structural template for a worker's *body*, but its
`context: fork` / `model` / `effort` frontmatter must be **removed** when it becomes a
worker — it is currently invoked by `pr` at top level, which is the arrangement being
replaced.

### D5 — Timing is recorded, not derived: `run.jsonl`

An **append-only JSONL**, written by the **orchestrator only**. Append-only means no
read-modify-write races across concurrently-running tickets, resume is a replay, and
analysis is one pass over one file.

Two locations, one schema:

| written by | location |
|---|---|
| `:design`, `:tickets` | `scratch/runs/$RUN_ID/run.jsonl` |
| `:run` | each ticket's own tracking dir |

Per-ticket placement for `:run` (Ian's amendment) removes the umbrella-less edge case
entirely and makes every archived ticket self-describing.

`scratch/runs/$RUN_ID/run.md` is **retired** — `:design` currently writes it as "the run
state file," and two state files per run is a §5 violation waiting to drift.

### D6 — The orchestrator is a pattern, used three times

`:design`, `:tickets`, and `:run` all follow one shape: launch timed work as forked
skills, append every transition to `run.jsonl`.

| | orchestrates | forks launched |
|---|---|---|
| `:design` | grill → spec-classify → PRD → charter | few; mostly human conversation |
| `:tickets` | read PRD → cut tree to disk → adversary loop → write to ticket system | `adversary` (≤3 rounds) |
| `:run` | N tickets × full lifecycle | all seven workers |

`:tickets` becoming an orchestrator (Ian's amendment) is what makes `adversary` genuinely
shared infrastructure, which in turn justifies collapsing three implementations into one.

### D7 — `:run` is the single lifecycle entry point

`:start`, `:plan`, `:pr`, `:merge`, `:archive`, `:document`, `:update` stop being
commands. Their *work* becomes forked worker skills or inline orchestrator steps; their
**handoff machinery is deleted outright** — "Autonomous mode", "Stage end — resume state
and `Next:`", per-stage confirm steps, resume modes.

That machinery is a large fraction of the current skill bodies and exists *only* because
stages were separate interactive sessions that had to hand off. `:merge` alone is ten
steps of which four are handoff bookkeeping.

The name `:run` is reused deliberately: it already means "drive N tickets to completion,"
so the documented `:design → :tickets → :run` chain stays valid across `COMMANDS.md`,
`WORKFLOW.md`, and `:design`'s closing `Next:` line.

### D8 — Nine worker skills

**Revised 2026-08-06 (Ian): seven → nine.** The two mechanical gates in `:pr` had no home
in the original seven and PRD §5 did not list them for deletion either, so they would have
vanished silently. They become workers, written and invoked exactly like the rest.

| skill | work | replaces |
|---|---|---|
| `investigate` | explore the codebase for a ticket | `plan` Step 1 |
| `red-tests` | write phase-0 failing tests from the DoD | `plan` Step 0 |
| `mutation-check` | prove each red test fails for the **right reason** | `plan-phase0-mechanics` |
| `adversary` | gap-find a target against stated goals | the **three** adversary refs |
| `implement` | make the red tests green | `plan` Steps 3a/7 |
| `review` | clean-context review of the diff | exists already |
| `slop-check` | slop detection on the diff — **judgment** | `pr-slop-detection` (541 lines) |
| `vacuity-check` | **prove** a test would have failed before the branch | `:pr` Step 2f (BILL-343) |
| `complexity-check` | cyclomatic-complexity gate over the diff | `pr-cc-gate` (357 lines) |

`slop-check` and `vacuity-check` are **complementary, not redundant**. `slop-check` asks
the vacuity question as a reasoned read ("what would have to break for this to go red?");
`vacuity-check` runs the test against the base commit and *proves* it. The judgment pass
catches what no mechanism can; the mechanical pass catches what a confident reader talks
themselves out of.

`plan-adversary-gaps.md`, `tickets-adversary.md`, and `single-ticket-adversary.md` (291
lines across three files, doing the same job against different targets) collapse into one
`adversary` skill. Universal §5.

Everything mechanical — branch creation, ticket label transitions, PR create/merge, doc
push, archive move, `run.jsonl` writes — runs **inline in the orchestrator, no fork**.

### D9 — Tracking-dir artifacts, orchestrator as sole writer

Surviving: `run.jsonl`, `findings.md`, `task_plan.md`. **Deleted:** `gates.json` and
`progress.md`.

`gates.json` was gate-pass evidence written by the session under test, which was never
evidence — the objection is already recorded in this repo's own memory. `progress.md` was
`:update`'s checkpoint, existing because stages were separate sessions that could lose
context; `run.jsonl` is that, mechanically.

**Consequence worth having:** if no worker writes, **no worker resolves the tracking
dir** — retiring the tier-2/tier-3 ladder hazard in `tracking-dir-resolution.md` where a
linked worktree falls through to an unwritable `~/.claude/` and a headless agent silently
invents its own directory.

### D10 — Skill inventory: 18 → 17

- **Orchestrators (3):** `design`, `tickets`, `run`
- **Workers (9):** `investigate`, `red-tests`, `mutation-check`, `adversary`,
  `implement`, `review`, `slop-check`, `vacuity-check`, `complexity-check`
- **Standalone (5):** `grill`, `gh-init`, `create-gh`, `doc-sync`, `single-ticket`

The headline count barely moves, and that is the point: the win is not fewer files, it is
that every stage's hand-off machinery — "Autonomous mode", "Stage end / `Next:`", resume
state, per-stage confirmation — disappears, and nine small single-purpose workers replace
four bespoke agent-launch dialects.
- **Deleted or absorbed (9):** `start`, `plan`, `pr`, `merge`, `archive`, `document`,
  `update`, `update-ticket`, `focus`

`create-gh` (issue creation) and `doc-sync` (mirrors `design/` to the wiki) are not
lifecycle work and stay standalone. `update` writes `progress.md`, which D9 deletes, so
it goes; `update-ticket` is `update` + `document` chained, so it goes with them.

### D11 — Installers glob `skills/*/`

Both Desktop installers carry a hardcoded `SKILLS=( … )` array. This reorg adds six
skills and deletes nine — the exact condition BILL-436 was filed for — and the test that
catches the omission is being deleted.

Fix the failure mode, don't test for it: derive the list by globbing `skills/*/` so the
arrays cannot desync. Same move the repo already made on the universal-block markers.

### D12 — Validation is dogfooding, plus `/code-review`

No replacement test suite. The nine consuming repos are the harness; running the
orchestrator on real tickets there is the only thing that ever proved the process worked.

Claude Code's own `/code-review` runs on the branch before merge — **invoked by Ian at
top level**, not by any orchestrator. It is user-triggered and billed and cannot be
launched by the model.

### D13 — Rules: universal edits are in scope, but confirmed and hand-propagated

**Revised 2026-08-06 (Ian).** The original decision was "never touch the mirror, override
locally." That is relaxed: changes to `CLAUDE-universal.md` are **appropriate and expected**
during this reorg, since the rules describe a process this branch is rewriting.

Two constraints:

1. **Every universal-rules change is proposed as an exact diff and confirmed by Ian before
   it is written.** The file is mirrored byte-identically into every consuming repo, so a
   change here changes nine repos' rules.
2. **Ian owns propagation.** Do not run `migrate-universal-block.py --apply` and do not
   touch another repo's copy. Change this repo's reference copy only.

`CLAUDE-universal.md` §1–§2 (run the project's tests; tests-first for new behavior) are the
first candidates, since slopstop is about to have no test suite. Whether that becomes a
universal rewording ("where a test suite exists") or a slopstop-local
`## Tests (overrides universal §1–§2)` section is now an open question for Ian, not a
settled decision.

The process still mandates TDD in consuming repos — `red-tests` and `mutation-check`
survive as workers. Only this repo opts out.

### D14 — Parallelism: predict to schedule, merge-time handling as backstop

Two facts shape this:

- **Worktree isolation means execution can never conflict.** Two tickets editing
  `CONFIG.md` in separate worktrees both succeed. Conflict is a *merge-ordering* problem.
- **It cannot be resolved by rebasing.** Universal §3 forbids the force-push a rebase of a
  pushed branch requires. This repo's own `CLAUDE.md` already prescribes `git merge master`
  for exactly this case.

So conflict detection buys scheduling efficiency, not correctness:

1. Fan out `investigate` for all N tickets first — read-only, always safe, always parallel
   — collecting each ticket's predicted file map.
2. Schedule non-overlapping tickets concurrently; overlapping ones serially.
3. Merge PRs serially regardless. On conflict, `git merge master` into the loser and
   re-run its tests.

Prediction is never perfect, so merge-time handling exists whether or not prediction runs.

---

## 4. `run.jsonl` and the timing model

### Schema

One JSON object per line. Every line carries `at` (ISO-8601 Z). Spans are **explicitly
bracketed** — a `started` line and a `finished` line.

```json
{"ticket":"BILL-501","stage":"red-tests","event":"started","at":"2026-08-06T14:02:11Z"}
{"ticket":"BILL-501","stage":"red-tests","event":"finished","at":"2026-08-06T14:07:48Z","result":"4 tests, all red"}
{"event":"waiting_for_user","phase":"started","at":"2026-08-06T14:07:49Z","what":"grill Q7"}
{"event":"waiting_for_user","phase":"finished","at":"2026-08-08T09:15:02Z","what":"grill Q7"}
```

### Computing compute time

Wall clock is meaningless when a human walks away for a weekend. The **old system tried
this and failed**: `tools/metrics/active.py` was a permanent stub for exactly the
human-idle / tool-execution / model-inference split (BILL-452, never implemented), and
`spans.py` records the damage — a `slopstop-plan` span of **45,843 seconds** because
someone went to bed, and an interactive ticket measuring 550.9 minutes wall against 45.5
minutes agent-active. 92% idle.

It failed because it reconstructed idle from transcripts after the fact. The new design
does not have to: **the orchestrator knows when it is blocked on a human, because it is
the thing doing the blocking.** It brackets that wait like any other span.

Everything then falls out of one pass:

| quantity | computation |
|---|---|
| wall clock | `last.at − first.at` |
| human idle | `Σ` `waiting_for_user` spans |
| **active time** | `wall − human_idle` |
| agent-seconds | `Σ` worker spans — *exceeds* active under parallelism, like CPU-seconds vs elapsed |
| unattributed | active minus the union of attributed spans |

`:design` is the motivating case and the easy one: every grill exchange is naturally a
bracket. A two-day gap falls entirely inside one `waiting_for_user` span and is
subtracted. No heuristics, no thresholds, no transcript parsing.

### Stated limits

1. **"Active" is active *elapsed*, not inference time.** Tool execution, model inference,
   and orchestrator overhead all sit inside it. Splitting them requires transcript-level
   data — precisely what D2 deletes. If true inference-seconds are ever wanted, D2 must be
   revisited.
2. **Session death is not a `waiting_for_user` gap.** If the session dies mid-run and
   resumes days later, nothing brackets it. Mitigated for free: the orchestrator must read
   `run.jsonl` on resume anyway to reload state, so it writes a `session_resume` line that
   bounds the gap.
3. **Unattributed time is reported, never redistributed.** `spans.py` did this correctly
   (`attributed_seconds` / `unattributed_seconds`) and it is the only defensible treatment.

---

## 5. Deletion inventory

| target | size | reason |
|---|---|---|
| `tests/` — markdown/config assertions | ~980 lines | pins wording, proves no behavior |
| `tests/` — collector tests | ~2,150 lines | subject deleted |
| `tests/fixtures/` | 36 files | collector inputs |
| `tests/__pycache__/` | ~90 stale `.pyc` | residue of the 2026-08-01 prune, for tests already deleted |
| `tools/metrics/` | ~1,100 lines, 9 modules | derivation replaced by recording |
| `skills/focus/` | 36 lines | router re-tagging only |
| Router wiring in 5 skills | — | D3 |
| `gates.json`, `progress.md`, `run.md` | — | D5, D9 |
| `--inline` flag | 2 skills | existed only because launch mechanisms did not nest |
| `Monitor` loop, `HARD_STUCK_MIN`, `poll_interval_min` | — | orchestrator awaits results |
| `run-agent-brief.md` (headless CLI brief) | — | one mechanism now |
| `pr-cr-polling.md`, `pr-greptile-polling.md` | — | see §10, R1 |
| Per-stage handoff machinery | large | D7 |

**Kept:** `router/` and its Go tests; the process itself.

---

## 6. Landing plan

One PR off `minor_fix`, phased commits. Master is untouched until merge, so there is no
broken intermediate state.

| phase | work |
|---|---|
| **1** | Extract the seven worker skills from the existing stage skills. Everything waits on this. |
| **2** | Build the three orchestrators; define the `run.jsonl` schema and writers. |
| **3** | Delete the old skills, `tests/`, `tools/metrics/`, router wiring, `:focus`. |
| **4** | Installers glob; docs, `CONFIG.md`, `plugin.json`, `CLAUDE.md` override, `CHANGELOG`. |

Extraction must precede deletion — the workers are extracted *from* the skills being
deleted.

`/code-review` on the branch before merge, invoked by Ian.

---

## 7. Underdetermined decisions and accepted risks

Following `:design`'s convention of naming these explicitly rather than pretending the
design answered everything.

**R1 — CodeRabbit/Greptile polling deleted, resolved by rule not by Ian.**
`pr-cr-polling.md` and `pr-greptile-polling.md` implement a 20-minute poll, which
contradicts universal §9: "read it if it is already there, **never wait for it**." The
orchestrator reads bot comments once, inline, and merges on the Claude review.
`[pr_review] backend` stays as config. **Flagged for override if Ian disagrees.**

**R2 — DoD authorship consolidates into `:tickets`, resolved by implication.** A separate
`dod` worker was declined, and `:tickets` already produces the DoD as part of the
five-section standard. So `plan` Step 2's DoD drafting disappears rather than moving.

**R3 — The `run.jsonl` writer is prose, and prose writers have failed here before.** The
timing model depends on an orchestrator reliably stamping before and after every human
wait. This is the same class of failure that killed `metrics_emit_path`: *"skills are
prose; the stub exists only if the agent executing `:start` chooses to follow the
instruction. There is no writer."* The position is better this time — one writer, in one
skill, at a handful of well-defined blocking points, rather than a discretionary emit
scattered across twelve skills — but it is **not zero risk**. If `run.jsonl` starts
returning large unattributed spans, that is the symptom.

**R3a — and there is no answer yet for how an incomplete record announces itself.**
Inherited from the superseded lifecycle-metrics brief
(`docs/design-brief-lifecycle-metrics.md`, open question 2), where it was raised and never
resolved.

The cautionary case, reproduced here because the file was deleted 2026-08-06 and was
gitignored, so this is now the only copy. `~/gaston/.slopstop/metrics/pipeline.json`,
written 2026-07-16:

```json
{
  "ticket": "GAST-3",
  "phase0_tests_red": 2,
  "phase0_tests_pass_unexpected": 0
}
```

Three keys. No `started_at`, no `branch`, no `completed_at` — and written to
`.slopstop/metrics/pipeline.json`, not the `.slopstop/metrics/<TICKET>/pipeline.json`
every consumer resolved. **It passed every check that existed.** A partial write that
looked like a successful one.

The hazard transfers directly. An unbracketed span in `run.jsonl` — a `started` with no
`finished`, because the orchestrator died or simply didn't stamp — is indistinguishable
from a short span unless something looks for it. **Phase 2 must decide what makes that loud
rather than plausible.**

**R4 — Cost and token measurement are given up.** Not deferred: given up. They cannot be
recorded from inside a run, only derived from transcripts, and the derivation apparatus is
what got out of hand. Recovering them means reversing D2.

**R5 — Fork-inside-fork is undocumented, and the design avoids rather than resolves it.**
If a worker ever needs to launch a worker, this must be probed first, not assumed.

**R6 — Nothing mechanical guards the install shape after D11.** The glob makes drift
structurally impossible for the *skill list*, but nothing checks that frontmatter survives
the install (the BILL-456 failure). Accepted; the installers are simpler after this reorg.

---

## 8. Out of scope — follow-on work not yet scoped

- Doc surface: `COMMANDS.md`, `WORKFLOW.md`, `README.md`, `QUICKSTART.md`,
  `SETUP-GUIDE.md`, `CONFIG.md`, `walkthrough/`, `site/`, `plugin.json`.
- A major version bump — user-facing commands disappear, so this is breaking.
- Dead `.project-conf.toml` keys: `[fleet.router]`, `[fleet.monitoring]`,
  `[fleet.agents]`, and the metrics keys.
- Memory files citing a test baseline (219 passing in ~95s) that becomes meaningless.
- `bin/pre-commit-file-size.sh` — an uninstalled hook nothing references.
