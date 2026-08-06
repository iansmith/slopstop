---
description: The single lifecycle entry point — take one or more tickets and drive each through its whole lifecycle (investigate, red tests, adversary, implement, gates, review, PR, merge, archive), interleaving them, launching workers for judgment work and doing every mechanical step inline. Invoke as /slopstop:run <TICKET> [TICKET...].
disable-model-invocation: true
---

# /slopstop:run

You are the **orchestrator**. There is no `:start`, `:plan`, `:pr`, `:merge`, `:archive`,
`:document` or `:update` — this skill is all of them. You take a list of tickets and drive
each one from "open" to "merged and archived", interleaving them so ticket A can be in
review while ticket B is still writing red tests. You run at **top level**; you launch
workers, and workers never launch workers.

## Read these two first — they are contracts, not background

- `skills/run/references/worker-launch.md` — the one `Agent()` launch form, stage → tier →
  model resolution, the nine-worker roster with each worker's arguments and return, and
  the data-flow diagram of what you must thread between them.
- `skills/run/references/run-jsonl.md` — the state/timing file: line shape, the sole-writer
  rule, human-wait bracketing, and the validation invariants.

**Do not restate either here or in your own output.** One definition each (universal §5).
Every launch and every span below assumes you have read them.

## Arguments

`$TICKETS` — one or more ticket keys (`BILL-501 BILL-502`). Empty → ask; never guess a
ticket list from the branch or the backlog. Each must match `^$PREFIX-\d+$`; one that does
not is refused by name and the rest of the list still runs. `--constraint "<phrase>"` is
optional and applies to every ticket: passed verbatim to `investigate`, a hard scope
everywhere else.

## Project scope — you are the sole reader of `.project-conf.toml`

Read it from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Missing from both → stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file
manually with system + key."`

Resolve, and carry, all of the following. A missing key takes its documented `CONFIG.md`
default; a missing table never errors. **Workers read none of this** — every value reaches
a worker only as an explicit argument, and a worker given nothing blocks rather than
guessing.

| value | source | default |
|---|---|---|
| `$PREFIX` | `prefix` | none — stop if absent or not `^[A-Za-z][A-Za-z0-9]*$` |
| `$SYSTEM` | `system` | none — authoritative, never inferred from MCP availability |
| `$OWNER`/`$REPO` | `pr-repo`, else split `key` on `/` | — |
| `$PR_REMOTE` / `$ORIGIN_REMOTE` | `pr-remote` / `origin-remote` | `origin` |
| `$BASE_BRANCH` | `base-branch`, else the repo default branch | — |
| stage models | `[stage_tiers].<stage>` → `[tiers.<name>]` | per `CONFIG.md` |
| `$PR_BACKEND` | `[pr_review].backend` | `coderabbit` |
| `$CC_WARN` | `[autonomous].cc_warn_threshold` | `5` |
| `$CC_REJECT` | `[autonomous].cc_reject_threshold` | `10` |
| `$CC_EXEMPT` | `[autonomous].cc_exempt_pre_existing` | `false` |
| `$FILE_NLOC_WARN` | `[autonomous].file_nloc_warn_threshold` | `400` (`0` disables) |
| `$IN_PROGRESS_LABEL` | `[status_labels].in_progress` | required when `$SYSTEM = github` |

**Tracking dirs.** Resolve `$TRACKING_DIR` and `$ARCHIVE_DIR` **together**, first match
wins: (1) explicit `tracking_dir` / `archive_dir`, verbatim, each key independent;
(2) `.slopstop/` at the main worktree root — checked as
`ROOT="$(dirname "$(git rev-parse --git-common-dir)")"; [ -d "$ROOT/.slopstop" ]`, never
against cwd — giving `.slopstop/ticket-active` and `.slopstop/ticket-archive`; (3)
`~/.claude/ticket-active` and `~/.claude/ticket-archive`. Relative paths resolve from the
main worktree root. Warn if a resolved path lands under `~/.claude/`: it is protected, and a
subagent's `Write` refuses it even with a matching `--add-dir`. You are the only writer, so
no worker ever resolves these.

## The state machine

State lives in each ticket's `run.jsonl` at `$TRACKING_DIR/<TICKET>/run.jsonl`, **not in
your context**. A long multi-ticket run gets compacted; anything you only remembered is
gone. Before acting on a ticket, read its file; after acting, append.

