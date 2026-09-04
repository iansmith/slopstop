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

## Read these three first — they are contracts, not background

- `skills/run/references/worker-launch.md` — the one `Agent()` launch form, stage -> tier ->
  model resolution, the eleven-worker roster with each worker's arguments and return, and
  the data-flow diagram of what you must thread between them.
- `skills/run/references/run-jsonl.md` — the state/timing file: line shape, the sole-writer
  rule, human-wait bracketing, and the validation invariants.
- `skills/run/references/user-output.md` — what the user sees and when. **Quiet by default**:
  one phase line per stage, gate stops, errors, and the final summary. Everything else is
  silent unless `--verbose`.

**Do not restate any of them here or in your own output.** One definition each (universal S5).
Every launch and every span below assumes you have read them.

## Arguments

`$TICKETS` — one or more ticket keys (`BILL-501 BILL-502`). Empty -> ask; never guess a
ticket list from the branch or the backlog. Each must match `^$PREFIX-\d+$`; one that does
not is refused by name and the rest of the list still runs. `--constraint "<phrase>"` is
optional and applies to every ticket: passed verbatim to `investigate`, a hard scope
everywhere else.

`--interactive` — stop at every gate and ask. **Without it you run autonomously**, which is
the default because `:run` exists to drive N tickets unattended.

`--verbose` — print full orchestrator output (worker launches, scheduling decisions, finding
text, timing). **Without it, output is quiet**: one phase line per stage, gate stops, errors,
and the final summary. See `skills/run/references/user-output.md`.

> **`--interactive` is specified but not built.** The table below is the spec for it; the
> ask-and-wait paths have not been implemented. Treat the autonomous column as what actually
> runs today.

Set `$MODE` from it once, at the top: `interactive` when the flag is present, `autonomous`
otherwise. Set `$VERBOSE` the same way: `true` when `--verbose` is present, `false` otherwise. It is passed to the `review` worker, which applies fixes autonomously and
reports them for a human interactively. **No other worker takes a mode.**

## Mode — autonomous by default

There is **one** switch, and it is this flag.

| | autonomous (default) | `--interactive` |
|---|---|---|
| adversary gap tests | add all | ask `add all / add selected <n,...> / skip` |
| gap test that comes up green | stop the ticket | ask `revise / continue / abort` |
| adversary still `FAIL` at round 3 | stop the ticket | present findings, ask |
| `GOAL DEFECT` | stop the ticket | present verbatim, ask |
| DoD item `not-met` / `unverifiable` | stop the ticket | present, ask |
| CC breach | stop the ticket | present, ask |
| merge conflict | `git merge master`, resolve, re-run tests | same, then confirm |

**A ticket that fails implementation twice may be a ticket defect, not a code defect.** Say
so when you stop it: recommend `/slopstop:tickets --rewrite <TICKET>`.

**"Stop the ticket" is not "wait".** Close its current span `failed`, leave its branch and
tracking dir intact, keep every other ticket running, and report the whole stopped set at
the end with what each needs.

Stopping needs no span. **A wait does** — see *Human waits — bracket every one* below.

### Mechanical gates never soften, in either mode

A **judgment** gate may be waved past by a human who has read it. A **mechanical** gate —
red-test tamper, vacuity, slop findings, and (in backfill mode) `mutation-check`'s
`not-pinned` — may not: it stops the ticket, always.
Why: an unattended run that waves past the anti-tamper gate is worse than having no gate, because it reports clean.

## Project scope — you are the sole reader of the resolved configuration

Configuration resolves in **three sets**: documented defaults, then `.project-conf.toml`,
then a gitignored `.project-conf-local.toml` beside it. Overrides apply **per leaf key**,
not per table. Report the source file of every non-default value.
-> Read `skills/run/references/config-resolution.md`

Read the tracked file from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Missing from both -> stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file
manually with system + key."`

Resolve, and carry, all of the following. A missing key takes its documented `CONFIG.md`
default; a missing table never errors. **Workers read none of this** — every value reaches
a worker only as an explicit argument.

