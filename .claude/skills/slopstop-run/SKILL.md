---
description: The single lifecycle entry point — take one or more tickets and drive each through its whole lifecycle (investigate, red tests, adversary, implement, gates, review, PR, merge, archive), interleaving them, launching workers for judgment work and doing every mechanical step inline. Invoke as /slopstop-run <TICKET> [TICKET...].
disable-model-invocation: true
---

<!-- GENERATED from slopstop 15de822-dirty by install-for-project.sh — do not edit.
     Edit skills/run/ in the slopstop repo and re-run. (universal §5) -->

# /slopstop-run

You are the **orchestrator**. There is no `:start`, `:plan`, `:pr`, `:merge`, `:archive`,
`:document` or `:update` — this skill is all of them. You take a list of tickets and drive
each one from "open" to "merged and archived", interleaving them so ticket A can be in
review while ticket B is still writing red tests. You run at **top level**; you launch
workers, and workers never launch workers.

## Read these two first — they are contracts, not background

- `.claude/skills/slopstop-run/references/worker-launch.md` — the one `Agent()` launch form, stage → tier →
  model resolution, the eleven-worker roster with each worker's arguments and return, and
  the data-flow diagram of what you must thread between them.
- `.claude/skills/slopstop-run/references/run-jsonl.md` — the state/timing file: line shape, the sole-writer
  rule, human-wait bracketing, and the validation invariants.

**Do not restate either here or in your own output.** One definition each (universal §5).
Every launch and every span below assumes you have read them.

## Arguments

`$TICKETS` — one or more ticket keys (`BILL-501 BILL-502`). Empty → ask; never guess a
ticket list from the branch or the backlog. Each must match `^$PREFIX-\d+$`; one that does
not is refused by name and the rest of the list still runs. `--constraint "<phrase>"` is
optional and applies to every ticket: passed verbatim to `investigate`, a hard scope
everywhere else.

`--interactive` — stop at every gate and ask. **Without it you run autonomously**, which is
the default because `:run` exists to drive N tickets unattended.

> **`--interactive` is specified but not built.** The table below is the spec for it; the
> ask-and-wait paths have not been implemented or exercised. Treat the autonomous column as
> what actually runs today, and do not report an interactive run as having gated on a human.

Set `$MODE` from it once, at the top: `interactive` when the flag is present, `autonomous`
otherwise. It is passed to the `review` worker, which applies fixes autonomously and
reports them for a human interactively. **No other worker takes a mode** — the rest are
leaves that return a result and never interact with anyone, so a mode would be a parameter
they could only ignore.

## Mode — autonomous by default

There is **one** switch, and it is this flag. There is no `[autonomous]` master switch and
no per-gate `on_*` config; those seven knobs were deleted 2026-08-06. They existed because
seven separate skills each needed their own policy at their own gate — one orchestrator has
one decision point.

| | autonomous (default) | `--interactive` |
|---|---|---|
| adversary gap tests | add all | ask `add all / add selected <n,…> / skip` |
| gap test that comes up green | stop the ticket | ask `revise / continue / abort` |
| adversary still `FAIL` at round 3 | stop the ticket | present findings, ask |
| `GOAL DEFECT` | stop the ticket | present verbatim, ask |
| DoD item `not-met` / `unverifiable` | stop the ticket | present, ask |
| 🔴 CC breach | stop the ticket | present, ask |
| merge conflict | `git merge master`, resolve, re-run tests | same, then confirm |

**A ticket that fails implementation twice may be a ticket defect, not a code defect.** Say
so when you stop it: recommend `/slopstop-tickets --rewrite <TICKET>`, which captures the
outgoing body, re-drafts against the specific failure, and runs a mandatory
`scope-subtraction` delta check before the ticket system sees anything. You do not rewrite
tickets yourself — authoring is `:tickets`' work.

**"Stop the ticket" is not "wait".** Close its current span `failed`, leave its branch and
tracking dir intact, keep every other ticket running, and report the whole stopped set at
the end with what each needs. A stalled autonomous run is the failure mode this default
exists to avoid.

### Mechanical gates never soften, in either mode

A **judgment** gate may be waved past by a human who has read it. A **mechanical** gate —
red-test tamper, vacuity, slop findings — may not, and has no permissive setting in either
mode: it stops the ticket, always.

This is the rule the deleted `[autonomous]` block stated about itself, kept as behavior now
that the knobs are gone: *any knob whose permissive value is the only fleet-viable one
silently disables its gate for exactly the agents it exists to police.* An unattended run
that waves past the anti-tamper gate is worse than having no gate, because it reports clean.

## Project scope — you are the sole reader of the resolved configuration

Configuration resolves in **three sets**: documented defaults, then `.project-conf.toml`,
then a gitignored `.project-conf-local.toml` beside it. Overrides apply **per leaf key**,
not per table. Report the source file of every non-default value.
→ Read `.claude/skills/slopstop-run/references/config-resolution.md`

