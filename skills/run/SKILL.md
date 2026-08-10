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
  model resolution, the eleven-worker roster with each worker's arguments and return, and
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
so when you stop it: recommend `/slopstop:tickets --rewrite <TICKET>`, which captures the
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
→ Read `~/.claude/commands/slopstop-run-refs/config-resolution.md`

Read the tracked file from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Missing from both → stop with
`"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file
manually with system + key."`

Resolve, and carry, all of the following. A missing key takes its documented `CONFIG.md`
default; a missing table never errors. **Workers read none of this** — every value reaches
a worker only as an explicit argument, and a worker given nothing blocks rather than
guessing.

| value | source | default |
|---|---|---|
| `$PREFIX` | `prefix` | none — stop if absent, malformed, or disagreeing with the tickets |
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
→ Read `~/.claude/commands/slopstop-run-refs/tracking-dir-resolution.md`

### Prefix-agreement preflight — before any ticket runs

**`$PREFIX` matching the regex is not the same as `$PREFIX` being right.** Once you have the
ticket keys for this run, compare each one's prefix against `$PREFIX` **byte for byte**, and
stop the whole run on a disagreement:

```
RUN BLOCKED: config prefix '<$PREFIX>' does not match ticket keys '<KEY>' — fix
             .project-conf.toml's `prefix`, or the ticket keys, before re-running
```

**Case included. `Bill` is not `BILL`.** That is the whole defect: nothing else in the system
compares these two, and every downstream consumer is case-sensitive. The router derives a
spend record's prefix from the `X-Slopstop-Ticket` header — the real ticket key — while
`/spend?prefix=…` filters on the config's `prefix`. A repo whose config says `Bill` against
`BILL-*` tickets gets `/spend?prefix=Bill` → **HTTP 200 with zero totals**. Not an error, not
an empty-result warning: a successful-looking response saying the run cost nothing.

**The check has to live here.** Charter rule 2 bars the router from reading project config, so
the router cannot notice the disagreement, and the config cannot notice the tickets. `:run` is
the only thing that holds both.

**Stop the run rather than warning.** A silent zero is unrecoverable after the fact — the spend
was recorded under the other prefix and no later query reconstructs which run it belonged to —
and the fix is a one-character config edit before anything is spent. This is the cheapest
possible moment to catch it and the only one where nothing is lost.

> **Do not "helpfully" normalise the case and continue.** Guessing which of the two is correct
> is the proxy-for-identity mistake: the config might be wrong, or the tickets might be, and
> they need opposite fixes from the human. Report both values and let them decide.

## The state machine

State lives in each ticket's `run.jsonl` at `$TRACKING_DIR/<TICKET>/run.jsonl`, **not in
your context**. A long multi-ticket run gets compacted; anything you only remembered is
gone. Before acting on a ticket, read its file; after acting, append.

Per ticket, in order. **W** = a worker launch (one `Agent()` per `worker-launch.md`);
**I** = your own inline work, no worker, no fork.

| # | stage | kind | record | notes |
|---|---|---|---|---|
| 1 | `intake` | I | **note** | fetch the ticket, its five sections and its **DoD**; set `$REFACTOR` / `$BACKFILL` (below); **parse `Blocked by:`** (see Scheduling); seed `$TRACKING_DIR/<TICKET>/` with `task_plan.md` + `findings.md` and open `run.jsonl` |
| 2 | `investigate` | W | **span** | returns findings + the **predicted file map**. Run for all N tickets before anything else — see Scheduling |
| 3 | `branch` | I | **note** | label/state → in progress; create the ticket's **worktree and branch** — see `## Worktrees` below. `<type>` per `slopstop-run-refs/branch-type.md`. Record `$WT` = the worktree path and `$BASE` = the branch point sha. **You never `git switch` the main worktree**, at this stage or any other. The stage keeps the `stage` value `branch` — it is a record key, and renaming it would break invariant 6 and orphan every run.jsonl already on disk |
| 4 | `red-tests` | W | **span** | returns test files, node-ids, `--command`, stub paths, observed failure output. `--backfill` when `$BACKFILL` — then it confirms **green**. Not launched when `$REFACTOR` |
| 5 | `mutation-check` | W | **span** | `--tests --node-ids --command --targets --stubs` from stage 4. `--backfill` when `$BACKFILL` — then it is **the gate**, not a sanity check, and it **re-runs after stage 7** if stage 7 changed the tests. Not launched when `$REFACTOR` |
| 6 | `phase0-commit` | I | **note** | commit the red tests + stubs. **Capture `$FROZEN` here.** Under `$BACKFILL` the commit holds green tests and no stubs — `$FROZEN` is captured the same way and means the same thing |
| 7 | `adversary` | W+I | **span** | the loop, the add/skip decision, gap-test authoring, RED re-verify, gap commit — all yours. **One span per round**, never one span per loop |
| 8 | `implement` | W | **span** | the ticket, the plan, the failing tests. **It may add tests; it may never weaken, retarget or remove one** — `skills/implement/SKILL.md` is the definition and this row used to compress it, wrongly, to "may not touch the tests". Under `--refactor` it may modify no test file at all. `--refactor` when `$REFACTOR`. **Not launched when `$BACKFILL`** — the tests are the deliverable and they already pass, so there is nothing to implement |
| 8a | `tamper` | I | **span** | **mechanical, yours, before any checker is spawned**: the tamper diff against `$FROZEN` and the file-map violation check against `$OWN`. A FAIL stops the ticket here — no worker is bought. Under `$BACKFILL` the trigger is unchanged and the **resolution** is a mutation re-run, not a judgment — see below |
| 9 | `gates` | W×3, then W×1–3 | **span** | `slop-check`, `vacuity-check`, `complexity-check` — launch together, they are independent **because all three are read-only**. That is the reason, and it does not generalise: 10b's two workers mutate production and must be serialized. **Then the pinning pass** — `mutation-check --implemented` against `$OWN`'s production diff, looping to a cap of 3, one span per round. It runs *after* the three, never beside them: it mutates, and a mutating worker never shares a tree. **After `implement`, deliberately**: the adversary's false-negative vector at stage 7 cannot see tests written later, and `vacuity-check` here is what covers them (BILL-343). W×2 when `$REFACTOR` or `$BACKFILL` |
| 10 | `review` | W | **span** | loop until `REVIEW CLEAN`, cap 5 rounds |
| 10a | `size` | I | **note** | once the diff exists: `git diff --numstat "$BASE"..HEAD`, then record **one entry per file** (path, added, removed, kind) plus the aggregates, the `test_globs` you classified by, and the provisional `tier` computed from **production counts**. **Nothing reads it** — it is the data that will later decide what is safe to skip |
| 10b | `handoff` | W×2 | **span** | a **fresh** requirements adversary and code reviewer at the tier above, **launched SERIALLY — never in parallel** (both mutate production to prove findings and contaminate each other otherwise; PLTF-2562), fed artifacts only — never the agent's comments or the PR description. Applied fixes are committed before the round closes, then re-verified on the new tip. Produces a blessing bound to the **branch tip SHA**. **W×1 for an invariant ticket**: requirements adversary only under `$BACKFILL`, code reviewer only under `$REFACTOR` — see `handoff-verification.md` |
| 11 | `pr` | I | **span** | commit, push to `$PR_REMOTE`, open the PR against `$OWNER/$REPO` |
| 12 | `bot-read` | I | **note** | read existing bot comments **once**. Never poll |
| 13 | `merge` | I | **span** | serial across tickets; `gh pr merge --merge --delete-branch` |
| 14 | `close` | I | **span** | score the DoD, advance the ticket state / swap labels, write the DoD confirmation into `task_plan.md` |
| 15 | `archive` | W+I | **span** | launch the `archive` worker (one comment per tracking file), close the log, then `mv $TRACKING_DIR/<TICKET> $ARCHIVE_DIR/<TICKET>` |