| value | source | default |
|---|---|---|
| `$PREFIX` | `prefix` | none — stop if absent, malformed, or disagreeing with the tickets |
| `$SYSTEM` | `system` | none — authoritative, never inferred from MCP availability |
| `$OWNER`/`$REPO` | `pr-repo`, else split `key` on `/` | — |
| `$PR_REMOTE` / `$ORIGIN_REMOTE` | `pr-remote` / `origin-remote` | `origin` |
| `$BASE_BRANCH` | `base-branch`, else the repo default branch | — |
| stage models | `[stage_tiers].<stage>` -> `[tiers.<name>]` | per `CONFIG.md` |
| `$PR_BACKEND` | `[pr_review].backend` | `coderabbit` |
| `$CC_WARN` | `[complexity].cc_warn_threshold` | `5` |
| `$CC_REJECT` | `[complexity].cc_reject_threshold` | `10` |
| `$CC_EXEMPT` | `[complexity].cc_exempt_pre_existing` | `true` |
| `$FILE_NLOC_WARN` | `[complexity].file_nloc_warn_threshold` | `400` (`0` disables) |
| `$CC_EXCLUDE_PATHS` | `[complexity].exclude_paths` | `[]` (empty — no filter) |
| `$DUP_MIN_LINES` | `[duplication].min_lines` | `5` |
| `$DUP_EXEMPT` | `[duplication].exempt_pre_existing` | `true` |
| `$DUP_EXCLUDE_PATHS` | `[duplication].exclude_paths` | `[]` (empty — no filter) |
| `$IN_PROGRESS_LABEL` | `[status_labels].in_progress` | required when `$SYSTEM = github` |
| `$POST_MERGE_DONE` | `[workflow].post_merge_done` | `true` |
| `$PUBLISH_ARTIFACTS` | `[workflow].publish_artifacts` | `false` |

**Tracking dirs.** Resolve `$TRACKING_DIR` and `$ARCHIVE_DIR` **together** — they are a
pair, and resolving one while the other falls to a different tier is the bug that
definition exists to prevent. **You are the only resolver**; no worker ever touches it.
-> Read `skills/run/references/tracking-dir-resolution.md`

### Prefix-agreement preflight — before any ticket runs

Once you have the ticket keys, compare each one's prefix against `$PREFIX` **byte for byte
(case included)**, and stop the whole run on a disagreement:

```
RUN BLOCKED: config prefix '<$PREFIX>' does not match ticket keys '<KEY>' — fix
             .project-conf.toml's `prefix`, or the ticket keys, before re-running
```

Why: a case mismatch (`Bill` vs `BILL`) causes the router to return zero totals under the wrong prefix, with no error — unrecoverable after the fact. The check lives here because `:run` is the only thing holding both config and tickets. **Do not normalise the case and continue** — the config might be wrong or the tickets might be, and they need opposite fixes.

## The state machine

State lives in each ticket's `run.jsonl` at `$TRACKING_DIR/<TICKET>/run.jsonl`, **not in
your context**. Before acting on a ticket, read its file; after acting, append.

Per ticket, in order. **W** = a worker launch (one `Agent()` per `worker-launch.md`);
**I** = your own inline work, no worker, no fork.

