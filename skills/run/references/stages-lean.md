# Lean mode — the default `:run`, and what `--full` restores

Read when `--full` is **absent**. This file is the one definition of every place the lean
flow differs from the fifteen-stage table in `SKILL.md`. Where a stage is not named here,
it runs exactly as the full flow's reference for it says — this file adds to those
references, it never restates one (universal §5). `--full` runs the fifteen-stage table
unchanged and reads none of this file except the first section.

## Why lean exists (measured, 2026-09-07)

119 tickets across five consumer repos: **4h51m average per ticket, 6% of it
implementation.** Adversary 22%, handoff verification 19%, the stage-9 gates 20% — and
85–95% of each gate's runtime was agent startup and context loading, not measurement.
Each stage transition cost 2–3 minutes of handoff; a ticket had 11+ launches. Lean cuts
the launches to three (`investigate`, `work`, `review`) and turns the mechanical gates into
scripts that finish in seconds. Target: ~45 minutes per ticket. The evidence, the per-stage
hit rates and the decisions are in the PRD (`docs/prd-v5-lean-run.html`, local).

## What `--full` restores — one table

| | lean (default) | `--full` |
|---|---|---|
| stages 4–9 | **one `work` worker** in one worktree | one worker per stage, per `stages-phase0.md` and `stages-implement.md` |
| `mutation-check` (5, 9) | not run | 3 probes per test + the pinning pass |
| `adversary` (7) | not run | one round |
| `slop-check` (9) | not run | judgment pass over the diff |
| `vacuity` / `complexity` / `duplication` / `tamper` | **scripts**, run by the `work` worker | LLM workers (`vacuity-check`, `complexity-check`, `duplication-check`) + inline 8a |
| `review` (10) | **`/code-review`** at effort `medium`, once, from a fresh worker | `slopstop:review` loop, cap 5 |
| `handoff` (10b) | not run | two fresh agents at the tier above |
| `archive` (15) | `task_plan.md` + `findings.md`, inline | `archive` worker, every tracking file |
| backfill tickets | **refused** — see below | run as today |

Everything else — intake, investigate, branch, size, pr, bot-read, merge, close, the
worktree rules, scheduling, `run.jsonl` discipline — is identical in both modes.

**What lean gives up, stated so nobody rediscovers it:** the "red for the right reason"
probe (mutation-check), the pinning pass, shadow-test detection (adversary-only), and
item-by-item DoD conformance hunting (the requirements adversary). DoD scoring at close
still checks "not implemented at all". For a ticket where those matter, run it `--full`.

### Backfill tickets are refused in lean mode

`mutation-check --backfill` is a backfill ticket's **only** gate (`SKILL.md`, invariant
tickets), and lean does not run it. A backfill ticket run lean would be proven by nothing.
At intake, when `$BACKFILL` is set and `--full` is absent:

```
RUN BLOCKED: <TICKET> carries slopstop-backfill — lean mode has no gate for a backfill
             ticket (mutation-check is cut). Re-run with --full.
```

Stop that ticket; every other ticket in the list still runs.

## The lean state machine

Same stage **names** as the full table — `run.jsonl` keys are unchanged, so every reader
and `derive.py` work on both. The numbers are lean's own, and lean phase lines use them
(`user-output.md`).

| # | stage | kind | record | notes |
|---|---|---|---|---|
| 1 | `intake` | I | note | as `SKILL.md`, plus the backfill refusal above |
| 2 | `investigate` | W | span | unchanged — read-only, fanned out for all N tickets first |
| 3 | `branch` | I | note | unchanged |
| 4 | `work` | W | span | **the single worker** — below. Its return carries the `phase0-commit` sha and the four gate verdicts; you transcribe them |
| 5 | `pr` | I | span | unchanged, and the `size` note is written first, as today |
| 6 | `review` | W | span | **`/code-review`** — below |
| 7 | `bot-read` | I | note | unchanged |
| 8 | `merge` | I | span | unchanged, except there is no `blessed_sha` to re-check — the tamper re-run in stage 6 is the tip check |
| 9 | `close` | I | span | unchanged |
| 10 | `archive` | I | **note** | two files, inline — below |