Stage 4 has two legitimate empty outcomes: `PHASE 0: none — prose-only change` and
`PHASE 0: none — refactor` (below). In both, stages 5–7 are skipped, `$FROZEN` is absent,
and every consumer of `$FROZEN` is told so explicitly rather than being handed a guess.

Prose that names a stage in `run.jsonl` uses **exactly these `stage` values**, so one pass
over the file reconstructs the run.

## Worktrees — where concurrent work physically happens

**Two branches cannot be checked out in one working tree.** A `git switch` between tickets
mid-flight interleaves their edits into whichever branch happens to be checked out when each
write lands: both PRs look plausible and both diffs are wrong, and no gate catches it because
every gate examines one branch against its own base. So each ticket gets its own worktree,
and **the main worktree is never switched.**

### Creating one

```bash
claude --worktree <TICKET>                 # Claude Code creates .claude/worktrees/<TICKET>
git -C .claude/worktrees/<TICKET> branch -m <type>/<TICKET>
```

**Location is `.claude/worktrees/<TICKET>` and is not a free choice.** `EnterWorktree` on a
path outside that directory raises an approval prompt that **no permission rule suppresses** —
only `bypassPermissions` skips it — so any other location stops an autonomous run dead at
every worker launch. It is gitignored fleet-wide by the `.claude/*` rule `setup-project.py`
installs, so a worktree there never appears in the parent's `git status` and cannot be staged
by accident (BILL-466: verified across all eight repos, and by live test).

**Why not `git worktree add`,** which would give the branch name directly: worktrees created
by plain git get none of Claude Code's setup — in particular `worktree.symlinkDirectories`,
which links configured directories from the main checkout into each new worktree and is how
universal §6's symlink rule is finally mechanized. Creating with `--worktree` and renaming
the branch afterwards gets both, and was probed end to end.

**A project that needs untracked directories present** (a font corpus, `node_modules`, a
fixture tree) declares them in `.claude/settings.json`:

```json
{ "worktree": { "symlinkDirectories": ["fonts"] } }
```

Symlinked, not copied. **Write the ignore pattern without a trailing slash** — `fonts`, not
`fonts/` — because a trailing slash matches directories only, and in a worktree the entry is
a *symlink*, which git records as a file. Get this wrong and every worktree carries a
permanent `?? fonts`, and a `git add -A` commits an absolute-path symlink into the repo.

### Everything the orchestrator writes stays in the MAIN worktree

`run.jsonl`, `task_plan.md` and `findings.md` are yours, not the worker's, and they live in
the main worktree's tracking dir. That is already how resolution works and needs no special
case — `tracking-dir-resolution.md`'s `$ROOT` is
`dirname "$(git rev-parse --git-common-dir)"`, which resolves to the **main** worktree root
from inside a linked one. Use that form and never `[ -d .slopstop ]` from the cwd, which
finds nothing in a worktree and falls through to a path a headless agent cannot write.

### Teardown is verdict-driven

- **Merged** → remove the worktree, then the branch: `git worktree remove <path>` then
  `git branch -d <type>/<TICKET>`. In that order — `remove` detaches without deleting the
  branch.
- **Stopped** → **the worktree stays, and you lock it.** Never clean it on a kill. The full
  rule, the lock command, and the `unlock → remove → branch -D` abandon order are one
  definition in `failure-and-salvage.md`.

**So `git worktree list` after a run shows the main worktree plus one per *stopped* ticket.**
An all-merged run leaves only the main worktree. A run that stopped a ticket and left nothing
behind has destroyed the evidence, which is the more expensive failure.

## Scheduling across tickets (PRD D14)

1. **Fan out `investigate` for all N tickets first.** It is read-only, so it is always safe
   and always parallel. Collect each ticket's predicted file map.