| # | stage | kind | record | notes |
|---|---|---|---|---|
| 1 | `intake` | I | **note** | fetch the ticket, its five sections and its **DoD**; set `$REFACTOR` / `$BACKFILL` (below) and record it as a **`mode` field** on the note — `normal`/`refactor`/`backfill`, alongside the prose, because stage 10a's basis branches on it and prose is not readable; **parse `Blocked by:`** (see Scheduling); seed `$TRACKING_DIR/<TICKET>/` with `task_plan.md` + `findings.md` and open `run.jsonl` |
| 2 | `investigate` | W | **span** | returns findings + the **predicted file map**. Run for all N tickets before anything else — see Scheduling |
| 3 | `branch` | I | **note** | label/state -> in progress; create the ticket's **worktree and branch** — see `## Worktrees` below. `<type>` per `slopstop-run-refs/branch-type.md`. Record `$WT` = the worktree path and `$BASE` = the branch point sha. **You never `git switch` the main worktree**, at this stage or any other. The stage keeps the `stage` value `branch` — it is a record key, and renaming it would break invariant 6 and orphan every run.jsonl already on disk |
| 4 | `red-tests` | W | **span** | returns test files, node-ids, `--command`, stub paths, observed failure output. `--backfill` when `$BACKFILL` — then it confirms **green**. Not launched when `$REFACTOR` |
| 5 | `mutation-check` | W | **span** | `--tests --node-ids --command --targets --stubs` from stage 4. `--backfill` when `$BACKFILL` — then it is **the gate**, not a sanity check, and it **re-runs after stage 7** if stage 7 changed the tests. Not launched when `$REFACTOR` |
| 6 | `phase0-commit` | I | **note** | commit the red tests + stubs. **Capture `$FROZEN` here.** Under `$BACKFILL` the commit holds green tests and no stubs — `$FROZEN` is captured the same way and means the same thing |
| 7 | `adversary` | W+I | **span** | the loop, the add/skip decision, gap-test authoring, RED re-verify, gap commit — all yours. **Exit immediately on `ADVERSARY PASS`; only FAIL rounds iterate.** Cap FAIL rounds at 3. **One span per round**, never one span per loop |
| 8 | `implement` | W | **span** | the ticket, the plan, the failing tests. **It may add tests; it may never weaken, retarget or remove one** — `skills/implement/SKILL.md` is the definition. Under `--refactor` it may modify no test file at all. `--refactor` when `$REFACTOR`. **Not launched when `$BACKFILL`** — the tests are the deliverable and they already pass |
| 8a | `tamper` | I | **span** | **mechanical, yours, before any checker is spawned**: the tamper diff against `$FROZEN` and the file-map violation check against `$OWN`. A FAIL stops the ticket here — no worker is bought. Under `$BACKFILL` the trigger is unchanged and the **resolution** is a mutation re-run, not a judgment — see below |
| 9 | `gates` | W x 4 parallel, then W x 1-3 | **span** | `slop-check`, `vacuity-check`, `complexity-check`, `duplication-check` — **launch as parallel agents** (all four `Agent()` calls in a single message) on the **READ-ONLY brief** (`worker-launch.md`), detached at `$TIP`. **Await all four**, then proceed to the pinning pass — `mutation-check --implemented` against `$OWN`'s production diff, looping to a cap of 3, one span per round. The pinning pass runs *after* the four, never beside them: it mutates, and a mutating worker never shares a tree. W x 2 when `$REFACTOR` or `$BACKFILL` |
| 10 | `review` | W | **span** | **exit immediately on `REVIEW CLEAN`; only APPLIED rounds iterate.** Cap at 5 rounds |
| 10a | `size` | I | **note** | once the diff exists: `git diff --numstat "$BASE"..HEAD`, then record **one entry per file** (path, added, removed, kind) plus the aggregates, the `test_globs` you classified by, and the provisional `tier` — an **enum**, computed from the counts the ticket's **mode** makes the deliverable (`run-jsonl.md` owns the table; backfill counts tests, not the production side its mode freezes to zero). **Nothing reads it** — it is the data that will later decide what is safe to skip, and `derive.py --check` validates its shape |
| 10b | `handoff` | W x 2 | **span** | a **fresh** requirements adversary and code reviewer at the tier above, **launched SERIALLY — never in parallel** (both mutate production and contaminate each other). Fed artifacts only — never the agent's comments or the PR description. Applied fixes are committed before the round closes, then re-verified on the new tip. Produces a blessing bound to the **branch tip SHA**. **W x 1 for an invariant ticket**: requirements adversary only under `$BACKFILL`, code reviewer only under `$REFACTOR` — see `handoff-verification.md` |
| 11 | `pr` | I | **span** | commit, push to `$PR_REMOTE`, open the PR against `$OWNER/$REPO` |
| 12 | `bot-read` | I | **note** | read existing bot comments **once**. Never poll |
| 13 | `merge` | I | **span** | serial across tickets; `gh pr merge --merge --delete-branch` |
| 14 | `close` | I | **span** | score the DoD, advance the ticket state / swap labels, write the DoD confirmation into `task_plan.md`, then **derive** — `tools/metrics/derive.py`, recorded as a note, never able to fail the run (step 4a) |
| 15 | `archive` | W+I | **span** | launch the `archive` worker (one comment per tracking file), close the log, then `mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>` |

