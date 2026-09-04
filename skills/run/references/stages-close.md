# Stages 13-15 — merge, close, archive

Read when the orchestrator enters stage 13 for a ticket. Serial across tickets, all inline.

## Stage 13 — merge

0. **Re-check the blessing before merging.** `git rev-parse <branch>` against `blessed_sha`. If the tip has advanced, **the blessing is void** — go back to stage 10b and re-verify. Record the re-check inside the `merge` span, not as a `pr` one. If you go back to 10b, that opens its own spans — never reopen the first.

1. `gh pr merge --merge --delete-branch` against `$OWNER/$REPO`. **Never** `--squash`, `--rebase`, or `--admin`. Read the PR back and assert `state == "MERGED"`; capture `$MERGE_COMMIT`.

   **Read `mergeStateStatus` first:**

   | `mergeStateStatus` | what it means | do |
   |---|---|---|
   | `CLEAN` | mergeable, checks green | merge |
   | `UNSTABLE` | a non-required check failing or queued | merge — say which check |
   | `BLOCKED` | required reviews or checks unsatisfied | **stop this ticket**, naming the unmet requirement |
   | `BEHIND` | base has advanced | `git merge <base>` into the branch, then re-verify from 10b |
   | `DIRTY` | conflicts | **stop this ticket**, naming conflicting files |
   | `UNKNOWN` | GitHub hasn't computed it yet | wait ~5s, ask once more; if still `UNKNOWN`, merge and let the read-back decide |

   **`UNKNOWN` is not a failure** — it is the normal answer for a PR opened seconds ago. Reading `mergeStateStatus` does not replace the read-back assertion; do both.

## Stage 14 — close

2. **Score the DoD** before advancing anything. `unverifiable` is not a polite `met`.
   -> Read `skills/run/references/dod-scoring.md`

3. **Advance the ticket, per `$POST_MERGE_DONE`:**

   - **`true`** — take the ticket to its **terminal** state.
   - **`false`** — advance **exactly one** state and stop. The ticket is deliberately parked (e.g. awaiting on-device verification).

   **Ensure a label exists before applying it.** On GitHub, applying an unknown label fails the whole edit:

   ```bash
   $GH label list --repo "$OWNER/$REPO" --json name -q '.[].name'   # exact match
   $GH label create "<label>" --repo "$OWNER/$REPO"                 # only if absent
   $GH issue edit "$N" --repo "$OWNER/$REPO" --add-label "<label>"
   ```

   Idempotent: an existing label is used as-is. The one definition of per-backend label creation lives in `create-ticket/SKILL.md` Step 3a.

   **Only slopstop's own labels.** This creates the configured status labels and slopstop's two mode labels — nothing else.

   Never write `Closes #N` in a PR body — GitHub would auto-close, skipping the label half and overriding `post_merge_done = false`.

   When you park a ticket, report it under `parked awaiting <state>`, never folded with completed ones.

3a. **Report issue links that contradict the ticket's `Blocked by:` header.** Read native relations and compare against the header parsed at intake. **Name every disagreement with the link id** in the final report. **This never stops or fails anything** — it is a board-display disagreement. On JIRA, issue links cannot be removed by the available tooling. On Linear, relations can be removed through the API — report as fixable. GitHub has no native `Blocked by` relation.

4. **Write the DoD-confirmation into `task_plan.md`.**

4a. **Derive the compute record:**

   ```bash
   python3 <slopstop>/tools/metrics/derive.py "$TICKET" --repo "$REPO_ROOT"
   ```

   Record outcome as a `close`-stage **note**. Must run here, not in `:archive` — `run.jsonl` survives but transcripts do not. **A derive failure never fails the run.** Re-entering close is safe: the deriver leaves an existing `run-derived.jsonl` alone. Do not pass `--redo` here.

## Stage 15 — archive

5. **Launch the `archive` worker** (`--ticket --dir --system` + backend coords). It posts one comment per tracking file. Bracket the span. Best-effort: `ARCHIVE PARTIAL` or `BLOCKED` never rolls back a merge.

6. Close the `archive` span, then append `run_closed`. **In that order.**

7. `mkdir -p $ARCHIVE_DIR && mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>`. **The move is yours, not the worker's** — it runs last, after the log is closed. If the destination exists, rename to `<TICKET>-<timestamp>`; never lose history.

## Human waits — bracket every one

Whenever you block on the user — adversary add decision, a gap test that came up green, a gate failure, a DoD item not `met`, a merge conflict — write the `waiting_for_user` `started` line **in the step that asks** and the `finished` line **in the step that receives the answer**.

You are the only thing that can record it. This is the mechanism separating machine time from a weekend. **The wait that actually happens is not an `--interactive` ask** — mechanical gate FAILs and checker escalations surface on the autonomous path with nothing to prompt a span.

`tools/metrics/derive.py --check` now names every unbracketed gap over 120s, sums the residue, and reports a run with big gaps and zero waits as **unmeasured, not measured-zero**.

**Bracketing a wait does not shorten it, and is not licence to skip one.** The mechanical gates keep no permissive setting.