2. **Explicit relations first — `Blocked by:` is a hard edge.** Below.
3. **Then schedule by overlap, deterministically.** Among tickets that are *not* blocked,
   those whose predicted file maps are disjoint run stages 3–12 concurrently; overlapping
   ones run serially, later ones starting from the updated tip. Prediction is never perfect;
   this buys efficiency, not correctness.

   **Order overlapping tickets by ticket key, ascending.** A stable, stated tie-break — not
   whichever the model considered first. Re-running the same list against the same tickets
   must produce the same schedule, or the timing record in `run.jsonl` reports a coin flip as
   a fact and corrupts the measurements the file exists to collect.

   **Write the computed schedule as a `note` before stage 3 opens**, naming every
   serialisation and its cause. **It is provisional, and it will be superseded** — step 2
   re-checks blockers after every merge, and a ticket released by that merge was *held* when
   this note was written, so it appears in no schedule yet. Append a **new** `schedule` note
   each time the runnable set changes, naming what released and what it changed; never edit
   the first one, and never let the run end with a schedule that omits tickets it actually
   ran. A single note claiming to be the plan, while three tickets entered later by another
   route, is worse than no note — it reads as the whole story:

   ```json
   {"event":"note","stage":"schedule","at":"…","result":
    "concurrent: [BILL-501, BILL-504]; serial: BILL-502 -> BILL-503 (overlap on
     internal/handler/services.go); order within an overlap group is ticket-key ascending"}
   ```

   **A key-order tie-break is conflict avoidance, never correctness.** If two overlapping
   tickets have a *semantic* order — B must land after A — that belongs in `Blocked by:`,
   which step 2 already honours as a hard edge. PLTF-2563 and PLTF-2564 both touch
   `services.go` and 2564 must go first; overlap alone cannot express that, and the fix was
   an explicit `Blocked by:` line. Never promote the heuristic into the thing that decides.
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

**Finding the declaration and parsing its value are two steps, and the recognisers differ.**

*Step 1 — find it by phrase, not by punctuation.* A ticket declares blockers on any line
containing the case-insensitive phrase `blocked by`, ignoring markdown emphasis (`*`, `_`)
around it. **Do not search for the literal string `Blocked by:`** — the colon is the bug.
SOP-262's header reads `**Blocked by three, all real:**`; a colon-anchored search finds
nothing, the ticket falls through to the *absent* rule below, and a ticket that visibly
declares three blockers launches with zero of them while the report calls it dependency-free.

**Do not anchor to the start of a line either.** The ticket standard's own template puts the
declaration mid-line — `Parent: none — freestanding leaf. Blocked by: nothing.` — so a
line-initial rule finds nothing on every *correctly formed* ticket. Both wrong anchors fail
the same way: silently, by finding nothing, which the absent rule then reads as "no blockers".

*Step 2 — parse the value, strictly, and bound it.* The value runs from the phrase to the
**first sentence terminator** (a `.` followed by whitespace or end of line) or the end of the
line, whichever comes first. Bounding is not optional. SOP-261's declaration line reads
`… Blocked by: nothing. This entry only launches the backend … Related: AATK-69`, and an
unbounded read swallows that `Related:` key and invents a blocker the ticket never declared.

Within that span, first strip any `<issue …>KEY</issue>` wrappers — **Linear stores
cross-references as tags, so the stored text of a well-formed ticket is not the bare key** —
then accept exactly two forms: the literal `nothing`, or keys matching `^$PREFIX-\d+$`.
Trailing prose after the keys is context for the reader; `Blocked by: PLTF-2563 — for
merge-conflict avoidance only` parses to one key. A recognised declaration yielding neither
`nothing` nor a key — prose, a URL, or the SOP-262 shape above — is **unparseable**, and an
unparseable value **holds the ticket** and is reported. Do not guess at prose. A scheduler
that shrugs at `Blocked by: the auth work` and launches anyway has silently discarded a real
dependency, which is the whole failure this section exists to stop.

**A key from another project is a third case, not garbage.** A token matching
`^[A-Za-z][A-Za-z0-9]*-\d+$` whose prefix is not `$PREFIX` — `Blocked by: BILL-471` in a
`PLTF` project — is a **foreign-project blocker**. You cannot resolve it: you hold one
`.project-conf.toml`, one ticket system, one prefix, and nothing here reaches another repo's
backlog. So hold the ticket, and report it as `held (blocked by BILL-471 — foreign project,
not resolvable here)`. Reporting it as unparseable would be actively misleading: the two
need opposite responses from the human — *fix the ticket* versus *go check the other repo
and re-run when it lands*. This is not hypothetical; it is how a cross-repo dependency
actually gets written down.

**Absent means step 1 found nothing** — no line in the ticket begins `blocked by` at all. That
is a ticket-standard gap: report it, treat it as `nothing`, and say you did both. Absent and
`nothing` mean different things — "nobody wrote it down" versus "checked, there are none" —
and only one of them is a defect.

**A line step 1 recognised can never reach this rule.** It either parses or it holds; there is
no path from a recognised line to "treat as `nothing`". Collapsing near-miss into absent is
exactly what would have launched SOP-262 while SOP-261 was still In Progress, and the two
demand opposite responses from the human — *fix the ticket* versus *nobody wrote it down*.

**A blocker is satisfied when it is MERGED, not when it is done.** Two cases:

- **The blocker is in this run's list.** It is satisfied once *its own* stage 13 merge has
  completed and the PR reads `MERGED`. Not when its gates pass, not when its review is clean —
  a ticket whose code has not landed on the integration branch cannot be built on, and a
  dependent branch cut before that merge forks from a base that never contained the work.
- **The blocker is not in this run's list.** Ask the same question — did it land? — in this
  order, once, at intake:
  1. **Its commits are on the base branch** → **satisfied**, whatever its status says:
     ```bash
     git log "$ORIGIN_REMOTE/$BASE_BRANCH" --oneline --grep="^\[<KEY>\]"
     ```
  2. **Status category**, only when step 1 finds nothing → terminal means **satisfied**.
  3. Neither → **hold**.

**Merge evidence outranks status, and the reason is a live deadlock.** Reading status *first*
was this section's rule until BILL-500, and it contradicted the heading three lines above it.
`[workflow] post_merge_done = false` makes `:run` deliberately park a merged ticket **one state
short of terminal**, so slopstop's own setting guaranteed that a merged out-of-run blocker read
non-terminal and held forever. server-v2 sets it. PLTF-2563 sat at `In Review` — category
`indeterminate` — with its PR merged and its commit on `master`, and PLTF-2565 would never have
run. Any project with a 4-state workflow had the same deadlock.

What a dependent needs is not a workflow state; it is the blocker's code on the branch it is
about to fork from. Merge evidence answers that directly.

**Ask git, not the PR list, and anchor the pattern.** The commit-subject prefix is mandated by
the project's own conventions and `:run` writes it, so the commits carry the key. The grep is
local, needs no API, and answers the real question in one step: a commit whose subject begins
`[<KEY>]` sitting on the base branch *is* that ticket's work having landed there. No PR to
locate, no sha to extract, no separate ancestry test.