**Stages 7, 10 and 10b do one extra thing when `$PUBLISH_ARTIFACTS` is `true`:** each round's
returned basis is accumulated and published as one live-updating artifact per
`(ticket, stage)`. It changes no worker launch and no verdict — see `## Publishing a review
primitive's basis` below. Off by default, and off entirely when the key is absent.

Stage 4 has two legitimate empty outcomes: `PHASE 0: none — prose-only change` and
`PHASE 0: none — refactor` (below). In both, stages 5-7 are skipped, `$FROZEN` is absent,
and every consumer of `$FROZEN` is told so explicitly rather than being handed a guess.

Prose that names a stage in `run.jsonl` uses **exactly these `stage` values**, so one pass
over the file reconstructs the run.

## Worktrees — where concurrent work physically happens

**Every ticket gets its own worktree, unconditionally — including a single ticket.**
Why: isolation is the execution environment, not an optimisation. A `git switch` between tickets mid-flight interleaves edits into whichever branch is checked out — both PRs look plausible and both diffs are wrong. A conditional rule is one an orchestrator can reason its way out of. The second half of the process needs it for `SALVAGE` and `DROP`.

### The orchestrator creates none of them

**You never run a worktree command to make one.** Each worker is launched with
`isolation: "worktree"`, which puts it in a fresh worktree under `.claude/worktrees/` and pins
it there. The launch result reports `worktreePath`. The branch is arranged in the worker's brief: the **first** worker of a ticket renames to `<type>/<TICKET>`, every later one switches to it. `worker-launch.md` owns both briefs and the guard.

**You stay in the main worktree for the whole run**, keeping `run.jsonl`, `task_plan.md` and `findings.md` writable. Why: from inside a worktree the Write tool refuses the main checkout outright.

**One worktree per worker, not per ticket, and they hand off through the branch:**

```bash
# after worker N reports, from the MAIN worktree — VERIFY, then remove
git log --oneline <base>..<type>/<TICKET>     # did the branch advance?
git -C <worktreePath> status --porcelain      # anything still uncommitted in there?
git worktree remove <worktreePath>            # only when the above two agree

# then the generated branch, BY ID and only when it is genuinely spare
ORPHAN=worktree-agent-<id>                    # <id> from THIS worker's worktreePath
git show-ref --verify --quiet "refs/heads/$ORPHAN" || : # renamed worker: nothing to do
git log --oneline "<base>..$ORPHAN"           # must be EMPTY before deleting
git branch -D "$ORPHAN"                       # only then
```

**The verify is not optional and `--force` is not the answer to it.** `remove` refusing
means the worktree still holds work — that is the check succeeding. If the branch did not
advance and the worktree is dirty, the worker did not hand its work over: **stop the ticket**.

**Remove between stages.** A worktree still holding the ticket branch makes the next worker's `git switch` fail as a guard `BLOCKED`.

**A renaming worker leaves no orphan; a switching one always does.** Check before deleting — `git branch -D` on a name that does not exist is an error, not a no-op.

**Three ways to get the sweep wrong:**

- **Pattern-matching `worktree-agent-*`.** Delete by the id from *this worker's* `worktreePath`. A wildcard reaches branches this run did not create.
- **Deleting one that carries commits.** The emptiness check precedes `-D` and is not decoration. A generated branch with commits means a worker committed before switching — **report it, do not delete it.**
- **Skipping it.** ~7 switching stages per ticket, so a five-ticket run leaves ~35 opaque names indistinguishable from a branch still holding work.

**`git branch --list 'worktree-agent-*'` printing nothing is the cheap end-of-run check** that
every worker handed its worktree back.

**Location is `.claude/worktrees/`** — gitignored fleet-wide by the `.claude/*` rule `setup-project.py` installs, so a worktree there never appears in the parent's `git status`.

**A project that needs untracked directories present** declares them in `.claude/settings.json`:

```json
{ "worktree": { "symlinkDirectories": ["fonts"] } }
```