Read the tracked file from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Missing from both → stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop-gh-init or create the file
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
| `$CC_WARN` | `[complexity].cc_warn_threshold` | `5` |
| `$CC_REJECT` | `[complexity].cc_reject_threshold` | `10` |
| `$CC_EXEMPT` | `[complexity].cc_exempt_pre_existing` | `false` |
| `$FILE_NLOC_WARN` | `[complexity].file_nloc_warn_threshold` | `400` (`0` disables) |
| `$IN_PROGRESS_LABEL` | `[status_labels].in_progress` | required when `$SYSTEM = github` |
| `$POST_MERGE_DONE` | `[workflow].post_merge_done` | `true` |

**Tracking dirs.** Resolve `$TRACKING_DIR` and `$ARCHIVE_DIR` **together** — they are a
pair, and resolving one while the other falls to a different tier is the bug that
definition exists to prevent. **You are the only resolver**; no worker ever touches it.
→ Read `.claude/skills/slopstop-run/references/tracking-dir-resolution.md`

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
| 3 | `branch` | I | label/state → in progress; `git switch -c <type>/<TICKET> $ORIGIN_REMOTE/$BASE_BRANCH`, `<type>` per `.claude/skills/slopstop-run/references/branch-type.md`. Record `$BASE` = the branch point sha |
| 4 | `red-tests` | W | returns test files, node-ids, `--command`, stub paths, observed failure output |
| 5 | `mutation-check` | W | `--tests --node-ids --command --targets --stubs` from stage 4 |
| 6 | `phase0-commit` | I | commit the red tests + stubs. **Capture `$FROZEN` here** |
| 7 | `adversary` | W+I | the loop, the add/skip decision, gap-test authoring, RED re-verify, gap commit — all yours. **One span per round**, never one span per loop |
| 8 | `implement` | W | the ticket, the plan, the failing tests. It may not touch the tests |
| 8a | `tamper` | I | **mechanical, yours, before any checker is spawned**: the tamper diff against `$FROZEN` and the file-map violation check against `$BASE`. A FAIL stops the ticket here — no worker is bought |
| 9 | `gates` | W×3 | `slop-check`, `vacuity-check`, `complexity-check` — launch together, they are independent. **After `implement`, deliberately**: the adversary's false-negative vector at stage 7 cannot see tests written later, and `vacuity-check` here is what covers them (BILL-343) |
| 10 | `review` | W | loop until `REVIEW CLEAN`, cap 5 rounds |
| 10a | `size` | I | once the diff exists: `git diff --numstat "$BASE"..HEAD`, then record **one entry per file** (path, added, removed, kind) plus the aggregates, the `test_globs` you classified by, and the provisional `tier` computed from **production counts**. **Nothing reads it** — it is the data that will later decide what is safe to skip |
| 10b | `handoff` | W×2 | a **fresh** requirements adversary and code reviewer at the tier above, fed artifacts only — never the agent's comments or the PR description. Produces a blessing bound to the **branch tip SHA** |
| 11 | `pr` | I | commit, push to `$PR_REMOTE`, open the PR against `$OWNER/$REPO` |
| 12 | `bot-read` | I | read existing bot comments **once**. Never poll |
| 13 | `merge` | I | serial across tickets; `gh pr merge --merge --delete-branch` |
| 14 | `close` | I | score the DoD, advance the ticket state / swap labels, write the DoD confirmation into `task_plan.md` |
| 15 | `archive` | W+I | launch the `archive` worker (one comment per tracking file), close the log, then `mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>` |

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

**Bracket every round separately** — `started` when you launch that round, `finished` or
`failed` when its verdict returns, each carrying its `round` number. Never one span opened
at round 1 and closed at round 3: GAST-8 did that and recorded 1050 seconds as one lump for
three rounds, on what was the most expensive stage in the run. A round that is capped,
escalated, or human-authorized past the cap is still its own span.

**Cap at 3 rounds.** A `FAIL` still standing at the cap goes to a human — bracket that as a
`waiting_for_user` span — with the round-3 findings quoted. Never loop a fourth time and
never declare pass by fatigue.

**The add decision is yours.** Present the numbered findings and ask
`add all / add selected <1,3,…> / skip` — but only under `--interactive`. Autonomously,
add all: a gap the adversary found is a gap.

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

## Stages 8a and 10b — handoff verification

**You do this, not a worker.** The `implement` worker's report is the *subject* of the
check, never its evidence. The full contract — the baseline resolution, the two variable
guards, the frozen-set diff, the file-map commands, the two fresh agents and the
SHA-bound blessing — is one definition and lives in `references/`, not here:

→ Read `.claude/skills/slopstop-run/references/handoff-verification.md`

Three things govern the shape and are worth having in front of you before you read it:

- **8a is mechanical and runs first.** A `TAMPER FAIL` or `FILEMAP FAIL` stops the ticket
  *before stage 9 launches anything*. A green suite is not evidence when the agent had write
  access to the tests, so a checker spent on a branch a diff already condemns is wasted.