**Anchoring is the whole point, and an unanchored version is actively wrong.** `^\[<KEY>\]`
matches a commit *belonging to* the ticket; a bare search for the key matches any commit or PR
that merely *mentions* it. Proved while writing this rule: searching server-mycopy's PRs for
`PLTF-2562` returns one **MERGED** PR — #108, which belongs to **PLTF-2563** and only discusses
2562's cancellation in its body. An unanchored rule would have satisfied a cancelled blocker on
a sibling ticket's merge. Match commit subjects on the base branch, not free text anywhere.

This works because universal §3 forbids squash and rebase merges. A real merge commit keeps the
branch's own commits, prefixes intact, reachable from the base branch. Squash them into one
`Merge pull request #N` subject and this signal disappears — one more thing that rule buys.

**Step 1 finding nothing is not evidence that nothing landed.** A ticket landed by hand without
the subject prefix leaves no trace for the grep, so fall through to the status check. Treating
absence as "not merged" recreates the deadlock with extra steps, which is the failure this rule
exists to remove.

**The status fallback is load-bearing — do not remove it.** A cancelled ticket never merges.
PLTF-2562 was killed `DontFix` with no PR and no merge commit at all; only its category answers
for it. Merge-evidence-only would hold every dependent on a cancelled blocker forever, which is
the same deadlock wearing the opposite mask.

**Terminal is a property of the status CATEGORY, never of its name.** One definition, here:

| backend | terminal when |
|---|---|
| JIRA | `statusCategory.key == "done"` |
| Linear | `state.type == "completed"` |
| GitHub Issues | `state == "CLOSED"` |

**Never test against a list of status names.** Every project renames its columns, and the
names that matter are the ones nobody thinks to list: PLTF-2562 was killed as `DontFix`, which
sits in category `done` while matching no plausible spelling of "done". A name list holds a
dependent ticket forever on a blocker that is finished, and reports it as still open. It fails
the other way too — a column *named* "Done" that a project has parked in an in-progress
category would read as satisfied and release a dependent early. The category is the backend's
own answer to this question; ask it rather than guessing from the label.

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

**Report the same comparison again at close** (stages 13–15, step 3a), with the link ids.
A blocker discharged *during* the run leaves a link that agreed at intake and disagrees by
the end — and on JIRA nobody can delete it, so naming it is the only correction available.

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

### Resolve the mode at intake — from labels, and from nothing else

Mode is carried by a **label**, one of exactly two, with fixed names:

| label | mode |
|---|---|
| `slopstop-refactor` | production code only; no test file may change |
| `slopstop-backfill` | tests only; no production file may change |
| *neither* | normal |

**Read the labels through the backend's API. Do not parse the ticket body for a mode.**
There is no `Mode:` marker, no emphasis to strip, no flattener to get right, and no
fallback. A body that mentions a mode in prose is discussing one, not declaring one.

| backend | read |
|---|---|
| `github` | `gh issue view $N --repo $OWNER/$REPO --json labels -q '[.labels[].name]'` |
| `linear` | `get_issue` → the issue's `labels` |
| `jira` | `getJiraIssue` → the `labels` field |

Then **count what you found**:

| labels present | result |
|---|---|
| neither | normal ticket — no warning, this is the common case |
| exactly one | that mode |
| both | **stop the ticket**, naming both labels |

A ticket carrying both labels can change nothing at all: refactor freezes every test file,
backfill freezes every production file, and together they freeze the repository. That is a
ticket-authoring defect, not a mode to resolve. Report it as
`RUN BLOCKED: ticket carries both slopstop-refactor and slopstop-backfill`.

**Never create a label on this path.** Resolving mode is a **read**, and a read creates
nothing. A mode label absent from the project means no ticket there can carry it, which is
already the correct and safe answer — creating one here changes nothing about the ticket in
front of you and gives the read a write it has no business making.

> **The rule is about reading, not about `:run`.** Create a label at the point you must
> **apply** it; never at the point you merely **read** for one. `:run` does both: it reads
> mode here and it applies the status labels at stages 13–15 step 3, where ensuring the label
> exists is mandatory because GitHub rejects an edit naming an unknown label outright.
>
> Stated as a blanket *"`:run` never creates a label"* until 2026-08-09 (BILL-527), which
> contradicted the status-label swap two stages later and stranded it: a project that skipped
> `gh-init` merged its code and then could not advance its ticket. Do not re-broaden this back
> to all of `:run` — the read/apply distinction is the whole content of the rule.

`create-ticket` ensures a mode label exists at the point it applies one, and `gh-init` seeds
both for a fresh GitHub project as a convenience.

Set `$REFACTOR` or `$BACKFILL` once, at intake, and record it as a `note` **naming the label
it came from** — so a later reader can see what the mode was decided from rather than taking
your word for it, and so an archived run stays auditable without a second source:

```json
{"t":"…","kind":"note","text":"mode: refactor (from label slopstop-refactor)"}
{"t":"…","kind":"note","text":"mode: normal (no slopstop-refactor or slopstop-backfill label)"}
```

The note is **derived, not authoritative**. The labels on the ticket are the source of truth;
this record exists so the archive can be read without querying the tracker again.

**Never infer a mode** from the title, the file map, the body, or how the diff turns out. A
mode inferred after the fact is a mode an implementer can talk you into.

> **Why a label and not a body marker.** Until 2026-08-09 the mode was a `**Mode:** refactor`
> line in the body, and its failures were all silent and all in the losing-rigour direction:
> refactor mode does not merely forbid test edits, it **skips Phase 0 entirely** — no
> `red-tests`, no `mutation-check`, no `adversary` rounds. A marker mangled by an editor ran
> the ticket as normal with its test-file guard never armed; the reverse skipped every gate.
> Neither failed. Both reported clean. A body is prose in a field every ticket-system editor
> is free to reflow, re-emphasise, or wrap — and the marker had already needed a rule for
> ADF-versus-markdown emphasis and a precondition on block flattening, each a way to read
> `normal` from a ticket that said `refactor`. A label is structured data behind an API: it
> cannot be reflowed into something else, and all three backends support it natively.

