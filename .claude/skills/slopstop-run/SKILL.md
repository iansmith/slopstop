---
description: The single lifecycle entry point — take one or more tickets and drive each through its whole lifecycle (investigate, red tests, adversary, implement, gates, review, PR, merge, archive), interleaving them, launching workers for judgment work and doing every mechanical step inline. Invoke as /slopstop-run <TICKET> [TICKET...].
disable-model-invocation: true
---

<!-- GENERATED from slopstop 5e7713f-dirty by install-for-project.sh — do not edit.
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
red-test tamper, vacuity, slop findings, and (in backfill mode) `mutation-check`'s
`not-pinned` — may not, and has no permissive setting in either mode: it stops the ticket,
always. The invariant modes' own mechanical checks are the same: a test file touched in
refactor mode, a production file touched in backfill mode.

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
| `$CC_EXEMPT` | `[complexity].cc_exempt_pre_existing` | `true` |
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
| 1 | `intake` | I | fetch the ticket, its five sections and its **DoD**; set `$REFACTOR` / `$BACKFILL` (below); **parse `Blocked by:`** (see Scheduling); seed `$TRACKING_DIR/<TICKET>/` with `task_plan.md` + `findings.md` and open `run.jsonl` |
| 2 | `investigate` | W | returns findings + the **predicted file map**. Run for all N tickets before anything else — see Scheduling |
| 3 | `branch` | I | label/state → in progress; `git switch -c <type>/<TICKET> $ORIGIN_REMOTE/$BASE_BRANCH`, `<type>` per `.claude/skills/slopstop-run/references/branch-type.md`. Record `$BASE` = the branch point sha |
| 4 | `red-tests` | W | returns test files, node-ids, `--command`, stub paths, observed failure output. `--backfill` when `$BACKFILL` — then it confirms **green**. Not launched when `$REFACTOR` |
| 5 | `mutation-check` | W | `--tests --node-ids --command --targets --stubs` from stage 4. `--backfill` when `$BACKFILL` — then it is **the gate**, not a sanity check, and it **re-runs after stage 7** if stage 7 changed the tests. Not launched when `$REFACTOR` |
| 6 | `phase0-commit` | I | commit the red tests + stubs. **Capture `$FROZEN` here.** Under `$BACKFILL` the commit holds green tests and no stubs — `$FROZEN` is captured the same way and means the same thing |
| 7 | `adversary` | W+I | the loop, the add/skip decision, gap-test authoring, RED re-verify, gap commit — all yours. **One span per round**, never one span per loop |
| 8 | `implement` | W | the ticket, the plan, the failing tests. It may not touch the tests. `--refactor` when `$REFACTOR`. **Not launched when `$BACKFILL`** — the tests are the deliverable and they already pass, so there is nothing to implement |
| 8a | `tamper` | I | **mechanical, yours, before any checker is spawned**: the tamper diff against `$FROZEN` and the file-map violation check against `$OWN`. A FAIL stops the ticket here — no worker is bought. Under `$BACKFILL` the trigger is unchanged and the **resolution** is a mutation re-run, not a judgment — see below |
| 9 | `gates` | W×3 | `slop-check`, `vacuity-check`, `complexity-check` — launch together, they are independent. **After `implement`, deliberately**: the adversary's false-negative vector at stage 7 cannot see tests written later, and `vacuity-check` here is what covers them (BILL-343). W×2 when `$REFACTOR` or `$BACKFILL` |
| 10 | `review` | W | loop until `REVIEW CLEAN`, cap 5 rounds |
| 10a | `size` | I | once the diff exists: `git diff --numstat "$BASE"..HEAD`, then record **one entry per file** (path, added, removed, kind) plus the aggregates, the `test_globs` you classified by, and the provisional `tier` computed from **production counts**. **Nothing reads it** — it is the data that will later decide what is safe to skip |
| 10b | `handoff` | W×2 | a **fresh** requirements adversary and code reviewer at the tier above, fed artifacts only — never the agent's comments or the PR description. Produces a blessing bound to the **branch tip SHA** |
| 11 | `pr` | I | commit, push to `$PR_REMOTE`, open the PR against `$OWNER/$REPO` |
| 12 | `bot-read` | I | read existing bot comments **once**. Never poll |
| 13 | `merge` | I | serial across tickets; `gh pr merge --merge --delete-branch` |
| 14 | `close` | I | score the DoD, advance the ticket state / swap labels, write the DoD confirmation into `task_plan.md` |
| 15 | `archive` | W+I | launch the `archive` worker (one comment per tracking file), close the log, then `mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>` |