## Resuming

A run resumes from disk, never from memory.

1. Read `$TRACKING_DIR/<TICKET>/run.jsonl` (or `$ARCHIVE_DIR/` — an archived ticket is finished).
2. **Validate it** against the invariants in `run-jsonl.md`.
3. On failure: name the unclosed spans and stop. **Report no timing numbers at all.**
4. Append a `session_resume` note.
5. Continue from the last **closed** span. A `started` with no close means that stage was interrupted: re-run it.

At run end, validate again, then append `run_closed`.

**Get the timing from the tool, not from your own arithmetic:**

```bash
python3 <slopstop>/tools/metrics/derive.py "$TICKET" --repo "$REPO_ROOT" --check
```

`--check` writes nothing. `run.jsonl` holds *stage* spans, not worker spans — computing the three-way split by hand is how negative figures and false "uncomputable" reports happen. `run-jsonl.md`'s "Computing time" owns the sources and the fallback.

## Re-scoring after a ticket-defect `not-met`

A ticket can stop at close because the *ticket* was wrong, not the work.

### Recognise the state — three conditions, all from `run.jsonl`

A ticket is **re-scorable** when all three hold:

1. `merge` has a `finished` span. The work is landed.
2. The **latest** `close` span is `failed`.
3. `run_closed` is the last record.

**Condition 2 is the latest `close`, not any `close`.** A log already re-scored holds both a `failed` and a later `finished` close.

### Refuse it otherwise, and name which condition failed

| what the log shows | verdict |
|---|---|
| no `merge` span, or `merge` `failed`/started-no-close | **refuse** — `RESCORE REFUSED: merge never finished` |
| `close` `finished` | **refuse** — `RESCORE REFUSED: close already succeeded` |
| no `run_closed`, or a span still open | **refuse** — `RESCORE REFUSED: run was interrupted — resume it instead` |
| branch tip moved since merge commit | **refuse** — `RESCORE REFUSED: branch state has moved` |

**This is a close-out path, not a way to skip gates.**

### What re-scoring does, and does not, re-run

**Re-run:** DoD scoring, then stages 13-15 from step 2 onward.
**Do not re-run** investigate, implement, gates, review, handoff, PR, or merge.

### Score the ticket as it is now

Re-fetch the ticket body from the backend before scoring. Read labels again too.

### The original `not-met` survives

A re-score **appends**. It never overwrites the failed `close` span or the DoD confirmation.

```
span  close       started   13:27:42   re-open of close after the ticket-level fix; the
                                       round-1 close failed on DoD bullet 5
note  close       ...       13:27:42   ticket changes made at the owner's request: DoD
                                       bullet 5 rescoped to ...
span  close       finished  13:27:42   DoD re-scored 6 of 6 MET against the rescoped bullet 5.
                                       The measurement did not change — the item did.
```

Carry the distinction into the DoD confirmation and final report: *"6 of 6 met after the ticket-level fix; the round-1 `not-met` on bullet 5 stands in the record."*

**Re-scoring never edits the ticket.** Authoring is `:tickets`' work.

## Failure handling

A ticket that stops is closed in `run.jsonl` with `failed` and its reason, and **every independent ticket keeps running**.

**A stopped ticket is not a held one.** A stop means the ticket ran; a hold means it never started. Separate headings in the report and separate treatment.

**A stopped ticket preserves everything and yields findings.** Branch, commits, worktree, tracking dir, and findings verbatim.
-> Read `skills/run/references/failure-and-salvage.md`

Two rules from it: **never clean up on a failure**, and **a retry carries the prior findings verbatim**.

Never resolve a stop by weakening the thing that raised it: no deleting a test, no narrowing an assertion, no `Skip()`, no editing a frozen expectation.

## Publishing a review primitive's basis — `$PUBLISH_ARTIFACTS`

**Off unless `[workflow].publish_artifacts` is `true`.** When absent or `false`, nothing in this section happens.

**The covered set is exactly three review primitives** — stage 7 (`adversary`), stage 10 (`review`), stage 10b (`handoff`). Not stage 8a (mechanical, no `findings`), not stage 9's gates.

**You publish, not the worker.** Compose from what the worker returned, after it returns. **Never mention artifacts or this key in a worker prompt.**

**One artifact per `(ticket, stage)`, accumulating.** Publish on round 1; on later rounds, **redeploy to the same URL**. Read the target back from `run.jsonl`.
-> `skills/run/references/run-jsonl.md`, "The artifact note", owns the note shape.

**Keep the title and favicon stable across redeploys.**

**What goes on the page, per round:** the verdict line; each finding as `file:line` + severity/class + summary; refuted findings with reason; launch tuple (`tier`, `model`, `effort`); source lines each finding cites. **Not** whole files, whole diffs or ticket bodies.

**Transcribe; do not author.** Never record anything **only** in an artifact. `run.jsonl` is the record; the artifact is a view.

**Never fail silently.** If the key is `true` and `Artifact` cannot be called, write the composed document into the tracking dir and say so — that publication was unavailable **and** where the file is.

**Nothing about worker contracts changes here.**