Symlinked, not copied. **Write the ignore pattern without a trailing slash** — `fonts`, not `fonts/` — because in a worktree the entry is a symlink (a file to git), and a trailing slash matches directories only.

### Everything the orchestrator writes stays in the MAIN worktree

`run.jsonl`, `task_plan.md` and `findings.md` live in the main worktree's tracking dir.
`tracking-dir-resolution.md`'s `$ROOT` is `dirname "$(git rev-parse --git-common-dir)"`,
which resolves to the **main** worktree root from inside a linked one. Use that form and
never `[ -d .slopstop ]` from the cwd.

### Teardown is verdict-driven

This is about the ticket's *last* worktree. Per-stage ones are removed as the run goes.

- **Merged** -> remove the worktree, then the branch: `git worktree remove <path>` then
  `git branch -d <type>/<TICKET>`. Then confirm `git branch --list 'worktree-agent-*'` prints nothing — as a *check*, not a delete list.
- **Stopped, or the attempt cap exhausted** -> **the worktree stays, and you lock it.** Never
  clean it on a kill. The full rule, the lock command, and the `unlock -> remove -> branch -D`
  abandon order are one definition in `failure-and-salvage.md`.
- **`DROP`** -> the *new* attempt gets a **fresh worktree** and a new branch. The dropped worktree is preserved and locked like any stop. The new attempt's first worker does **not** switch to the dropped branch.

**So `git worktree list` after a run shows the main worktree plus one per *stopped* ticket.**

## Scheduling across tickets (PRD D14)

1. **Fan out `investigate` for all N tickets first.** Read-only, always safe and always parallel.
2. **Explicit relations first — `Blocked by:` is a hard edge.** Below.
3. **Then schedule by overlap, deterministically.** Among unblocked tickets, those with disjoint predicted file maps run stages 3-12 concurrently; overlapping ones run serially. **Order overlapping tickets by ticket key, ascending** — a stable, stated tie-break. Re-running the same list must produce the same schedule.

   **Write the computed schedule as a `note` before stage 3 opens.** Append a **new** `schedule` note each time the runnable set changes.

   ```json
   {"event":"note","stage":"schedule","at":"...","result":
    "concurrent: [BILL-501, BILL-504]; serial: BILL-502 -> BILL-503 (overlap on
     internal/handler/services.go); order within an overlap group is ticket-key ascending"}
   ```

   **A key-order tie-break is conflict avoidance, never correctness.** Semantic ordering belongs in `Blocked by:`.
4. **Merge serially, always.** On conflict: `git merge master` **into the losing branch**, resolve, re-run that ticket's test command, push, merge. **Never rebase.**

**When the explicit relation and the file-affinity heuristic disagree, the explicit relation wins.**

One ticket <-> one branch <-> one PR. Never bundle two tickets onto a branch, and never branch off another ticket's branch.

### `Blocked by:` — read it, or the dependency does not exist

Every leaf ticket carries `Blocked by:` in its header. **Parse it at intake, for every ticket.**

**Finding the declaration and parsing its value are two steps, and the recognisers differ.**

*Step 1 — find it by phrase, not by punctuation.* Search for the case-insensitive phrase `blocked by`, ignoring markdown emphasis. **Do not anchor to a colon** — some tickets read `**Blocked by three, all real:**`. **Do not anchor to line start** — the template puts the declaration mid-line. Both wrong anchors fail silently by finding nothing, which the absent rule then reads as "no blockers".

*Step 2 — parse the value, strictly, and bound it.* The value runs from the phrase to the **first sentence terminator** (`.` followed by whitespace or EOL) or end of line. Strip any `<issue ...>KEY</issue>` wrappers (Linear stores cross-references as tags). Accept exactly two forms: the literal `nothing`, or keys matching `^$PREFIX-\d+$`. Trailing prose is context for the reader. A recognised declaration yielding neither `nothing` nor a key is **unparseable** and **holds the ticket**. Do not guess at prose.

**A key from another project is a third case, not garbage.** A token matching `^[A-Za-z][A-Za-z0-9]*-\d+$` whose prefix is not `$PREFIX` is a **foreign-project blocker**. Hold the ticket: `held (blocked by BILL-471 — foreign project, not resolvable here)`. Unparseable and foreign need opposite responses from the human.