Stage 4 has two legitimate empty outcomes: `PHASE 0: none — prose-only change` and
`PHASE 0: none — refactor` (below). In both, stages 5–7 are skipped, `$FROZEN` is absent,
and every consumer of `$FROZEN` is told so explicitly rather than being handed a guess.

Prose that names a stage in `run.jsonl` uses **exactly these `stage` values**, so one pass
over the file reconstructs the run.

## Scheduling across tickets (PRD D14)

1. **Fan out `investigate` for all N tickets first.** It is read-only, so it is always safe
   and always parallel. Collect each ticket's predicted file map.
2. **Explicit relations first — `Blocked by:` is a hard edge.** Below.
3. **Then schedule by overlap.** Among tickets that are *not* blocked, those whose predicted
   file maps are disjoint run stages 3–12 concurrently; overlapping ones run serially, later
   ones starting from the updated tip. Prediction is never perfect; this buys efficiency,
   not correctness.
4. **Merge serially, always** — regardless of overlap. One PR at a time.
   On conflict: `git merge master` (i.e. `$BASE_BRANCH`) **into the losing branch**, resolve,
   re-run that ticket's test command, push, merge. **Never rebase.** A rebase of a pushed
   branch needs `git push --force`, which universal §3 forbids.

**When the explicit relation and the file-affinity heuristic disagree, the explicit relation
wins.** Step 2 runs before step 3 for exactly that reason: overlap is a guess about
efficiency, a `Blocked by:` line is a statement about correctness, and a scheduler that lets
the guess override the statement is wrong in the one case somebody bothered to write down.

One ticket ⇄ one branch ⇄ one PR. Never bundle two tickets onto a branch, and never branch
off another ticket's branch.

### `Blocked by:` — read it, or the dependency does not exist

Every leaf ticket carries `Blocked by:` in its header, per the ticket standard. **Parse it at
intake, for every ticket in the list**, into a set of ticket keys.

The accepted forms are exactly two: the literal `nothing`, or a comma-separated list of keys
matching `^$PREFIX-\d+$`. Trailing prose after the keys is fine and is context for the
reader — `Blocked by: PLTF-2563 — for merge-conflict avoidance only` parses to one key.
Anything with no key in it — prose, a URL, a description of the work — is **unparseable**,
and an unparseable value **holds the ticket** and is reported. Do not guess at prose. A
scheduler that shrugs at `Blocked by: the auth work` and launches anyway has silently
discarded a real dependency, which is the whole failure this section exists to stop.

**A key from another project is a third case, not garbage.** A token matching
`^[A-Za-z][A-Za-z0-9]*-\d+$` whose prefix is not `$PREFIX` — `Blocked by: BILL-471` in a
`PLTF` project — is a **foreign-project blocker**. You cannot resolve it: you hold one
`.project-conf.toml`, one ticket system, one prefix, and nothing here reaches another repo's
backlog. So hold the ticket, and report it as `held (blocked by BILL-471 — foreign project,
not resolvable here)`. Reporting it as unparseable would be actively misleading: the two
need opposite responses from the human — *fix the ticket* versus *go check the other repo
and re-run when it lands*. This is not hypothetical; it is how a cross-repo dependency
actually gets written down.

A missing `Blocked by:` line is a ticket-standard gap: report it, treat it as `nothing`, and
say you did both. Absent and `nothing` mean different things — "nobody wrote it down" versus
"checked, there are none" — and only one of them is a defect.

**A blocker is satisfied when it is MERGED, not when it is done.** Two cases:

- **The blocker is in this run's list.** It is satisfied once *its own* stage 13 merge has
  completed and the PR reads `MERGED`. Not when its gates pass, not when its review is clean —
  a ticket whose code has not landed on the integration branch cannot be built on, and a
  dependent branch cut before that merge forks from a base that never contained the work.
- **The blocker is not in this run's list.** Read its state from the ticket system once, at
  intake. Terminal state → satisfied, proceed. Anything else → **hold**.

**Re-check the blocked set after every merge**, not once at the start. The runnable set grows
as the run proceeds; that is the entire point of accepting a chain in one invocation.

### Holding, and what a hold is not