> **The names are namespaced, and fixed, on purpose.** A bare `refactor` label already exists
> in real backlogs meaning "this is refactoring work", loosely; reading that as "engage
> invariant mode" would silently re-interpret every pre-existing ticket carrying it, in the
> direction that skips gates. And the names are **not** configurable — `[status_labels]` is,
> which is exactly what makes it a required key a project can get wrong. One definition
> (universal §5). There is deliberately **no `slopstop-normal` label**: absence of both is the
> declaration, and a third label would recreate the absent-versus-declared-absent ambiguity
> that moving to labels removes.

> **The separator is a hyphen, and a colon was rejected on evidence.** `slopstop:refactor`
> was the first design. **Linear reinterprets it**: `group/label` and `group:label` are
> Linear's add-label syntax for creating a label group, so `slopstop:refactor` there does not
> create that label — it creates a group `slopstop` containing a label named **`refactor`**,
> which is precisely the bare-`refactor` collision the namespace exists to prevent, landing
> in the gate-skipping direction. On JIRA a colon is at best degraded: labels containing `:`
> are reported not to appear in autocomplete, so a human cannot find the label to apply it.
> A hyphen has no special meaning on any of the three.
>
> **All three are now verified, and none of it is inference.** Linear: checked 2026-08-09
> against its documented add-label syntax. GitHub: slopstop has shipped `status:in-progress`
> for months, and hyphens are unremarkable there. JIRA: **tested live** on 2026-08-09 by
> Ian, who applied `slopstop-foo` to PLTF-2567 and confirmed it holds — a hyphenated,
> `slopstop`-prefixed label is accepted. That last one replaces what this note previously
> recorded as public report rather than a probe; do not reintroduce the hedge.

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

**"The same suite" means the same runnable node-id set, not the same count** — compared as
sets, in both directions. What a node-id is, why a declaration is not one, and how to take
the set from the runner are defined once and not restated here (universal §5).
→ Read `~/.claude/commands/slopstop-run-refs/node-ids.md`

What is `:run`'s alone: **`implement`'s Step 1.3 baseline is one side of the comparison and
its final run is the other**, so both sides already happen and neither needs a separate step.

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

   **Enumerate both sides from the runner, never from the source** — the rule and the recipe
   are defined once and not restated here (universal §5).
   → Read `~/.claude/commands/slopstop-run-refs/node-ids.md`

   Why it bites *at this gate* specifically: PLTF-2562's entire enumeration contract lived
   inside a single `t.Run`, so a function-level comparison reported "no shrink" — exactly as
   it would have if that subtest had been deleted outright. The later side comes from
   `mutation-check`'s Step B1 report, which enumerates as part of a run it already performs.

   A set you could not build is `could-not-enumerate`, and the stop **does not clear**.
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

**`adversary` is a review primitive: every round's close carries `findings`.** It already
assigns `blocker`/`major`/`minor` and `behavioural`/`presentational` to each numbered finding,
so this is transcription, not judgment — count them into the object `run-jsonl.md` defines and
leave the verdict line in `result` beside it. `ADVERSARY PRESENTATIONAL: n` is reproducible
from the record only if the class split is in it; without that, the verdict cannot be
explained by the numbers next to it.

**Branch on its verdict line, which is not prose:**

- `ADVERSARY PASS` → advance to stage 8.
- `ADVERSARY FAIL: n` → work the findings, then run another round.
- `ADVERSARY PRESENTATIONAL: n` → every finding is naming, comments or wording, with no
  behavioural or contractual consequence. **Fix them, then run one `--verify-only` round** —
  a resolved/not-resolved pass over those findings, no fresh attack. `PASS` from that round
  advances to stage 8. This is where a round gets saved, and it is safe precisely because the
  round that produced it already searched the whole target and found nothing behavioural.

  **One behavioural finding among twenty presentational ones is `FAIL`**, and `FAIL` re-attacks
  normally. The verdict is about the whole round, and the adversary classes toward
  `behavioural` when uncertain.

  This applies to **stage 7 only**. `:tickets` and `:design` run their own adversary loops
  over *documents*, where a wording finding is the substance rather than the polish — applying
  this there would gut ticket authoring.
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

→ Read `~/.claude/commands/slopstop-run-refs/handoff-verification.md`

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

**10b is a review primitive, so its closes carry `findings` too** — both agents'. The reviewer
returns a severity split on its verdict line; the requirements adversary returns severities on
its numbered findings. Transcribe both, per `run-jsonl.md`. **This stage is the reason the
field exists**: "does the tier above find things the tier below did not?" is unanswerable if
10's counts are structured and 10b's are not, and an uninstrumented 10b close reads as a tier
that found nothing — the error that flatters the cheaper option.

**One launch note per agent, not per span.** W×2 here means two notes, and their `tier` will
differ from stage 10's by exactly one rung — which is the measurement.

## Stage 9 — the three gates, then the pinning pass

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

**Every mechanical gate runs in every mode.** The mode-based skips below and at 10b remove
*tier-above worker launches*, which is where the wall-clock goes; a mechanical check costs
seconds and is what actually catches the failures this process exists for. Never skip one to
save time.

When `$REFACTOR` is set, launch two: `vacuity-check` is not run and you record
`VACUITY SKIPPED: refactor ticket — no new tests` yourself. `slop-check` is told
`--frozen none --refactor` so it does not read the absent Phase 0 baseline as tampering.

When `$BACKFILL` is set, launch **one**: `vacuity-check` is not run, and **`complexity-check`
is not launched either** — a backfill ticket has zero production diff, so measuring the test
file returns numbers nobody acts on. Record `CC SKIPPED: backfill ticket — no production diff`.
For `vacuity-check`, record
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
It is not a footnote — it is the queue for `/slopstop:tickets --refactor <fn>…`, and it is
the only place the complexity the run declined to block is ever visible. A run that exempts
23 violations and reports `CC CLEAN` with no list has hidden exactly what the exemption was
supposed to make actionable.

### The pinning pass — mutate what `implement` actually wrote

**Nothing between stage 8 and 10b perturbs the real implementation.** Stage 5's
`mutation-check` mutates the **stubs**, before `implement` exists. `vacuity-check` asks
whether a test would have failed *before the branch*, which is a different question and
contains no mutation logic. So every "the suite does not actually pin this" defect had to
survive to the tier above, and the measured record shows it doing exactly that — SOP-262's own
log: *"NEW test-adequacy gaps proven by live mutation, **not previously seen in rounds 1–2 or
in stage 9's earlier mutation-check (which only covered the two node-ids)**."*