`work` is a `W` stage: it gets a launch note like any worker launch.

## Stage 4 — `work`: one worker, one worktree, red → green → gates

### What it is

A single `Agent()` launch, per `worker-launch.md`'s **FIRST-worker** form (it renames its
branch to `<type>/<TICKET>`), at the `implement` stage's tier. Inside it, the worker
invokes the existing skills in sequence — **`slopstop:red-tests`, then `slopstop:implement`**
— then runs the four gate scripts, then commits. The skills are the prompt; nothing here
restates them.

**The worker skills are unchanged and unaware of lean.** `red-tests` still returns the
report in its Step 7 shape; `implement` still returns its four parts. The `work` worker
is the thing that used to be the orchestrator between stages 4 and 9, moved into the
worktree where the code is.

### The brief — what the launch prompt carries beyond the FIRST-worker guard

Everything a worker would otherwise be handed stage by stage, all at once:

- the ticket key, body, five sections and DoD, verbatim
- `investigate`'s report, including the **predicted file map** (stage 4 passes it to
  `tamper.sh --file-map` as a JSON array)
- `$BASE`, `$FORK` (equal to `$BASE` on a fresh branch), `$ORIGIN_REMOTE/$BASE_BRANCH`
- the mode: `normal` or `refactor` (backfill never reaches here)
- the resolved gate thresholds: `$CC_WARN $CC_REJECT $CC_EXEMPT $FILE_NLOC_WARN
  $CC_EXCLUDE_PATHS $DUP_MIN_LINES $DUP_EXEMPT $DUP_EXCLUDE_PATHS`
- the gate script directory: `~/.claude/slopstop/tools/gates/` (installed by
  `setup-project.py` alongside `derive.py`)
- the graph-tool directive (`worker-launch.md`), as for every code-reading worker
- the step list and the return contract below, verbatim

### The steps the worker runs, in order

1. **Red tests.** `Invoke Skill({skill: "slopstop:red-tests", args: "<ticket, DoD>"})`
   — with `--refactor` when the mode is refactor, in which case it returns
   `PHASE 0: none — refactor` and steps 2–3 are skipped with `$FROZEN = none`.
   `PHASE 0: none — prose-only change` likewise. Anything other than `RED` or those two
   literals: stop, return `WORK BLOCKED: <the report's first line>`.
2. **Phase 0 commit — explicitly by path.** Stage exactly the test files and stub files
   the report names, nothing else:
   ```
   git add -- <test files> <stub files>
   git commit -m "[<TICKET>] Phase 0: failing tests — <N> cases" \
              -m "Co-Authored-By: Claude <model> using slopstop <noreply@anthropic.com>"
   FROZEN=$(git rev-parse HEAD)
   ```
   `$FROZEN` is captured **here**, at the commit, the only moment it is unambiguous
   (`stages-phase0.md`). It goes into the return as `PHASE0: <sha>`.
3. **Implement.** `Invoke Skill({skill: "slopstop:implement", args: "<ticket, plan, the
   failing tests and node-ids from step 1>"})` — `--refactor` when the mode is refactor.
   `IMPLEMENT BLOCKED` → stop, return `WORK BLOCKED: <line>`. Then commit everything
   `implement` changed: `git add -A && git commit -m "[<TICKET>] <what it did>"`.
4. **Tamper + file map** (the old 8a):
   ```
   ~/.claude/slopstop/tools/gates/tamper.sh --frozen $FROZEN --tip HEAD --base $BASE \
       --stubs <step 1's stub files, omit the flag when none> \
       --fork $FORK --file-map '<predicted file map as JSON>' [--refactor]
   ```
   Stubs are subtracted from the frozen set — they are not frozen, the implementation
   replaces them (`handoff-verification.md`). Pass exactly what `red-tests` listed.
   `TAMPER FAIL` or `FILEMAP FAIL` → **stop**. Mechanical gates never soften: do not
   restore a frozen line and continue, do not widen the map. Return `WORK STOPPED:` with
   the verdict lines verbatim.