**Absent means step 1 found nothing.** Report it, treat it as `nothing`, and say you did both. Absent and `nothing` mean different things. **A line step 1 recognised can never reach this rule** — it either parses or it holds.

**A blocker is satisfied when it is MERGED, not when it is done.** Two cases:

- **The blocker is in this run's list.** Satisfied once *its own* stage 13 merge has completed and the PR reads `MERGED`.
- **The blocker is not in this run's list.** Check once at intake, in this order:
  1. **Its commits are on the base branch** -> **satisfied**:
     ```bash
     git log "$ORIGIN_REMOTE/$BASE_BRANCH" --oneline --grep="^\[<KEY>\]"
     ```
  2. **Status category**, only when step 1 finds nothing -> terminal means **satisfied**.
  3. Neither -> **hold**.

**Merge evidence outranks status.** Why: `post_merge_done = false` parks a merged ticket one state short of terminal, so reading status first creates a deadlock where a merged out-of-run blocker holds forever.

**Ask git, not the PR list, and anchor the pattern.** `^\[<KEY>\]` matches a commit *belonging to* the ticket; an unanchored search matches any commit that mentions it. This works because universal S3 forbids squash/rebase merges, keeping prefixed subjects reachable from the base branch.

**Step 1 finding nothing is not evidence that nothing landed.** A ticket landed by hand without the prefix leaves no trace — fall through to the status check.

**The status fallback is load-bearing.** A cancelled ticket never merges; only its category answers for it.

**Terminal is a property of the status CATEGORY, never of its name:**

| backend | terminal when |
|---|---|
| JIRA | `statusCategory.key == "done"` |
| Linear | `state.type == "completed"` |
| GitHub Issues | `state == "CLOSED"` |

**Never test against a list of status names.** Why: every project renames its columns, and names like `DontFix` sit in category `done` while matching no plausible spelling.

**Re-check the blocked set after every merge**, not once at the start.

### Holding, and what a hold is not

A held ticket has **not run**:

- It consumes no attempt and is not a failure.
- It opens **no span**. Record a `note` naming the ticket and every unsatisfied blocker.
- If never released, the run ends cleanly with that ticket untouched. **This is not an error.**

**Report held tickets under their own heading**, separate from stopped tickets and from `parked awaiting <state>`.

### Cycles stop the run

Before launching anything, check the blocked-by graph for a cycle. One found -> **stop the run** and name every ticket in it. Check for cycles of any length.

### The native relation is a cross-check, never the source

Read the backend's own blocked-by relation and **compare**. **The prose line wins.** Report any disagreement in both directions and say which you acted on. **Never write the native relation** (universal S5). **Report the same comparison again at close** (stages 13-15, step 3a).

## Invariant tickets — refactor and backfill

**This is the one definition of all three modes.** Do not restate it elsewhere (universal S5).

A normal ticket proves itself by change (test fails at base, passes after). An invariant ticket changes no behaviour, so it has no such test. Two invariant modes, exact mirrors:

| | **refactor** | **backfill** |
|---|---|---|
| deliverable | production code | tests |
| may **not** modify | any **test** file | any **production** file |
| evidence | the whole suite: green before, the same green after | **every new test is mutation-proven** |
| `red-tests` | not launched | launched with `--backfill`; confirms **green** |
| `mutation-check` | not launched — no new tests | **the gate**, question inverted |
| `vacuity-check` | not launched — no new tests | not launched — passing at base is the point |
| stage-4 outcome | `PHASE 0: none — refactor` | `PHASE 0: green — backfill` |

Each mode freezes exactly what the other delivers, so neither can smuggle in the other's work.

### Resolve the mode at intake — from labels, and from nothing else

Mode is carried by a **label**, one of exactly two, with fixed names:

| label | mode |
|---|---|
| `slopstop-refactor` | production code only; no test file may change |
| `slopstop-backfill` | tests only; no production file may change |
| *neither* | normal |

**Read the labels through the backend's API. Do not parse the ticket body for a mode.** Why: a body marker mangled by an editor silently runs the wrong mode, and both directions reported clean. A label is structured data behind an API that cannot be reflowed.