Launch after the three gates return, **not with them**, for two independent reasons. It
**mutates production**, and `worker-launch.md`'s protocol is explicit that two workers never
share a working tree while one is perturbing it — the rule PLTF-2562 paid for at 10b. And it
is worth nothing on a branch a gate has already condemned. The three gates are safe to launch
together precisely because they are read-only; this one is not, and that is the whole
difference:

```
$ROUND = 1
loop:
  mutation-check --implemented --targets <$OWN's production files>
                 --node-ids <stage 4 + 7> --tests <…> --command <…>

  MUTATION CHECK PINNED: n of n      -> converged, go to stage 10
  MUTATION CHECK NOT PINNED: n of m  -> write a test pinning each named symbol,
                                        confirm it is RED against the same mutation,
                                        commit, then run another round
  MUTATION CHECK BLOCKED: <r>        -> stop this ticket, surface <r>
  anything else                      -> stop, surface the raw verdict verbatim

  if $ROUND >= 3  -> capped: stop the ticket, report every symbol still unpinned
  $ROUND += 1
```

**One span per round**, never one span per loop — same rule and same reason as stage 7's
adversary; `run-jsonl.md` states it once and this does not restate it.

**Authoring the pinning test is yours, exactly as stage 7's gap tests are.** Adding a test to
a non-frozen file is already legal, so nothing about the frozen-test rule, the tamper diff or
the file-map kill is relaxed to make room for it. Confirm the new test is **red against the
surviving mutation** before you commit it — a pinning test that was never red pins nothing,
and writing one is the same defect this pass exists to catch, committed by the fixer.

**Targets come from `$OWN`, never `$BASE`.** The set is this branch's production changes. A
symbol the branch did not touch is somebody else's debt, and mutating it buries this ticket's
finding in noise.

**Mode:**

- **`$REFACTOR`** — **run it, and report rather than fix.** A refactor's whole claim is that
  behaviour is unchanged and the suite proves it, so this is the sharpest possible test of that
  claim. But `implement --refactor` may modify no test file at all, so a surviving mutation is
  reported as a finding against the ticket and **does not open a fix round** — record
  `PINNING REPORTED: <n> unpinned — refactor ticket, no test may be added` and carry it to the
  final report.
- **`$BACKFILL`** — **skipped, and say so.** `implement` is not launched and there is no
  production diff, so there is nothing this branch wrote to mutate. Record
  `PINNING SKIPPED: backfill ticket — no production diff`. The `mutation-check` that carries a
  backfill ticket is stage 5's, in `--backfill` mode, and it is already the gate there.

**This is a mechanical gate and mechanical gates run in every mode** — see above. What the
mode changes is whether a finding opens a fix round, never whether the check runs.

**Record the round count and the wall-clock.** A gate that materially lengthens the run is a
trade to make knowingly. If it turns out to cost more than the 10b rounds it saves, that is a
finding about this stage, and the spans are what make it arguable rather than felt.

## Stage 10 — review

```
$ROUND = 1
loop:
  Agent(... prompt: invoke slopstop:review with
        "--scope <PR-or-ref-range> --mode $MODE --frozen $FROZEN")

  # Branch on the LEADING TOKEN: everything from REVIEW up to the first `|`.
  # Anything after the `|` is the severity split — data for the record, never for the branch.

  REVIEW CLEAN         -> converged, go to stage 11
  REVIEW APPLIED: <n>  -> commit and push this round's fixes, then continue
  REVIEW BLOCKED: <r>  -> stop this ticket, surface <r>, do not retry
  anything else        -> stop, surface the raw verdict verbatim; never assume it applied

  if $ROUND >= 5       -> capped: report the LAST round's findings and stop this ticket
  $ROUND += 1
```

**Branch on the token, record the whole line.** `review` returns
`REVIEW CLEAN | reported <r> (blocker <b>, major <M>, minor <m>)` and
`REVIEW APPLIED: <n> | applied <n> (…) | reported <r> (…)`; `REVIEW BLOCKED: <reason>` takes
no counts. **Split on the first `|` and match the left side** — the token is unchanged from
what it has always been, so this reads correctly whether or not the worker emits a suffix.
A `review` that returns a bare `REVIEW CLEAN` is not a malformed verdict; it is an older
worker, and it branches identically.

**Put the verdict line verbatim into the span's `result`.** Not a paraphrase, not a
count you recomputed — the line as returned, counts included:

```json
{"ticket":"BILL-544","event":"span","stage":"review","state":"finished","round":1,
 "result":"REVIEW CLEAN | reported 3 (blocker 0, major 1, minor 2)"}
```

This is the only record of what the round found: the worker applies with `Edit` and hands
nothing back, so a summary that drops the counts destroys the evidence rather than
compressing it.

**And transcribe the same numbers into a `findings` object on that close** — schema in
`run-jsonl.md`, not restated here. Copy them from the verdict line; never re-derive a severity
the worker did not state. `result` stays on the line beside `findings` so the transcription
can be audited against its source. **An absent `findings` and an all-zero one are different
facts** and invariant 8 fails a close that has neither.

The same two rules apply to the `handoff` span at stage 10b, which runs this same worker, and
to every `adversary` round at stage 7.

**A `REVIEW CLEAN` carrying a reported `blocker` is a contract violation, not a pass.** A
confirmed blocker is never left unfixed in either mode, so that line cannot be true. Take
the `anything else` exit and surface it verbatim. This is the shape every lethal gate
failure in this repo has had: something measured zero and zero read as fine.

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

   **Record the re-check inside the `merge` span, not as a `pr` one.** It is a precondition of
   merging, not a second run of the `pr` stage, so it belongs in `merge`'s `started` result:
   *"blessing re-checked before merging: branch tip <sha> == blessed_sha"*. PLTF-2565 wrote it
   that way and pairs clean. SOP-261 wrote it as a second `pr` `finished` with no `started`,
   which is both the wrong stage and an orphan close, and that file's whole 3h00m05s of timing
   is unreportable as a result.

   **If the tip HAS advanced and you go back to 10b, that re-verification opens its own
   spans** — a second `tamper`, a second `handoff`. A second run is a second span; never
   reopen or re-close the first. See `run-jsonl.md`, invariant 1's close-time mirror.
