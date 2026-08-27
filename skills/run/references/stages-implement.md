# Stages 8-9 — implement, tamper, gates, pinning

Read when the orchestrator enters stage 8 for a ticket.

## Stages 8a and 10b — handoff verification

**You do this, not a worker.** The `implement` worker's report is the *subject* of the
check, never its evidence. The full contract lives in `references/`:
-> Read `skills/run/references/handoff-verification.md`

Three things to know before reading it:

- **8a is mechanical and runs first.** A `TAMPER FAIL` or `FILEMAP FAIL` stops the ticket *before stage 9 launches anything*.
- **`TAMPER BLOCKED` is not `TAMPER CLEAN`.** Both guards (unset `$FROZEN`, empty frozen file set) fail toward looking clean. Assert them before diffing.
- **10b is fed artifacts only.** Not `implement`'s report, not the PR description, not your summary.

Bracket 8a as an inline span and each 10b launch as its own span.

### Branch on the three-way verdict

```
HANDOFF CORRECT: <sha>  -> record blessed_sha, go to stage 11
HANDOFF SALVAGE: <n>    -> repair IN THIS WORKTREE, on this branch, guided by the findings;
                           commit; then re-run 10b. Never self-certify the repair.
HANDOFF DROP: <n>       -> preserve and lock this worktree; relaunch a fresh agent into a
                           FRESH worktree with the findings quoted verbatim
anything else           -> stop, surface the raw verdict verbatim
```

**`SALVAGE` is the orchestrator implementing, which it otherwise never does.** Constraints it does not relax (frozen tests stay frozen, repaired branch re-enters at 10b) bind here — see `failure-and-salvage.md`.

**Findings cross back verbatim, never paraphrased.** An empty finding list on `SALVAGE` or `DROP` means the evaluator is broken — re-run the check.

**Three attempts total.** The second failure forks on *why*. On exhaustion the ticket stops and everything is preserved.

**10b is a review primitive, so its closes carry `findings` too** — transcribe both agents' per `run-jsonl.md`. **One launch note per agent, not per span.**

## Stage 9 — the four gates, then the pinning pass

**Capture `$TIP` first**: `git rev-parse <type>/<TICKET>`. Resolving it once makes the four verdicts attributable to one commit.

Launch all four together on the **READ-ONLY brief** (`worker-launch.md`) — `git switch --detach $TIP` so no gate holds the branch.
Why: a branch can be checked out in exactly one worktree. Four workers on one ticket branch means one wins the `git switch` and three die.

- `slop-check --scope <ref-range-or-PR> --ticket <the ticket's stated scope> --frozen $FROZEN`
- `vacuity-check --base $BASE --frozen $FROZEN --node-ids <from stage 4+7, MINUS the declared invariance ids> --test-files <...> --stubs <...> --command <...>`
- `complexity-check --base $FORK --repo <root> --warn $CC_WARN --reject $CC_REJECT --exempt-pre-existing $CC_EXEMPT --file-nloc-warn $FILE_NLOC_WARN --exclude-paths $CC_EXCLUDE_PATHS`
- `duplication-check --base $FORK --repo <root> --min-lines $DUP_MIN_LINES --exempt-pre-existing $DUP_EXEMPT --exclude-paths $DUP_EXCLUDE_PATHS`

**Pass `$FORK`, not `$BASE`** to `complexity-check` and `duplication-check` — the derived point from the `$OWN` section. The workers cannot correct this themselves.

`complexity-check` and `duplication-check` **block** if you omit a threshold; neither reads config.

**Every mechanical gate runs in every mode.** Mode-based skips remove tier-above worker launches, never mechanical checks.

When `$REFACTOR`: launch two. `vacuity-check` not run — record `VACUITY SKIPPED: refactor ticket — no new tests`. `slop-check` gets `--frozen none --refactor`.