A held ticket has **not run**. So:

- It consumes no attempt and is not a failure.
- It opens **no span**. Record a `note` naming the ticket and every unsatisfied blocker; the
  ticket's first real span opens when it is released. (A `waiting_for_user` span would be a
  lie — nothing is waiting on a human.)
- If it is never released — its blocker was not in the list and is not merged — the run ends
  cleanly with that ticket untouched. **This is not an error.** A run of three tickets whose
  fourth blocker nobody passed on the command line is the common case, and launching anyway
  is the silent failure.

**Report held tickets under their own heading**, `held (blocked by <key>, not merged)`,
separate from stopped tickets and from `parked awaiting <state>`. Three different states that
look identical in a summary that only counts what finished.

### Cycles stop the run

Before launching anything, check the blocked-by graph over the whole list for a cycle. One
found → **stop the run** and name every ticket in it. Not one ticket: a cycle is a
ticket-authoring defect, and breaking it at an arbitrary entry point hides the defect while
appearing to work. Check for cycles of any length — a two-ticket cycle is caught by a naive
"is my blocker me" test and a three-ticket one is not.

### The native relation is a cross-check, never the source

All three backends have a blocked-by relation of their own — JIRA issue links, Linear
relations, GitHub `issues/{n}/dependencies/blocked_by` (verified 2026-08-07: the endpoint
exists and returns a list). Read it where it is cheap and **compare**.

**The prose line wins.** It is what `:tickets` writes and what you just parsed; the native
relation exists for humans scanning a board. Report any disagreement in both directions —
prose says blocked and the board does not, or the board says blocked and the prose does not —
and say which you acted on. **Never write the native relation**; a second writer is a second
source of truth for a value the ticket body already holds (universal §5).

## Invariant tickets — refactor and backfill

**This is the one definition of all three modes.** Do not restate it in a worker skill or
in `CONFIG.md`; those point here (universal §5).

A normal ticket and an invariant ticket prove themselves by **opposite evidence**. New
behaviour needs a test that fails at base and passes after: *change* is the evidence. An
invariant ticket changes no behaviour at all, so it has no such test to write, and every
stage below assumes the first kind. That is why these need their own path rather than an
exemption from the normal one.

There are **two** invariant modes, and they are exact mirrors of each other:

| | **refactor** | **backfill** |
|---|---|---|
| deliverable | production code | tests |
| may **not** modify | any **test** file | any **production** file |
| evidence | the whole suite: green before, the same green after | **every new test is mutation-proven** |
| `red-tests` | not launched | launched with `--backfill`; confirms **green** |
| `mutation-check` | not launched — no new tests | **the gate**, question inverted |
| `vacuity-check` | not launched — no new tests | not launched — passing at base is the point |
| stage-4 outcome | `PHASE 0: none — refactor` | `PHASE 0: green — backfill` |

The mirror is the design, not a coincidence. Each mode freezes exactly what the other one
delivers, so neither can be used to smuggle in the other's work.

### Detect the mode at intake — match rendered text, never markup

A ticket cut by `/slopstop-tickets --refactor` or `--backfill` carries one of:

```
**Mode:** refactor — invariant DoD (nothing broke)
**Mode:** backfill — tests over existing behaviour
```

**The asterisks are presentation. Do not match them.** The marker's meaning is *"a line that
says `Mode:` followed by a mode name"*, and that is what you match — because not every
backend stores markdown. GitHub Issues returns raw markdown and the asterisks survive; JIRA
stores ADF, where a body authored with bold renders as bold and the asterisks are simply
**gone**. Both were measured 2026-08-07, and matching the markdown literal silently failed on
two of the first two markers written through the normal path.

**Normalize, then match, per line:**

1. Strip surrounding whitespace.
2. Strip markdown emphasis runs — `*`, `_`, backtick — from the line's start and end, and
   from around the `Mode:` token.
3. A **marker line** is one matching `^Mode:\s*(refactor|backfill)\b` after that.

All of these resolve identically, which is the whole point:

```
**Mode:** refactor — invariant DoD (nothing broke)     Mode: refactor
*Mode:* refactor          __Mode:__ refactor           **Mode: refactor**
```

**Anchor to the start of a line. Never substring-search the body.** Tickets carry prose
*about* their own markers — a note explaining why a marker is written a certain way — and a
substring search reads that as a second marker. Line-anchoring is the only thing separating
a declaration from a discussion of one.