1. `gh pr merge --merge --delete-branch` against `$OWNER/$REPO`. **Never** `--squash`,
   `--rebase`, or `--admin`. Read the PR back and assert `state == "MERGED"` before believing
   it; capture `$MERGE_COMMIT`.

   **Read `mergeStateStatus` first, and name the reason yourself when it is not mergeable.**
   One call — `gh pr view $PR --json mergeStateStatus,statusCheckRollup,reviewDecision` — and
   translate it before spending the merge attempt:

   | `mergeStateStatus` | what it means | do |
   |---|---|---|
   | `CLEAN` | mergeable, checks green | merge |
   | `UNSTABLE` | a non-required check is failing or **still queued** | merge — but say which check, in the report |
   | `BLOCKED` | required reviews or required checks unsatisfied | **stop this ticket**, naming the unmet requirement |
   | `BEHIND` | base has advanced | `git merge <base>` into the branch per the conflict rule, then re-verify from stage 10b — the blessing is void |
   | `DIRTY` | conflicts | **stop this ticket**, naming the conflicting files |
   | `UNKNOWN` | GitHub has not computed it yet | wait ~5s and ask **once** more; if still `UNKNOWN`, merge and let the read-back decide — never treat it as a stop |

   **`UNKNOWN` is not a failure and must not become one.** GitHub computes this field
   asynchronously, so it is the normal answer for a PR opened seconds ago — measured
   2026-08-09, `gh pr view --json mergeStateStatus` returned `UNKNOWN` on a real PR of this
   repo. Stopping a ticket on it would invent a blocker out of a value that means "ask again",
   which is worse than the cryptic error this whole check exists to replace.

   **Reading it does not replace the read-back assertion**; it is not a substitute for
   checking what actually happened. GitHub computes `mergeStateStatus` asynchronously and it
   can be stale or `UNKNOWN` at the moment you ask, so a merge can still be refused after a
   `CLEAN`. Do both: predict, then verify.

   **Why bother, when the read-back already catches a refused merge.** Because it catches it
   as a `gh` exit code and an API error string, and the next thing a run does with that is
   guess. Naming the state turns *"the merge failed"* into *"BLOCKED: required check `build`
   has not reported"*, which is the difference between a human fixing it in a minute and a
   run reporting a mystery. Measured on this repo 2026-08-09: a queued CodeRabbit check left
   a PR `UNSTABLE`, the merge was refused — and the orchestrator posted the ticket's closing
   comment anyway and had to reopen it. `UNSTABLE` is in the table above as *merge and say
   so* precisely because of that run.

   **`--admin` is still never the answer to any row of that table.** A required check that has
   not reported is a check that has not reported; forcing past it converts a visible stop into
   an invisible one.
2. **Score the DoD** before advancing anything. `unverifiable` is not a polite `met` — any
   `not-met` or `unverifiable` blocks and goes to the human. The scoring rules are one
   definition and live in `references/`, not here:
   → Read `~/.claude/commands/slopstop-run-refs/dod-scoring.md`
3. **Advance the ticket, per `$POST_MERGE_DONE`** (`[workflow].post_merge_done`, default
   `true`):

   - **`true`** — take the ticket to its **terminal** state, however many transitions that
     is. For GitHub: close it and swap `$IN_PROGRESS_LABEL` for the done label.
   - **`false`** — advance **exactly one** state and stop there. The ticket is deliberately
     parked, not forgotten: merged code that still needs verification a machine cannot do.
     The motivating case is on-device mobile testing — an Expo/EAS build has to reach real
     hardware, possibly days later, and a human moves the ticket to done once it passes.

   **Ensure a label exists before applying it.** On GitHub, applying a label that does not
   exist fails the whole edit — measured 2026-08-09: `gh issue edit 461 --add-label
   slopstop-blech` → `failed to update …: 'slopstop-blech' not found`, with the label not
   created and the issue's existing labels untouched. So check, create if absent, then apply:

   ```bash
   $GH label list --repo "$OWNER/$REPO" --json name -q '.[].name'   # exact match
   $GH label create "<label>" --repo "$OWNER/$REPO"                 # only if absent
   $GH issue edit "$N" --repo "$OWNER/$REPO" --add-label "<label>"
   ```

   Idempotent: an existing label is used as-is, never recreated or recoloured. The one
   definition of per-backend label creation — including why JIRA needs no step and Linear
   does — lives in `create-ticket/SKILL.md` Step 3a.

   **This is why `gh-init` can stay optional.** It seeds these labels for a fresh project as a
   convenience, and nothing depends on it having run *because this step does not need it to*.
   Before 2026-08-09 that claim was aspirational: a project that skipped `gh-init` merged its
   code here and then failed to advance the ticket, having been told to apply a label it was
   forbidden to create.

   **Only slopstop's own labels.** This creates the configured status labels and slopstop's two
   mode labels — nothing else. A label a human named in a ticket body is not slopstop's to
   invent.

   Closure happens here, through the API. Never write `Closes #N` in a PR body — GitHub
   would auto-close, which both skips the label half of this step *and* overrides
   `post_merge_done = false` entirely, terminating a ticket that was meant to wait.

   When you park a ticket, say so in the final report under its own heading — `parked
   awaiting <state>` — never folded in with the completed ones. A parked ticket looks
   identical to a forgotten one unless the report distinguishes them, and the whole point
   of the flag is that someone comes back to it later.
3a. **Report issue links that contradict the ticket's `Blocked by:` header.** Read the
   ticket's native relations once — you already compare them at intake — and compare each
   against the header you parsed. **Name every disagreement, with the link id**, in the final
   report:

   ```
   Stale links on PLTF-2565 (prose header says: Blocked by: nothing):
     12517  PLTF-2563 blocks PLTF-2565   — PLTF-2563 merged as 1fe73f0
     12518  PLTF-2565 blocks PLTF-2566   — discharged
   ```

   **This never stops or fails anything.** The prose header governs scheduling, so a stale
   link is a board-display disagreement, not a run-blocking one — and slopstop cannot fix it
   anyway on the backend where it happens. **On JIRA, an issue link cannot be removed by the
   available tooling** — `editJiraIssue` reaches only the `fields` path and removal needs the
   REST `update` path. Do not try it: the verbatim failure and its cause are recorded once,
   beside the code that creates the links, in `create-ticket/SKILL.md` Step 3. It has been
   re-derived by retrying twice already.

   So the report *is* the deliverable here: a link nobody can delete and nobody has named is
   a second source of truth that quietly disagrees with the first, and a human reading the
   board draws the wrong conclusion from it. Say it out loud instead. Where slopstop *can*
   write — a ticket comment, or the prose header — recording the discharge and the stale link
   id is worth doing; it is the only correction available.

   **Backend-scoped.** This applies as written to JIRA. Linear can remove a relation through
   its API (`removeBlockedBy` / `removeBlocks` / `removeRelatedTo`), so there a contradiction
   is fixable rather than permanent — still report it, and say that it is fixable. GitHub has
   no native `Blocked by` relation at all: its blockers are body text, so there is nothing to
   contradict and nothing to report.

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