5. **Vacuity** (normal mode only; refactor records `VACUITY SKIPPED: refactor ticket — no
   new tests` itself):
   ```
   ~/.claude/slopstop/tools/gates/vacuity.sh --base $BASE --frozen $FROZEN --tip HEAD \
       --node-ids <contract + non-interference ids from step 1 — NEVER the regression ids> \
       --test-files <step 1's test files> --stubs <step 1's stubs, or omit the flag> \
       --command '<step 1's test command>'
   ```
   The `regression`-tagged omission is the caller's (`stages-implement.md`), and the
   caller is now this worker: list each omitted id with its quotation in the return.
   `VACUITY VACUOUS` → **stop**; the fix (strengthen the assertion) edits a frozen file.
6. **Complexity**:
   ```
   ~/.claude/slopstop/tools/gates/complexity.sh --base $FORK --repo . --tip HEAD \
       --warn $CC_WARN --reject $CC_REJECT --exempt-pre-existing $CC_EXEMPT \
       --file-nloc-warn $FILE_NLOC_WARN --exclude-paths '$CC_EXCLUDE_PATHS'
   ```
   `CC VIOLATIONS` with `N > 0` → **one** refactor pass around the code's real seams
   (`stages-implement.md`, "Reducing a production CC breach"), re-run the tests, commit,
   re-run the script once. Still `N > 0` → stop.
7. **Duplication**:
   ```
   ~/.claude/slopstop/tools/gates/duplication.sh --base $FORK --repo . --tip HEAD \
       --min-lines $DUP_MIN_LINES --exempt-pre-existing $DUP_EXEMPT \
       --exclude-paths '$DUP_EXCLUDE_PATHS'
   ```
   `DUP VIOLATIONS` → extract the helper (dedupe is in scope, universal §4), re-run the
   tests, commit, re-run the script once. Still blocking → stop.
8. **Final state.** `git status --porcelain` must be empty. Every gate re-run after a fix
   is re-run against the new `HEAD`; report the last verdict of each and how many runs it
   took.

**Each script's exit code is the branch:** 0 = proceed, 1 = the finding rule above, 2 =
`BLOCKED`/`ERROR` — stop and return the verdict line; a BLOCKED gate is a wrong argument,
not a pass. **Never round `SKIPPED`, `INCONCLUSIVE` or `BLOCKED` to clean.**

**Every timestamp the worker reports comes from `date -u +%FT%TZ` at the moment**, not
reconstructed at the end.

### The return contract

```
WORK <CLEAN | STOPPED: <first verdict line> | BLOCKED: <reason>>

PHASE red-tests   <started> <finished>  <PHASE 0 line verbatim>
PHASE0            <sha | none — refactor | none — prose-only change>
PHASE implement   <started> <finished>  <one line: N tests green, regressions none|named>
PHASE tamper      <started> <finished>  <TAMPER … line> | <FILEMAP … line>
PHASE gates       <started> <finished>  <VACUITY …> ; <CC …> ; <DUP …>   (runs: v1 c2 d1)
Regression ids omitted from vacuity: <id — "quotation"> | none
Findings reported, not fixed: <implement's part 4, verbatim> | none

<red-tests report verbatim>
<implement report verbatim>
<each gate's full output verbatim>

WORKTREE: <pwd>
BRANCH: <branch>
COMMIT: <sha of the final commit>
```

`STOPPED` and `BLOCKED` still carry every `PHASE` line that ran, with the failing one last.

### What the orchestrator does with it

**Write the `work` close first**, as for any worker (`run-jsonl.md`, writing discipline).
Then transcribe — never re-derive — from the `PHASE` lines:

```json
{"ticket":"BILL-501","event":"note","stage":"phase0-commit","at":"<PHASE0 time>","result":"<sha>"}
{"ticket":"BILL-501","event":"note","stage":"work","at":"…","phase":"red-tests","started":"…","finished":"…","result":"PHASE 0: RED"}
{"ticket":"BILL-501","event":"note","stage":"work","at":"…","phase":"implement","started":"…","finished":"…","result":"6 tests green, regressions none"}
{"ticket":"BILL-501","event":"note","stage":"work","at":"…","phase":"tamper","started":"…","finished":"…","result":"TAMPER CLEAN | FILEMAP CLEAN"}
{"ticket":"BILL-501","event":"note","stage":"work","at":"…","phase":"gates","started":"…","finished":"…","result":"VACUITY CLEAN ; CC CLEAN — 2 exempt ; DUP CLEAN"}
```