Per ticket, in order. **W** = a worker launch (one `Agent()` per `worker-launch.md`);
**I** = your own inline work, no worker, no fork.

| # | stage | kind | notes |
|---|---|---|---|
| 1 | `intake` | I | fetch the ticket, its five sections and its **DoD**; seed `$TRACKING_DIR/<TICKET>/` with `task_plan.md` + `findings.md` and open `run.jsonl` |
| 2 | `investigate` | W | returns findings + the **predicted file map**. Run for all N tickets before anything else — see Scheduling |
| 3 | `branch` | I | label/state → in progress; `git switch -c <type>/<TICKET> $ORIGIN_REMOTE/$BASE_BRANCH`, `<type>` per `references/branch-type.md`. Record `$BASE` = the branch point sha |
| 4 | `red-tests` | W | returns test files, node-ids, `--command`, stub paths, observed failure output |
| 5 | `mutation-check` | W | `--tests --node-ids --command --targets --stubs` from stage 4 |
| 6 | `phase0-commit` | I | commit the red tests + stubs. **Capture `$FROZEN` here** |
| 7 | `adversary` | W+I | the loop, the add/skip decision, gap-test authoring, RED re-verify, gap commit — all yours |
| 8 | `implement` | W | the ticket, the plan, the failing tests. It may not touch the tests |
| 9 | `gates` | W×3 | `slop-check`, `vacuity-check`, `complexity-check` — launch together, they are independent |
| 10 | `review` | W | loop until `REVIEW CLEAN`, cap 5 rounds |
| 11 | `pr` | I | commit, push to `$PR_REMOTE`, open the PR against `$OWNER/$REPO` |
| 12 | `bot-read` | I | read existing bot comments **once**. Never poll |
| 13 | `merge` | I | serial across tickets; `gh pr merge --merge --delete-branch` |
| 14 | `close` | I | advance the ticket state / swap labels, push docs to the ticket |
| 15 | `archive` | I | `mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>` |

Stage 4 has one legitimate empty outcome: `PHASE 0: none — prose-only change`. Then stages
5–7 are skipped, `$FROZEN` is absent, and every consumer of `$FROZEN` is told so explicitly
rather than being handed a guess.

Prose that names a stage in `run.jsonl` uses **exactly these `stage` values**, so one pass
over the file reconstructs the run.

## Scheduling across tickets (PRD D14)

1. **Fan out `investigate` for all N tickets first.** It is read-only, so it is always safe
   and always parallel. Collect each ticket's predicted file map.
2. **Schedule by overlap.** Tickets whose predicted file maps are disjoint run stages 3–12
   concurrently. Overlapping ones run serially, later ones starting from the updated tip.
   Prediction is never perfect; this buys efficiency, not correctness.
3. **Merge serially, always** — regardless of overlap. One PR at a time.
   On conflict: `git merge master` (i.e. `$BASE_BRANCH`) **into the losing branch**, resolve,
   re-run that ticket's test command, push, merge. **Never rebase.** A rebase of a pushed
   branch needs `git push --force`, which universal §3 forbids.

One ticket ⇄ one branch ⇄ one PR. Never bundle two tickets onto a branch, and never branch
off another ticket's branch.

## Stage 7 — the adversary loop, and everything around it

The `adversary` worker does **one round and returns**. It cannot write, commit, or prompt.
The loop and all the machinery below are yours; this is the largest thing you own.

**Launch** with `--target <the phase-0 test files> --goals <the ticket body + its DoD>
--caliber <the families relevant to a test suite> --round <n>` and, from round 2,
`--prior <the previous round's findings>`.

**Branch on its verdict line, which is not prose:**

- `ADVERSARY PASS` → advance to stage 8.
- `ADVERSARY FAIL: n` → work the findings, then run another round.
- `ADVERSARY GOAL DEFECT` → the ticket itself is wrong. Stop this ticket and take it to the
  human; do not fix the ticket by editing a test.

**Cap at 3 rounds.** A `FAIL` still standing at the cap goes to a human — bracket that as a
`waiting_for_user` span — with the round-3 findings quoted. Never loop a fourth time and
never declare pass by fatigue.

**The add decision is yours.** Present the numbered findings and ask
`add all / add selected <1,3,…> / skip`. Under `[autonomous]`, `on_test_gaps` answers it.