> **Precondition: whatever converts the backend's body to text must emit a line break per
> block.** Line-anchoring is meaningless otherwise. A rich-text document is a *tree of
> blocks*, not a string — a flattener that concatenates text nodes without separators turns
> `…(nothing broke)` + `Why` into `…(nothing broke)Why`, and every marker after the first
> block loses its line start. Measured 2026-08-07 on a live ticket whose marker sits at block
> 2: with block newlines it resolved `refactor`, without them it resolved **`normal`** —
> silently, which is the failure shape this whole ticket exists to remove. When you flatten
> ADF or any block document, append `\n` for every `paragraph`, `heading`, `listItem`,
> `codeBlock`, `blockquote` and table row. If you cannot control the flattener, verify a
> marker that is *not* the first block before trusting the result.

Then **count**, rather than taking the first hit:

| marker lines found | result |
|---|---|
| none | normal ticket |
| exactly one | that mode |
| two or more, **same** mode | that mode — and report the duplication |
| two or more, **different** modes | **malformed: stop the ticket**, naming both |

A ticket claiming both modes can change nothing at all: refactor freezes every test file,
backfill freezes every production file, and together they freeze the repository. That is a
ticket-authoring defect, not a mode to resolve.

Set `$REFACTOR` or `$BACKFILL` once, at intake, and record it as a `note` **with the marker
line you matched, verbatim** — so a later reader can see what the mode was decided from
rather than taking your word for it.

**Never infer a mode** from the title, the file map, or how the diff turns out. A mode
inferred after the fact is a mode an implementer can talk you into.

> **Linear's storage format is not verified.** GitHub (markdown) and JIRA (ADF) were
> measured; Linear was not. The normalization above is designed so the answer does not
> matter — but if you are the first to run this against Linear, check and record it rather
> than assuming this note is still current.

### `$OWN` — what THIS branch changed, derived at check time

Both invariant-mode checks below, and the file-map check in `handoff-verification.md`, ask
one question: **which files did this branch change?** `$BASE` is not the answer to it.

`$BASE` is the fork point, captured once at stage 3. It stops meaning "everything since here
is mine" the moment the branch carries the integration branch in — which `:run`'s own conflict
rule tells you to do (*"On conflict: `git merge master` into the losing branch"*). After that,
`git diff "$BASE"..HEAD` reports everything **master** gained since the fork as though this
branch had written it. Measured: a refactor branch that touched one production file reported
another ticket's test file, and would have stopped itself as tamper for it.

**Derive the comparison point instead, every time you check:**

```bash
OWN="$ORIGIN_REMOTE/$BASE_BRANCH...HEAD"                       # comparing two commits
FORK=$(git merge-base "$ORIGIN_REMOTE/$BASE_BRANCH" HEAD)      # comparing against the working tree
```

> **`"$BASE...HEAD"` is not the fix, and it is worth knowing why before you try it.**
> `git diff A...B` means `merge-base(A,B)..B`, and `$BASE` **is** an ancestor of `HEAD` — so
> `merge-base($BASE, HEAD)` is `$BASE` and the three-dot form is byte-identical to the
> two-dot one. The left side has to be the **integration branch**, not the fork point.

On a branch that has merged nothing this is a no-op: `merge-base` returns the fork point and
every check reports exactly what it reported before. It only diverges where it must.

**`$FROZEN` is untouched by all of this.** It is a point *on this branch*, not a fork point,
and the tamper diff is pathspec-limited to the frozen set — which the integration branch does
not contain and cannot pollute. Do not "fix" it to match; that would break the one range a
merge cannot reach.

### Refactor mode — `$REFACTOR`

When `$REFACTOR` is set, five things change and nothing else does:

1. **Stage 4 writes no tests.** Record the outcome `PHASE 0: none — refactor` yourself and
   do not launch `red-tests`; there is no new behaviour to describe. Stages 5–7 are skipped
   with it, exactly as for a prose-only change, and `$FROZEN` is absent.
2. **`implement` is launched with `--refactor`.** Its Step 1.3 full-suite run — which it
   already does before changing anything — becomes the regression baseline **and** the
   guard, so this costs no extra pass.