| backend | read |
|---|---|
| `github` | `gh issue view $N --repo $OWNER/$REPO --json labels -q '[.labels[].name]'` |
| `linear` | `get_issue` -> the issue's `labels` |
| `jira` | `getJiraIssue` -> the `labels` field |

Then **count what you found**:

| labels present | result |
|---|---|
| neither | normal ticket |
| exactly one | that mode |
| both | **stop the ticket**: `RUN BLOCKED: ticket carries both slopstop-refactor and slopstop-backfill` |

**Never create a label on this path.** Resolving mode is a **read**. A mode label absent from the project means no ticket there can carry it. **The rule is about reading, not about `:run`** — create a label at the point you must **apply** it (stages 13-15 step 3), never at the point you merely read for one.

`create-ticket` ensures a mode label exists at the point it applies one, and `gh-init` seeds both as a convenience.

Set `$REFACTOR` or `$BACKFILL` once, at intake, and record it as a `note` **naming the label
it came from**:

```json
{"t":"...","kind":"note","text":"mode: refactor (from label slopstop-refactor)"}
{"t":"...","kind":"note","text":"mode: normal (no slopstop-refactor or slopstop-backfill label)"}
```

The note is **derived, not authoritative**. The labels on the ticket are the source of truth. **Never infer a mode** from the title, the file map, the body, or how the diff turns out.

The names are namespaced with `slopstop-` to avoid collision with bare `refactor` labels in existing backlogs. The separator is a hyphen — a colon was rejected because Linear reinterprets `slopstop:refactor` as a label group, recreating the bare-name collision. There is no `slopstop-normal` label: absence of both is the declaration.

### `$OWN` — what THIS branch changed, derived at check time

Both invariant-mode checks and the file-map check ask: **which files did this branch change?** `$BASE` is not the answer after a `git merge master` into the branch.

**Derive the comparison point instead, every time you check:**

```bash
OWN="$ORIGIN_REMOTE/$BASE_BRANCH...HEAD"                       # comparing two commits
FORK=$(git merge-base "$ORIGIN_REMOTE/$BASE_BRANCH" HEAD)      # comparing against the working tree
```

Why: `$BASE` is the fork point. After merging the integration branch in, `git diff "$BASE"..HEAD` reports everything master gained as though this branch wrote it. The left side must be the integration branch, not the fork point. The three-dot form against `$BASE` is byte-identical to two-dot because `$BASE` *is* an ancestor of `HEAD`.

On a branch that has merged nothing this is a no-op. **`$FROZEN` is untouched by all of this** — it is a point *on this branch*, and the tamper diff is pathspec-limited to the frozen set.

### Refactor mode — `$REFACTOR`

When `$REFACTOR` is set, five things change:

1. **Stage 4 writes no tests.** Record `PHASE 0: none — refactor` yourself. Stages 5-7 skipped, `$FROZEN` absent.
2. **`implement` is launched with `--refactor`.** Its Step 1.3 full-suite run becomes the baseline and the guard.
3. **A red baseline stops the ticket.** `implement` returns `IMPLEMENT BLOCKED: refactor baseline not green`. You cannot prove you broke nothing against a broken suite.
4. **`vacuity-check` is not launched.** Record `VACUITY SKIPPED: refactor ticket — no new tests`. A legitimate skip, **not** `BLOCKED`. `slop-check`, `complexity-check`, and `duplication-check` run normally.
5. **You check mechanically that no test file was touched**:

   ```bash
   git diff --name-only "$OWN" | grep -E '(^|/)(tests?|spec|testdata|__tests__)/|_test\.|\.test\.|_spec\.|conftest\.py$'
   ```

   Any output is a **stop**, naming every path. This is checked by a diff you run, not by a claim anyone makes.

   **This one expression decides both invariant modes**, and backfill inverts it with `-v`.
   Keep it aligned with the `test_globs` list in `run-jsonl.md`.

***Nothing broke* is all three of: the suite green before, the same suite green after, and
no test file modified.** Not two of three.

**"The same suite" means the same runnable node-id set, not the same count** — compared as sets, in both directions. -> Read `skills/run/references/node-ids.md`

