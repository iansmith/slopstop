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
the launches to two or three (`investigate`, `work`, and a fix worker when review found something) and turns the mechanical gates into
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
| `review` (10) | **`/code-review`** at effort `medium`, once, invoked by the orchestrator (which did not write the code), then a fix worker | `slopstop:review` loop, cap 5 |
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
| 6 | `review` | I + W | span | **`/code-review` inline at top level**, then one fix worker if there is something to apply — below |
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
   re-run the script once. Still `N > 0` → stop. **The pass may not touch a frozen file.**
   If reducing the breach would edit one, that is not a fix: stop with
   `WORK STOPPED: CC VIOLATIONS — reduction would edit frozen <file>` and the finding.
7. **Duplication**:
   ```
   ~/.claude/slopstop/tools/gates/duplication.sh --base $FORK --repo . --tip HEAD \
       --min-lines $DUP_MIN_LINES --exempt-pre-existing $DUP_EXEMPT \
       --exclude-paths '$DUP_EXCLUDE_PATHS'
   ```
   `DUP VIOLATIONS` → extract the helper (dedupe is in scope, universal §4), re-run the
   tests, commit, re-run the script once. Still blocking → stop. **A clone group with an
   instance inside a frozen file is not yours to dedupe** — the script scans test files
   too, and extracting a helper there rewrites frozen lines. Stop with
   `WORK STOPPED: DUP VIOLATIONS inside the frozen set` and the clone group verbatim; the
   human decides.
8. **Tamper again, then final state.** If step 6 or 7 committed anything, re-run step 4's
   `tamper.sh` command unchanged against the new `HEAD` — it costs a second, and it is
   the only check that sees what a gate-driven fix did to the frozen set. (Found on the
   first lean run, 2026-09-07: as first written, the next tamper run was stage 6's
   post-review re-check, after the PR and the review had already been spent on a branch
   that was dead at step 7.) `TAMPER FAIL` → stop, as in step 4. Then
   `git status --porcelain` must be empty. Every gate re-run after a fix is re-run
   against the new `HEAD`; report the last verdict of each and how many runs it took.

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

## Stage 6 — `review`: `/code-review`, once, at top level, then a fix worker

Universal §9's rule is unchanged: **the context that wrote the code never reviews it.** In
lean mode the code was written by the `work` worker, whose context is gone with its
worktree. The orchestrator did not write it. So the orchestrator invokes the review
**itself, at top level**, and a separate worker applies what it finds.

**Why top level, not a subagent — measured on the first lean run (SOP-589,
2026-09-07).** `/code-review` runs its eight angles as *background* agents. Wrapped in an
`Agent()`, the wrapper ended its turn with "I'll wait for the background agents" and that
sentence came back as the worker's result; the orchestrator then removed the worktree per
the handoff rule and killed four angles mid-read. The merge was gated on five of eight
angles salvaged from transcripts. At top level the background agents belong to the main
loop, which is notified when each completes and can wait. This corrects the section as
first written, which said the subagent form was verified — the 2026-08-27 verification
was of the call being *accepted*, not of its background angles completing inside a
subagent.

### 6a — the review, inline

**Run the tamper re-check first.** The `work` worker's last tamper run was before its
step 6–7 fixes may have committed (and, on runs from before `a9bfd9a`, never after). A
mechanical FAIL here means no review is bought — the 8a principle:

```
~/.claude/slopstop/tools/gates/tamper.sh --frozen $FROZEN --tip <type>/<TICKET> --base $BASE \
    --stubs <the stubs from the work return>
```

Its own `tamper` span. `TAMPER FAIL` stops the ticket before the launch note is written.

Then:

```
Skill({skill: "code-review", args: "<PR#> medium"})
```

**No `--fix`** — the orchestrator's working tree is the main checkout on the integration
branch, so a fix applied there lands in the wrong place. The PR must already exist, which
is why `pr` precedes `review`. **Wait for every angle to complete** before reading the
findings; a partial set is not a review. Bracket the whole thing as the `review` span
(`round: 1`), and write a launch note with `worker: code-review` and the session's own
model — it is a launch in the sense invariant 7 cares about, even though it is not an
`Agent()`.

Close the span with a `findings` object (`run-jsonl.md`): every finding is `reported` at
this point, by severity as the tool states it (`blocker`/`major`/`minor`; do not invent
one it did not give). **A `blocker` stops the ticket** — human, finding quoted. Refute
what you can refute by direct check and say so; a wrong premise is not a defect.

### 6b — the fix worker, only when there is something to apply

If any `major`/`minor` finding is real and mechanical to apply, launch **one** fresh
`Agent()` on the **LATER-worker** brief (`git switch <type>/<TICKET>`) at the `review`
stage's tier, with the findings quoted verbatim:

```
Apply these code-review findings, and nothing else: <findings, verbatim>.
Never edit these files, which are frozen: <the files in $FROZEN minus stubs, listed>.
Run the project's test command; it must be green. Then `git add -A` and commit as
`[<TICKET>] apply code-review findings`, or commit nothing and say why.
Return `FIX CLEAN` / `FIX PARTIAL: <what was not applied and why>` / `FIX BLOCKED: <r>`,
then the three WORKTREE:/BRANCH:/COMMIT: lines.
```

Its own `review` span, `round: 2`, closing with `findings.applied` transcribed from its
return. Then, in order:

1. **Re-run tamper** (the 6a command) against the new tip — the fix may have touched a
   frozen file. Its own `tamper` span. `TAMPER FAIL` stops the ticket.
2. Verify the handoff and remove the worktree, as for any worker.
3. `git push $PR_REMOTE <type>/<TICKET>` from the main worktree.

No findings worth applying → no launch, no round 2, and say so in the `review` close.

There is no review round 3. What `/code-review` reported and the fix worker did not apply
goes into `findings.md` and merges.

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