- **`TAMPER BLOCKED` is not `TAMPER CLEAN`.** Both guards in that file — an unset `$FROZEN`
  and an empty frozen file set — fail *toward looking clean*. Assert them before diffing.
- **10b is fed artifacts only.** Not `implement`'s report, not the PR description, and not
  your own summary of what the run did. Your summary is still a narrative.

Bracket 8a as an inline span and each 10b launch as its own span, and write each verdict
line into `run.jsonl` verbatim.

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
  Agent(... prompt: invoke slopstop-review with
        "--scope <PR-or-ref-range> --mode $MODE --frozen $FROZEN")

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

0. **Re-check the blessing before merging.** `git rev-parse <branch>` against the
   `blessed_sha` recorded at stage 10b. If the tip has advanced — stage 10 committed review
   fixes, stage 12 applied a bot finding, a salvage landed — **the blessing is void**: go
   back to stage 10b and re-verify on the new tip. Do not merge on a blessing taken before
   commits that are now in the diff. A blessing is a statement about a commit, not about a
   ticket.
1. `gh pr merge --merge --delete-branch` against `$OWNER/$REPO`. **Never** `--squash`,
   `--rebase`, or `--admin`. Read the PR back and assert `state == "MERGED"` before believing
   it; capture `$MERGE_COMMIT`.
2. **Score the DoD** before advancing anything. `unverifiable` is not a polite `met` — any
   `not-met` or `unverifiable` blocks and goes to the human. The scoring rules are one
   definition and live in `references/`, not here:
   → Read `.claude/skills/slopstop-run/references/dod-scoring.md`
3. **Advance the ticket, per `$POST_MERGE_DONE`** (`[workflow].post_merge_done`, default
   `true`):

   - **`true`** — take the ticket to its **terminal** state, however many transitions that
     is. For GitHub: close it and swap `$IN_PROGRESS_LABEL` for the done label.
   - **`false`** — advance **exactly one** state and stop there. The ticket is deliberately
     parked, not forgotten: merged code that still needs verification a machine cannot do.
     The motivating case is on-device mobile testing — an Expo/EAS build has to reach real
     hardware, possibly days later, and a human moves the ticket to done once it passes.

   Closure happens here, through the API. Never write `Closes #N` in a PR body — GitHub
   would auto-close, which both skips the label half of this step *and* overrides
   `post_merge_done = false` entirely, terminating a ticket that was meant to wait.

   When you park a ticket, say so in the final report under its own heading — `parked
   awaiting <state>` — never folded in with the completed ones. A parked ticket looks
   identical to a forgotten one unless the report distinguishes them, and the whole point
   of the flag is that someone comes back to it later.
4. **Write the DoD-confirmation into `task_plan.md`** — per-item verdicts and their
   evidence — so it is a file in the tracking dir like everything else. Do not push it
   yourself; step 5's worker pushes the whole directory.
5. **Launch the `archive` worker** (`--ticket --dir --system` + backend coords). It posts
   one comment per tracking file — task plan, findings, `run.jsonl`, any adversary rounds —
   so the local record survives where the ticket lives. Bracket the span like any other
   launch. Best-effort: `ARCHIVE PARTIAL` or `BLOCKED` is reported and never rolls back a
   merge, and a re-run converges because the worker edits comments it already posted.
6. Close the `archive` span, then append `run_closed`. **In that order** — the worker read
   `run.jsonl` before either line existed, so the pushed copy omits them by construction and
   says so in its own comment. Do not try to make the two copies match.
7. `mkdir -p $ARCHIVE_DIR && mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>`. **The move is
   yours, not the worker's** — it runs last, after the log is closed, because moving a
   directory out from under an open span loses the lines still being written to it. If the
   destination exists, rename to `<TICKET>-<timestamp>`; never lose history. `run.jsonl`
   travels with the directory, so the archived copy is the complete one.

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

A ticket that stops — `GOAL DEFECT`, a 🔴 gate, `TAMPER FAIL`, `FILEMAP FAIL`,
`HANDOFF FAIL`, `REVIEW BLOCKED`, a capped review loop, a blocked DoD — is closed in
`run.jsonl` with `failed` and its reason, and **every independent ticket keeps running**.
One stuck ticket never stalls the run. Report all stopped tickets together at the end, with
what each needs from the human.

**A stopped ticket preserves everything and yields findings, not nothing.** The branch, its
commits, its worktree where one exists, the tracking dir, and the findings verbatim — plus
what a retry, a rewrite, and a human-authorized salvage each do with them. One definition,
in `references/`:

→ Read `.claude/skills/slopstop-run/references/failure-and-salvage.md`

The two rules from it you must not get wrong here: **never clean up on a failure** — no
branch delete, no `git reset`, no worktree removal — and **a retry carries the prior
findings verbatim**, because a retry without new information is a wasted attempt.

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