When `$BACKFILL`: launch **one** (`slop-check` only). `vacuity-check` not run. `complexity-check` not launched — zero production diff. Record `CC SKIPPED: backfill ticket — no production diff`. `duplication-check` not launched — zero production diff. Record `DUP SKIPPED: backfill ticket — no production diff`. `slop-check` gets `--backfill`. `$FROZEN` **is** present — pass it normally.

A finding from `slop-check`, a `vacuous` verdict, `VIOLATIONS` from `complexity-check`, or `VIOLATIONS` from `duplication-check` **stops the ticket**. Warn-level proceeds. `SKIPPED` / `BLOCKED` / `could-not-determine` are reported as themselves — never rounded to a pass.

### `regression`-tagged tests never reach `vacuity-check`, and the omission is recorded

`red-tests` tags every test with `contract`, `regression` or `non-interference` (Step 4a). **Read the tags; do not re-derive them.**

**Omit `regression` node-ids** from the list and write **one `note` naming each omitted id with the quotation it carried**. **Refuse a tag missing its required clause.** **Only Phase 0 tags count** — a tag added after a gate flagged something is the failure mode this guards against.

**A `vacuous` verdict on a `contract` or `non-interference` id is a real defect and stops the ticket:**

- **`contract`** -> strengthen the assertion until it fails against base. Never delete, narrow, or skip.
- **`non-interference`** -> strengthen the positive pairing, not the negative half.
- **Untagged** -> a `red-tests` defect upstream. Stops the ticket; fix belongs at Phase 0.

Why tags moved to authoring time: six vacuous tests on AATK-81 were all decidable when written — a gate can only stop, the author could have fixed all six for nothing.

**A CC finding in a test function does not stop the ticket.** `complexity-check` Step 4a reports test rows as `T test-info`, outside `N`. `T > 0, N = 0` is the clean run it is.

### Reducing a production CC breach — one pass, real seams

**Refactor around the code's existing seams. Do not transform mechanically.** Extracting a helper whose only purpose is moving branches out of the measured function games the proxy.

**Attack the whole reject set in one pass.** Re-measuring means re-running a gate stage.

**Carry `complexity-check`'s exempt list into the final report, ranked, with its total.** It is the queue for `/slopstop:tickets --refactor <fn>...`.

### The pinning pass — mutate what `implement` actually wrote

Nothing between stage 8 and 10b perturbs the real implementation. Stage 5 mutates stubs; `vacuity-check` contains no mutation logic. So every "the suite does not actually pin this" defect had to survive to the tier above.

Launch after the four gates return, **not with them** — it mutates production and `worker-launch.md` prohibits two workers sharing a tree while one perturbs it. Also worth nothing on a branch a gate already condemned.

```
$ROUND = 1
loop:
  mutation-check --implemented --targets <$OWN's production files>
                 --node-ids <stage 4 + 7> --tests <...> --command <...>

  MUTATION CHECK PINNED: n of n      -> converged, go to stage 10
  MUTATION CHECK NOT PINNED: n of m  -> write a test pinning each named symbol,
                                        confirm it is RED against the same mutation,
                                        commit, then run another round
  MUTATION CHECK BLOCKED: <r>        -> stop this ticket, surface <r>
  anything else                      -> stop, surface the raw verdict verbatim

  if $ROUND >= 3  -> capped: stop the ticket, report every symbol still unpinned
  $ROUND += 1
```

**One span per round.** **Authoring the pinning test is yours.** Adding a test to a non-frozen file is already legal, so nothing about frozen-test rules is relaxed. Confirm the new test is **red against the surviving mutation** before committing.

**Targets come from `$OWN`, never `$BASE`.**

**Mode:**

- **`$REFACTOR`** — **run it, and report rather than fix.** A surviving mutation is reported as a finding: `PINNING REPORTED: <n> unpinned — refactor ticket, no test may be added`.
- **`$BACKFILL`** — **skipped.** No production diff to mutate. Record `PINNING SKIPPED: backfill ticket — no production diff`.

**Record the round count and the wall-clock.** A gate that materially lengthens the run is a trade to make knowingly.