## Re-scoring after a ticket-defect `not-met`

**A ticket can stop at close because the *ticket* was wrong, not the work.** `dod-scoring.md`
is right to say so — *"an item the implementation satisfies in spirit but not as written is
`not-met`; the fix belongs in the ticket, not in a generous reading"* — and the remedy it
prescribes is to amend the ticket. This is where the amendment lands.

Without this path there is nowhere to land it. Re-running `:run` is **unsafe** on a merged
ticket: stage 3 cuts a branch, and the branch already exists locally and on every remote
while the PR has merged. PLTF-2565 hit exactly this, and its re-score, ticket transition and
archive were all done by hand — the right outcome reached by the wrong route.

### Recognise the state — three conditions, all from `run.jsonl`

A ticket is **re-scorable** when all three hold:

1. `merge` has a `finished` span. The work is landed.
2. The **latest** `close` span is `failed`. The run stopped where scoring happens.
3. `run_closed` is the last record. The run is over, not interrupted.

**Condition 2 is the latest `close`, not any `close`.** A log that has already been through
this path holds *both* a `failed` close and a later `finished` one — that is the point of
appending rather than overwriting. Testing whether a `failed` close exists anywhere marks
every successfully re-scored run as re-scorable again, forever. Found by running this rule
against PLTF-2565's archive, which is exactly such a log.

PLTF-2565's archived log is the reference case, and it reads:

```
span  merge       finished  13:14:44   PR 109 read back: state=MERGED, mergeCommit=1504f14…
span  close       started   13:14:44
span  close       failed    13:15:40   DoD 5 of 6 met, 1 not-met -> ticket STOPPED at close
note  run_closed  …         13:16:07   1 merged (1504f14), 1 stopped at close (bullet 5 not-met)
```

All three conditions hold: `merge` finished, latest `close` failed, `run_closed` last.
Re-scorable.

The **archived** copy of that same file goes on past this point — it carries the re-score
that was done by hand, so its latest `close` is `finished` and it correctly refuses a second
one. Same file, two states, and the rule tells them apart.

### Refuse it otherwise, and name which condition failed

| what the log shows | verdict |
|---|---|
| no `merge` span, or `merge` `failed`, or `merge` `started` with no close | **refuse** — `RESCORE REFUSED: merge never finished; this is not a close-out path` |
| `close` `finished` | **refuse** — `RESCORE REFUSED: close already succeeded; nothing was stopped` |
| no `run_closed`, or a span still open | **refuse** — `RESCORE REFUSED: run was interrupted, not stopped — resume it instead` |
| branch tip has moved since the merge commit | **refuse** — `RESCORE REFUSED: branch state has moved; the work changed` |

**Name the condition, never just "refused".** These are four different situations with four
different next steps, and a bare refusal sends the reader to re-derive which one they are in.

**This is a close-out path, not a way to skip gates.** That is what every refusal above is
protecting. If the *work* needs to change, this is the wrong door — go back through the
normal stages.

### What re-scoring does, and does not, re-run

**Re-run:** DoD scoring, then stages 13–15 from step 2 onward — advance the ticket, write the
DoD confirmation, launch `archive`, close the log, move the directory.

**Do not re-run** investigate, implement, gates, review, handoff, PR, or merge. They
completed, their evidence is in the record, and re-running them against a merged branch
measures something other than what shipped.

### Score the ticket as it is now

Re-fetch the ticket body from the backend before scoring. **The whole point is that the DoD
changed** — scoring a cached copy re-derives the original `not-met` and the path achieves
nothing. Read the labels again too: the mode is a label, and a ticket amended at the same
time may have had it changed.

### The original `not-met` survives — this is a requirement, not a courtesy

A re-score **appends**. It never overwrites, edits, or deletes the failed `close` span, and
it never rewrites the DoD confirmation that recorded the original verdict.

Write the second `close` span with the reason in its `result`, so one pass over the file
still reconstructs the whole run:

```
span  close       started   13:27:42   re-open of close after the ticket-level fix; the
                                       round-1 close failed on DoD bullet 5
note  close       …         13:27:42   ticket changes made at the owner's request: DoD
                                       bullet 5 rescoped to …
span  close       finished  13:27:42   DoD re-scored 6 of 6 MET against the rescoped bullet 5.
                                       The measurement did not change — the item did.
```

**A ticket that was fixed must not read as one that was always green.** The pre-amendment
`not-met`, the amendment, and the re-score are three facts and the record keeps all three.
Carry the same distinction into the DoD confirmation and the final report: say *"6 of 6 met
after the ticket-level fix; the round-1 `not-met` on bullet 5 stands in the record as what
actually happened"*, not *"6 of 6 met"*.

> **Watch the span duration.** PLTF-2565's re-scored `close` span opened and closed on the
> same second, which invariant 5 flags as suspect — a zero-second span is usually a stamp
> written from memory. Here the scoring genuinely was near-instant, the human having already
> made the decision during the preceding 12 minutes. Bracket the human's part as
> `waiting_for_user` when you are the one waiting on it; that is where the time actually
> went, and on PLTF-2565 it went unrecorded and inflated the orchestrator's inline figure
> (`run-jsonl.md`, "Computing time").

**Re-scoring never edits the ticket.** Authoring is `:tickets`' work. The amendment arrives
already made; this path reads it, scores it, and closes out.

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

→ Read `~/.claude/commands/slopstop-run-refs/failure-and-salvage.md`

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