What is `:run`'s alone: **`implement`'s Step 1.3 baseline is one side of the comparison and
its final run is the other.**

### Backfill mode — `$BACKFILL`

When `$BACKFILL` is set, six things change:

1. **Stage 4 launches `red-tests --backfill`, which confirms the tests are GREEN.** A test that comes up **red** means the ticket is a normal ticket in the wrong mode. Stop it.
2. **Stage 5 launches `mutation-check --backfill`, and it is the gate.** Any `not-pinned` **stops the ticket**. This replaces `vacuity-check`.
3. **Stage 7's adversary runs normally.** There *are* new tests here, so there is something to attack.
4. **`vacuity-check` is not launched.** Record `VACUITY SKIPPED: backfill ticket — tests pass at base by design`. A legitimate skip, **not** `BLOCKED`.
5. **You check mechanically that no production file was touched** — the exact mirror of refactor mode:

   ```bash
   git diff --name-only "$OWN" | grep -vE '(^|/)(tests?|spec|testdata|__tests__)/|_test\.|\.test\.|_spec\.|conftest\.py$'
   ```

   Note the `-v`. Any output is a **stop**.
6. **`mutation-check --backfill` re-runs after stage 7, if stage 7 changed the tests.** Report the re-run as the authoritative verdict with its sha. If stage 7 changed nothing, say the stage-5 proof stands.

### Stage 8a under `$BACKFILL` — same trigger, mechanical resolution

**Do not skip the tamper diff.** The sharpest evasion: `mutation-check` says `not-pinned`, so the test is deleted. That produces the same diff as a legitimate rewrite.

**Trigger is unchanged; resolution is evidence.** A removal inside the frozen set stops the ticket, cleared by **both** of:

1. **The node-id set did not shrink.** Compare sets, not line counts. A dropped node-id stops the ticket on its own. Enumerate both sides from the runner, never from source. -> Read `skills/run/references/node-ids.md`
2. **`mutation-check --backfill` passes on the current files.**

Both, or the stop stands. **Never clear it by reading the diff for intent.**

**Neither mode is a way to skip tests-first.** A ticket that needs both modes is two tickets.

## Stage details — loaded on demand

Read the stage group that applies when you reach it. Each contains the full contract
for its stages.

### Stages 4-7: red tests, mutation-check, phase-0 commit, adversary
-> Read `skills/run/references/stages-phase0.md`

Covers: `$FROZEN` capture, adversary loop mechanics (verdict branching, cap-at-3,
residue table, gap tests, commit format).

### Stages 8-9: implement, tamper, gates, pinning
-> Read `skills/run/references/stages-implement.md`

Covers: 8a tamper check, 10b handoff verification (three-way verdict, SALVAGE/DROP),
stage 9 four gates + pinning pass (regression-tag handling, CC breach reduction,
mode variants).

### Stages 10-12: review, handoff, bot-read
-> Read `skills/run/references/stages-review.md`

Covers: review loop (cap 5, residue rule), 10b handoff summary, stage 12 bot-read
(read once, never poll).

### Stages 13-15: merge, close, archive + resuming + failure
-> Read `skills/run/references/stages-close.md`

Covers: mergeStateStatus table, DoD scoring, label creation, derive.py, archive
worker, human-wait bracketing, resuming from disk, re-scoring after ticket-defect
`not-met`, failure handling, `$PUBLISH_ARTIFACTS`.

## Rules

- **One writer.** You write `run.jsonl`; no worker does, and no worker resolves a tracking dir.
- **One reader.** You read `.project-conf.toml`; no worker does.
- **One launch form.** Every worker goes through the `Agent()` form in `worker-launch.md`.
- Adversarial and checking work runs **one tier above** the work it checks.
- Never `git push --force`, `git reset --hard`, `git commit --no-verify`, or `gh pr merge --admin`. Never rebase a pushed branch. Never squash- or rebase-merge.
- Commits anchored to a ticket carry `[<TICKET>]` in the subject and a `Refs:`/`Closes:` trailer — provenance only, not a GitHub closing keyword.
- Never use `open` to display a file.