**Notes, not spans**, because you did not observe the transitions — the worker did — and a
span without a launch note of its own is an unattributed launch to invariant 7. The
`phase` notes carry the same timing under a shape `derive.py` already ignores. The sole
writer is still you; the worker wrote nothing under the tracking dir.

Then verify the handoff exactly as for any worker: `git log --oneline $BASE..<type>/<TICKET>`
must show at least the Phase 0 commit and one implementation commit (or, for refactor, one
commit); `git -C <worktreePath> status --porcelain` must be empty; then remove the worktree
(`SKILL.md`, worktrees). A `WORK STOPPED`/`BLOCKED` stops the ticket with the worktree
preserved and locked (`failure-and-salvage.md`) — same as any stop.

**`$FROZEN`** for every later step is the `PHASE0` sha from the return. Carry it; the
stage-6 tamper re-check needs it.

## Stage 6 — `review`: `/code-review`, once, from a context that did not write the code

Universal §9's rule is unchanged and it is the whole point of this stage's launch form:
**the worker that wrote the code never reviews it.** The `work` worker is gone by now —
its worktree removed — and this is a fresh `Agent()` with the **LATER-worker** brief
(`git switch <type>/<TICKET>`), at the `review` stage's tier:

```
Invoke Skill({skill: "code-review", args: "<PR#> medium --fix"}) and follow it.
Never edit these files, which are frozen: <the files in $FROZEN, listed>.
Then `git add -A` and commit whatever --fix changed as
`[<TICKET>] apply code-review findings`, or commit nothing and say so.
Return every finding as `<file>:<line> — <severity> — <summary> — applied|reported`,
then the three WORKTREE:/BRANCH:/COMMIT: lines.
```

`/code-review` **is** agent-invocable in this form — verified 2026-08-27 (universal §9). The
PR must already exist, which is why `pr` precedes `review` in the lean table. `--fix`
applies what it finds to the working tree; the commit is the handoff.

After it returns:

1. Close the `review` span with a `findings` object (`run-jsonl.md`) — `applied` and
   `reported` by severity, transcribed from the returned list. Map the tool's severities
   onto `blocker`/`major`/`minor` as it states them; do not invent one it did not give.
2. **Re-run tamper from the main worktree** — the review may have touched a frozen file:
   ```
   ~/.claude/slopstop/tools/gates/tamper.sh --frozen $FROZEN --tip <type>/<TICKET> --base $BASE
   ```
   Its own `tamper` span, as the 10b re-check was. `TAMPER FAIL` stops the ticket.
3. Verify the handoff and remove the worktree, as for any worker.
4. If the branch advanced, `git push $PR_REMOTE <type>/<TICKET>` from the main worktree.
5. A **`reported`, unapplied finding at `blocker` severity stops the ticket** — human,
   finding quoted. `major`/`minor` reported findings go into `findings.md` and the PR
   proceeds.

There is no round 2. What `/code-review` did not fix and did not block on is recorded and
merges.

## Stage 10 — `archive`: two files, inline, a note

Post `task_plan.md` and `findings.md` — and only those two — to the ticket, from the main
worktree, using the per-backend carrier table in `skills/archive/SKILL.md` ("Per backend"
and "Composing a comment body"). Read that section and follow it; the bytes still move by
`--body-file` / attachment, never through your own arguments, and the `## 📁 <filename>`
header still makes a re-run idempotent.

Two API calls, no splitting (both files are far under any comment ceiling), so it is a
**note**, not a span:

```json
{"ticket":"BILL-501","event":"note","stage":"archive","at":"…","result":"posted task_plan.md (3.9 KB), findings.md (1.2 KB)"}
```

Then `run_closed`, then the `mv` to `$ARCHIVE_DIR` — same order as `stages-close.md` steps
6–7. `run.jsonl`, `run-derived.jsonl` and anything else in the directory stay on disk in
`$ARCHIVE_DIR/<TICKET>/`; they are not posted.

A failed post is `result: "failed: …"` on the note and stops nothing — the merge is done.