**Argue, don't ignore.** A finding you disagree with is rebutted **in the correction note
you send into the next round**, with the reason. Silently dropping a finding is the failure
mode this rule exists to stop — it looks identical to fixing it.

**A gap test naming surface that does not exist yet gets a stub**, exactly like stage 4's:
a minimal non-satisfying sentinel that lets the test reach its assertion instead of failing
to collect. Stubs are not frozen.

**Re-verify RED after adding gap tests.** Run the stage-4 test command. Every added gap test
must fail on current code. One that passes goes to the human as `revise / continue / abort`
— it is not evidence of a covered case until someone says so.

**Then commit, explicitly by path:**

```
git commit -m "[$TICKET] Phase 0: adversary gap tests — <N> cases added" \
           -m "Gap tests identified by adversary review. Fail on current code." \
           -m "Co-Authored-By: Claude <model> using slopstop <noreply@anthropic.com>"
```

Stage only the gap-test files and their stubs. Never `git add -A` here.

**If the worker is unavailable**, that is a caller decision: work the attack families
yourself inline, take the same add/skip decision, and say in the report that it was inline.

## `$FROZEN` — capture it once, thread it everywhere

**At the moment you make the stage-6 commit**, `$FROZEN = git rev-parse HEAD`. That is the
only moment it is unambiguous. **Recovering it later by scanning history is forbidden** —
`git log | grep 'Phase 0' | tail -1` is exactly the derivation every worker is banned from,
and it is wrong on any branch carrying two such commits (the gap-test commit is a second).

`$FROZEN` goes to `slop-check`, `review`, and `vacuity-check`. `$BASE` — the branch point, a
different value with a different name — goes to `vacuity-check` and `complexity-check`. Two
concepts, two names, no synonyms, no swapping.

## Stage 9 — the three gates

Launch all three together; they do not depend on each other.

- `slop-check --scope <ref-range-or-PR> --ticket <the ticket's stated scope> --frozen $FROZEN`
- `vacuity-check --base $BASE --frozen $FROZEN --node-ids <from stage 4+7> --test-files <…>
  --stubs <…> --command <…>`
- `complexity-check --base $BASE --repo <root> --warn $CC_WARN --reject $CC_REJECT
  --exempt-pre-existing $CC_EXEMPT --file-nloc-warn $FILE_NLOC_WARN`

`complexity-check` **blocks** if you omit a threshold; it does not read config and does not
carry a default. You resolved them, so you pass them.

A 🔴 from `slop-check`, a `vacuity`-verdict of `vacuous`, or a `VIOLATIONS` at the reject
threshold **stops this ticket** and goes to the human. A warn-level breach is reported and
proceeds. `SKIPPED` / `BLOCKED` / `could-not-determine` are reported as themselves — never
rounded to a pass.

## Stage 10 — review

```
$ROUND = 1
loop:
  Agent(... prompt: invoke slopstop:review with
        "--scope <PR-or-ref-range> --mode <autonomous|interactive> --frozen $FROZEN")

  REVIEW CLEAN         -> converged, go to stage 11
  REVIEW APPLIED: <n>  -> commit and push this round's fixes, then continue
  REVIEW BLOCKED: <r>  -> stop this ticket, surface <r>, do not retry
  anything else        -> stop, surface the raw verdict verbatim; never assume it applied

  if $ROUND >= 5       -> capped: report the LAST round's findings and stop this ticket
  $ROUND += 1
```

**Commit before the cap check.** The worker applies with `Edit` and hands nothing back, so a
cap that fires first strands round 5's fixes uncommitted. Each round is a fresh worker, so
round N+1 cannot rationalise round N's edits. Record which exit was taken.

## Stage 12 — bot reviews are read once, never polled

Universal §9: *read it if it is already there, never wait for it.* There is no poll. Read the
PR's existing bot comments once, inline, and sort what you find three ways:

- **A real review** — verify each finding against the actual code, apply the ones that
  survive, and state which you refuted and why.
- **A non-review notice** (`Review limit reached`, or `auto reviews are disabled` when the
  base is not the default branch) — **not a clean pass**, and not a reason to wait.
- **Silence.** Same action as the notice: proceed on the `review` worker's verdict.

Never post `@coderabbitai review` to force one. `$PR_BACKEND` selects whose comments to look
for, nothing more.