3. **A red baseline stops the ticket.** For a refactor ticket the Step 1.3 baseline must be
   **fully green**. `implement` returns `IMPLEMENT BLOCKED: refactor baseline not green` with
   the failing tests named; close the span `failed` and report those names. You cannot prove
   you broke nothing against a suite that was already broken, and proceeding would let the
   refactor inherit someone else's failure.
4. **`vacuity-check` is not launched.** There are no new tests to check. Record the verdict
   `VACUITY SKIPPED: refactor ticket — no new tests` yourself, in `run.jsonl` and in the
   report. That is a legitimate skip and it is **not** `BLOCKED` — spell it out, because the
   two look identical in a summary that only counts gates that ran. `slop-check` and
   `complexity-check` run normally.
5. **You check mechanically that no test file was touched**, before reading anybody's
   report:

   ```bash
   git diff --name-only "$OWN" | grep -E '(^|/)(tests?|spec|testdata|__tests__)/|_test\.|\.test\.|_spec\.|conftest\.py$'
   ```

   Any output is a **stop**, naming every path. This is the most likely cheat on this path,
   because the suite is the only thing between the refactor and a merge — so it is checked by
   a diff you run, not by a claim anyone makes.

   **This one expression decides both invariant modes**, and backfill inverts it with `-v`,
   so every gap in it is simultaneously a hole in one mode and a false positive in the other.
   A missing pattern lets a refactor ticket edit tests freely *and* blocks a backfill ticket
   from adding them. Keep it aligned with the `test_globs` list in `run-jsonl.md` — measured
   2026-08-07, the earlier version missed `spec/` at the repo root (it required a leading
   slash), `testdata/`, and `_spec.` files, all three of which `test_globs` already covered.
   Say in the report which expression you used.

***Nothing broke* is all three of: the suite green before, the same suite green after, and
no test file modified.** Not two of three. A suite that is green at both ends because a
failing test was deleted in the middle is green and proves nothing.

### Backfill mode — `$BACKFILL`

Coverage over behaviour that already works. The tests are the deliverable, they pass at
base **by design**, and the question that makes them worth anything is not vacuity's but
mutation's. When `$BACKFILL` is set, five things change and nothing else does:

1. **Stage 4 launches `red-tests --backfill`, which confirms the tests are GREEN.** It
   returns `PHASE 0: green — backfill` with node-ids and the test command. A test that
   comes up **red** here is not a backfill test — it describes behaviour that does not yet
   exist, which means the ticket is a normal ticket in the wrong mode. Stop it and say so;
   do not let it proceed and do not let anyone "fix" the code to make it green.
2. **Stage 5 launches `mutation-check --backfill`, and it is the gate.** It breaks the
   production code each test claims to pin and requires the test to go red. Any node-id
   coming back `not-pinned` **stops the ticket**. This is not an addition to `vacuity-check`
   — it is what replaces it, and it is the only thing standing between a backfill ticket
   and a suite full of tests that assert nothing.
3. **Stage 7's adversary runs normally.** Unlike refactor mode, there *are* new tests here,
   so there is something to attack. Do not skip it.
4. **`vacuity-check` is not launched.** Its question — *would this have passed at base?* —
   has the answer "yes, that is the point", so it carries no information. Record
   `VACUITY SKIPPED: backfill ticket — tests pass at base by design` yourself, in
   `run.jsonl` and in the report. A legitimate skip, **not** `BLOCKED`, and worded
   differently from refactor mode's so a summary cannot conflate them.
5. **You check mechanically that no production file was touched**, before reading anybody's
   report — the exact mirror of refactor mode's check:

   ```bash
   git diff --name-only "$OWN" | grep -vE '(^|/)(tests?|spec|testdata|__tests__)/|_test\.|\.test\.|_spec\.|conftest\.py$'
   ```

   Note the `-v`. Any output is a **stop**, naming every path. This is what keeps backfill
   from becoming a way to ship behaviour without a red test, and it is checked by a diff you
   run rather than by a claim anyone makes.

6. **`mutation-check --backfill` re-runs after stage 7, if stage 7 changed the tests.** It is
   the only gate on this path, it ran at stage 5, and stage 7 is allowed to rewrite what it
   proved — so the stage-5 verdict covers tests that may no longer exist. Re-run it against
   the **committed** files, with the same `--targets`, and **report the re-run as the
   authoritative verdict, with its sha**. Stage 7 changed nothing → no re-run, and say that
   the stage-5 proof stands and why. Two runs with different verdicts and no statement of
   which one counted is how a stale proof ships looking current.