## Stages 13–15 — landing a ticket

Serial across tickets, and all of it inline.

1. `gh pr merge --merge --delete-branch` against `$OWNER/$REPO`. **Never** `--squash`,
   `--rebase`, or `--admin`. Read the PR back and assert `state == "MERGED"` before believing
   it; capture `$MERGE_COMMIT`.
2. **Score the DoD** before advancing anything. `unverifiable` is not a polite `met` — any
   `not-met` or `unverifiable` blocks and goes to the human. The scoring rules are one
   definition and live in `references/`, not here:
   → Read `~/.claude/commands/slopstop-run-refs/dod-scoring.md`
3. Advance the ticket **one state** (or, for GitHub, close it and swap
   `$IN_PROGRESS_LABEL` for the done label). Closure happens here, through the API. Never
   write `Closes #N` in a PR body — GitHub would auto-close and silently skip the label half
   of this step.
4. **Push docs to the ticket**: the task plan into the description, a DoD-confirmation
   comment with per-item verdicts and evidence, and a findings comment. Best-effort — a
   failed doc push never rolls back a merge.
5. `mkdir -p $ARCHIVE_DIR && mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>`. If the
   destination exists, rename to `<TICKET>-<timestamp>`; never lose history. `run.jsonl`
   travels with the directory, which is why an archived ticket carries its own timing.

## Human waits — bracket every one

Whenever you block on the user — the adversary add decision, the round-3 escalation, a gap
test that came up green, a 🔴 gate, a DoD item that is not `met`, a merge conflict you want
confirmed — write the `waiting_for_user` `started` line **in the step that asks** and the
`finished` line **in the step that receives the answer**.

You are the thing doing the blocking, so you are the only thing that can record it. This is
the whole mechanism separating machine time from a weekend, and a stamp deferred to
"afterwards" is a stamp that never happens.

## Resuming

A run resumes from disk, never from memory.

1. For each ticket, read `$TRACKING_DIR/<TICKET>/run.jsonl` (or `$ARCHIVE_DIR/` — an
   archived ticket is finished).
2. **Validate it** against the invariants in `run-jsonl.md` — every `started` closed
   exactly once, no orphan close, every line parsing with an `at`.
3. On failure: name the unclosed spans and stop. **Report no timing numbers at all.** A
   broken record must not be able to produce a plausible-looking summary.
4. Append a `session_resume` note — it bounds the gap that no `waiting_for_user` span covers
   because the session was dead, not waiting.
5. Continue from the last **closed** span. A `started` with no close means that stage was
   interrupted: re-run it from the beginning rather than assuming its result.

At run end, validate again before reporting anything, then append the final
`{"event":"note","stage":"run_closed",…}` line. Its absence is what tells a later reader the
orchestrator died mid-run.

## Failure handling

A ticket that stops — `GOAL DEFECT`, a 🔴 gate, `REVIEW BLOCKED`, a capped review loop, a
blocked DoD — is closed in `run.jsonl` with `failed` and its reason, and **every independent
ticket keeps running**. One stuck ticket never stalls the run. Report all stopped tickets
together at the end, with what each needs from the human.

Never resolve a stop by weakening the thing that raised it: no deleting a test, no narrowing
an assertion, no `Skip()`, no editing a frozen expectation. If the ticket's own expectation
is wrong, that is a `GOAL DEFECT` for a human, not an edit.

## Rules

- **One writer.** You write `run.jsonl`; no worker does, and no worker resolves a tracking
  dir. A worker that needs something persisted returns it and you write it.
- **One reader.** You read `.project-conf.toml`; no worker does.
- **One launch form.** Every worker goes through the `Agent()` form in `worker-launch.md`.
  No headless `claude -p`, no worktree flags, no per-worker prompt templates.
- Adversarial and checking work runs **one tier above** the work it checks. Resolve it from
  `[stage_tiers]`; never flatten it.
- Never `git push --force`, `git reset --hard`, `git commit --no-verify`, or
  `gh pr merge --admin`. Never rebase a pushed branch. Never squash- or rebase-merge.
- Commits anchored to a ticket carry `[<TICKET>]` in the subject and a `Refs:`/`Closes:`
  trailer — provenance only, not a GitHub closing keyword.
- Never use `open` to display a file.