### Stage 8a under `$BACKFILL` — same trigger, mechanical resolution

**Do not skip the tamper diff here.** Under normal mode its named actor is the implementer
who weakened a test so its code would pass; under backfill `implement` is never launched, so
that actor does not exist. A sharper one does:

> `mutation-check` said a test was `not-pinned`, so the test was deleted.

That is the cheapest evasion available on a path where one check decides everything, and it
produces **exactly the same diff as a legitimate rewrite** — collapsing a hand-maintained
enumeration into a structure-driven test removes lines too, and that collapse is what a good
adversary asks for. The gate cannot separate the two, and it should not try.

**So the trigger is unchanged and the resolution is evidence.** A removal inside the frozen
set stops the ticket, and it is cleared by **both** of:

1. **The node-id set did not shrink** across the freeze. Compare the sets, not the line
   counts — a deleted test cannot come back `not-pinned`, so a mutation re-run alone reports
   clean on a contract that got smaller. **A dropped node-id stops the ticket on its own**,
   whatever the mutation verdict says.
2. **`mutation-check --backfill` passes on the current files**, both probe shapes, per the
   re-run above.

Both, or the stop stands. **Never clear it by reading the diff for intent** — that is the
narrative the tamper rule exists to refuse, and here it would be written by the session that
made the change.

**Neither mode is a way to skip tests-first.** Both are for changes that provably do not
alter behaviour. A ticket that changes behaviour is a normal ticket however much
restructuring or coverage it also carries — and for the refactor case it is the CC exemption
(`cc_exempt_pre_existing`, on by default), not this mode, that keeps such a ticket from
being forced to mix the two.

**A ticket that needs both is two tickets.** Production change plus new coverage is the
normal path, which already handles it: write the red test, make it green. Reaching for an
invariant mode there means one half of the work is going unverified.

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
- `complexity-check --base $FORK --repo <root> --warn $CC_WARN --reject $CC_REJECT
  --exempt-pre-existing $CC_EXEMPT --file-nloc-warn $FILE_NLOC_WARN`

**Pass `$FORK`, not `$BASE`** — the derived point from the `$OWN` section, not the recorded
fork sha. On a branch that has merged the integration branch in they differ, and the stale
one makes `complexity-check` measure the integration branch's files and blame this branch for
complexity somebody else added. The worker cannot correct this itself: it does not read
`.project-conf.toml`, so it has no way to name the integration branch, and the `merge-base`
it *could* run against `$BASE` is a no-op. This is yours.

`complexity-check` **blocks** if you omit a threshold; it does not read config and does not
carry a default. You resolved them, so you pass them.

When `$REFACTOR` is set, launch two: `vacuity-check` is not run and you record
`VACUITY SKIPPED: refactor ticket — no new tests` yourself. `slop-check` is told
`--frozen none --refactor` so it does not read the absent Phase 0 baseline as tampering.

When `$BACKFILL` is set, launch two as well: `vacuity-check` is not run — record
`VACUITY SKIPPED: backfill ticket — tests pass at base by design` — and `slop-check` is told
`--backfill`, which turns a modified production file into a 🔴 and stops its vacuous-test
signal firing on tests that pass at base by design. `$FROZEN` **is** present here (stage 6
committed the green tests), so pass it normally. The gate that carries this mode is
`mutation-check` at stage 5, not anything at stage 9.

A 🔴 from `slop-check`, a `vacuity`-verdict of `vacuous`, or a `VIOLATIONS` at the reject
threshold **stops this ticket** and goes to the human. A warn-level breach is reported and
proceeds. `SKIPPED` / `BLOCKED` / `could-not-determine` are reported as themselves — never
rounded to a pass.

**Carry `complexity-check`'s exempt list into the final report, ranked, with its total.**
It is not a footnote — it is the queue for `/slopstop-tickets --refactor <fn>…`, and it is
the only place the complexity the run declined to block is ever visible. A run that exempts
23 violations and reports `CC CLEAN` with no list has hidden exactly what the exemption was
supposed to make actionable.

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

**A stopped ticket is not a held one.** A stop means the ticket ran and something went
wrong; a hold means it never started because a `Blocked by:` was unsatisfied. They get
separate headings in the report and separate treatment here: a stop consumes an attempt and
leaves a branch, a hold consumes nothing and leaves nothing.
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
