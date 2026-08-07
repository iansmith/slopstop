# slopstop commands

**Six slash commands.** In Claude Code (CLI) they are namespaced `/slopstop:<name>`; the Claude
Desktop standalone install renames them `/slopstop-<name>`.

slopstop v4 is **slopstop for autonomous agents**. The tool drives coding work end to end with no
human in the loop, while keeping every anti-slop guarantee it has ever made. That is why the menu
is short: there is one lifecycle command, two commands that produce the tickets it consumes, and
three utilities.

| | |
|---|---|
| **The lifecycle** | [`:run`](#slopstoprun-ticket) |
| **Getting tickets worth running** | [`:design`](#slopstopdesign-topic) · [`:tickets`](#slopstoptickets-run-id) · [`:grill`](#slopstopgrill) |
| **Utilities** | [`:gh-init`](#slopstopgh-init) · [`:doc-sync`](#slopstopdoc-sync) |

Everything else you may remember — `:start`, `:plan`, `:pr`, `:merge`, `:archive`, `:document`,
`:update`, `:update-ticket`, `:focus`, `:create-gh`, `:single-ticket` — is gone. See
[What happened to the old commands](#what-happened-to-the-old-commands).

Eleven further skills ship in the plugin but are **not commands**: they are the
[workers](#the-eleven-workers) an orchestrator launches inside a run.

---

# The lifecycle

<a id="slopstoprun-ticket"></a>
## `/slopstop:run <TICKET> [TICKET...]` — the single lifecycle entry point

```
/slopstop:run BILL-501
/slopstop:run BILL-501 BILL-502 BILL-503
/slopstop:run BILL-501 --constraint "database layer only"
/slopstop:run BILL-501 --interactive
```

Takes one or more ticket keys and drives **each one from "open" to "merged and archived"**,
interleaving them so ticket A can be in review while ticket B is still writing red tests.

This replaces a chain that used to need a human at every joint. `:start` → `:plan` → `:pr` →
`:merge` → `:archive` were five commands, each typically run in a fresh session, each carrying its
own resume state, its own confirmation step, and its own "Stage end / `Next:`" handoff bookkeeping.
That machinery existed *only* because the stages were separate sessions. One orchestrator does not
hand off to itself, so all of it is deleted.

### The fifteen stages

**W** = a worker launched as an agent; **I** = the orchestrator's own inline work, no agent.

| # | stage | kind | what happens |
|---|---|---|---|
| 1 | `intake` | I | fetch the ticket, its five sections and its DoD; seed the tracking dir; open `run.jsonl` |
| 2 | `investigate` | W | findings + a **predicted file map** — run for all N tickets before anything else |
| 3 | `branch` | I | ticket → in progress; `git switch -c <type>/<TICKET>` off the base branch |
| 4 | `red-tests` | W | failing tests for the ticket's contract, with node-ids, test command, stubs, observed failure output |
| 5 | `mutation-check` | W | proves each red test is red for the **right** reason |
| 6 | `phase0-commit` | I | commit the red tests — and capture `$FROZEN`, the frozen-test sha |
| 7 | `adversary` | W+I | the gap-finding loop (≤3 rounds), the add decision, gap-test authoring, RED re-verify, gap commit |
| 8 | `implement` | W | make the tests green. It may not touch the tests |
| 9 | `gates` | W×3 | `slop-check`, `vacuity-check`, `complexity-check` — launched together, they are independent |
| 10 | `review` | W | clean-context review, looping until `REVIEW CLEAN`, cap 5 rounds |
| 10a | `size` | I | record `lines_changed`, `files_changed`, `paths`, provisional `tier` — see [`run.jsonl`](#runjsonl) |
| 11 | `pr` | I | commit, push, open the PR |
| 12 | `bot-read` | I | read existing bot comments **once**. Never poll |
| 13 | `merge` | I | serial across tickets; `gh pr merge --merge --delete-branch` |
| 14 | `close` | I | score the DoD, advance the ticket state, write the DoD confirmation |
| 15 | `archive` | W+I | push the tracking files to the ticket, close the log, move the dir to the archive |

Stage 9 runs **after** `implement`, deliberately: the stage-7 adversary cannot see tests written
later, and `vacuity-check` here is what covers them.

A prose-only change has one legitimate empty outcome at stage 4 — `PHASE 0: none` — and then
stages 5–7 are skipped and every consumer of `$FROZEN` is told so explicitly rather than handed a
guess.

### Scheduling N tickets

1. **Fan out `investigate` for all N tickets first.** It is read-only, so it is always safe and
   always parallel. Collect each ticket's predicted file map.
2. **Schedule by overlap.** Tickets whose predicted file maps are disjoint run stages 3–12
   concurrently; overlapping ones run serially. Prediction is never perfect — this buys efficiency,
   not correctness.
3. **Merge serially, always**, regardless of overlap. One PR at a time. On conflict, merge the base
   branch *into* the losing branch, resolve, re-run that ticket's tests, push, merge. Never rebase
   a pushed branch.

One ticket ⇄ one branch ⇄ one PR. Never two tickets on a branch, never a branch off another
ticket's branch.

### Autonomous by default

`:run` exists to drive tickets unattended, so unattended is the default. There is **one** switch —
`--interactive` — and no `[autonomous]` master block and no per-gate `on_*` config; those seven
knobs were deleted 2026-08-06. They existed because seven separate skills each needed their own
policy at their own gate. One orchestrator has one decision point.

> **`--interactive` is declared, not yet implemented.** The flag and its behaviour are specified in
> `skills/run/SKILL.md` — the table below is that specification — but the interactive paths have
> not been built out or exercised. Treat the autonomous column as what actually runs today.

| | autonomous (default) | `--interactive` |
|---|---|---|
| adversary gap tests | add all | ask `add all / add selected <n,…> / skip` |
| gap test that comes up green | stop the ticket | ask `revise / continue / abort` |
| adversary still `FAIL` at round 3 | stop the ticket | present findings, ask |
| `GOAL DEFECT` | stop the ticket | present verbatim, ask |
| DoD item `not-met` / `unverifiable` | stop the ticket | present, ask |
| 🔴 complexity breach | stop the ticket | present, ask |
| merge conflict | merge base in, resolve, re-run tests | same, then confirm |

**"Stop the ticket" is not "wait".** Its current span closes `failed`, its branch and tracking dir
are left intact, **every other ticket keeps running**, and the whole stopped set is reported at the
end with what each one needs. A stalled autonomous run is precisely the failure mode this default
exists to avoid.

A ticket that fails implementation twice may be a **ticket** defect rather than a code defect;
`:run` says so when it stops one, and points at
[`:tickets --rewrite`](#slopstoptickets-run-id). `:run` never rewrites a ticket itself — authoring
is `:tickets`' work.

### Mechanical gates never soften

A **judgment** gate may be waved past by a human who has read it. A **mechanical** gate may not,
and has no permissive setting in either mode:

- the **red-test tamper check** (`$FROZEN`),
- **vacuity** — proving a test would have failed before the branch,
- **slop findings** — tests rewritten to pass, assertions inverted, swallowed errors.

Each stops the ticket, always. This is the rule the deleted `[autonomous]` block stated about
itself, kept as behaviour now the knobs are gone: *any knob whose permissive value is the only
fleet-viable one silently disables its gate for exactly the agents it exists to police.* **A gate
that waves through for the cases it exists to police is worse than no gate, because it reports
clean.**

`SKIPPED`, `BLOCKED`, and `could-not-determine` are reported as themselves — never rounded up to a
pass.

### Arguments

| | |
|---|---|
| `<TICKET> [TICKET...]` | one or more keys matching `^$PREFIX-\d+$`. Empty → asks; never guessed from the branch or the backlog. A malformed key is refused **by name** and the rest of the list still runs |
| `--constraint "<phrase>"` | applies to every ticket: passed verbatim to `investigate`, a hard scope everywhere else |
| `--interactive` | stop at every gate and ask (see the note above) |

---

# Getting tickets worth running

`:design` and `:tickets` are the other two orchestrators. Like `:run` they launch workers and
write `run.jsonl` — but their run log lives in the run dir (`scratch/runs/<run-id>/`), not a
ticket's tracking dir. Both run at declared model tiers and **hard-stop if the session's model does
not match**: `:design` on huge, `:tickets` on large. See [CONFIG.md](CONFIG.md) for `[tiers]` and
`[stage_tiers]`.

<a id="slopstopdesign-topic"></a>
## `/slopstop:design <topic>` — Stage 1: PRD and feature charter

```
/slopstop:design I want a CLI that stores key-value pairs in a local JSON file …
/slopstop:design --spec docs/api-contract.md payments retry policy
```

Grills you to shared understanding, then writes a **PRD** and a **feature charter** into a fresh
run directory under `scratch/runs/<run-id>/`, and stops at gate **G-design**. Mints the run-id that
tags every artifact downstream. Cuts no tickets and writes no code. **Huge tier only.**

Every decision in the PRD is classified against the resolved spec — `SPEC` (the source settles it,
with the quote), `DERIVED` (follows from a quote, with the reasoning step), or `UNDERDETERMINED`
(the source does not settle it, with the alternatives). `UNDERDETERMINED` is not a failure; a PRD
that *pretends* the spec answered everything is. `--spec <path>` is repeatable; with nothing to
resolve the run records `SPEC: none — greenfield` and continues.

The stage boundary is **artifact-only**: Stage 2 reads `prd.md` and `charter.md`, never this
conversation.

<a id="slopstoptickets-run-id"></a>
## `/slopstop:tickets <run-id>` — Stage 2: the ticket tree

```
/slopstop:tickets kvstore-20260725-1001
/slopstop:tickets --retrofit BILL-204
/slopstop:tickets --rewrite BILL-204
/slopstop:tickets --refactor linkWithObjs cmd/link/arfmt.go:archiveRead
```

Reads the PRD and charter from the run dir and cuts an umbrella/leaf ticket tree to the
**five-section leaf standard** — each leaf carrying 2–5 numbered observable behaviors, an explicit
file map, and test expectations, so an agent with no conversation history can implement it. Drafts
go to disk first; the ticket system only ever receives an approved tree. Then it drives a
**huge-tier adversary loop** over the drafts (≤3 correction rounds), whose job is to prove the
tickets wrong, and stops at gate **G-tickets**. Launches no implementation work. **Large tier
only.**

A finding it disagrees with is **argued in the correction note**, never silently dropped — a
dropped finding looks identical to a fixed one. A `GOAL DEFECT` verdict means the *PRD* is wrong,
which is a Stage 1 defect and a human's decision; it goes up unmodified and immediately.

### `--retrofit <TICKET>`

Brings **one existing ticket** up to the five-section standard, so `:run` can take a ticket that
was written by someone else or written fast. Fetches the ticket (body and comments only — comments
are context, never authority), grills toward the missing structure, drafts the five sections, runs
the adversary loop against the *original ticket* as its goals, then pushes the new body in place
with the original preserved verbatim below a separator. Creates nothing and **never touches ticket
status** — retrofitting is not progress. (Absorbed from the former `:single-ticket`.)

### `--rewrite <TICKET>`

Repairs a ticket that `:run` stopped after **two** failed implementations and diagnosed as a ticket
defect rather than a code defect.

The outgoing body is captured verbatim first, before anything is drafted. The new body must cite
the **specific** failure — the file:line the implementation produced, and the quoted DoD item or
file-map entry that did not survive contact with the code; a generic rewrite changes the wording
without changing what was underspecified. Then the **mandatory scope-subtraction check**: the
adversary runs at the `rewrite_delta_check` tier with the new draft as target and the captured body
as `--baseline`. A `FAIL` means scope was subtracted — the DoD quietly shrunk until the existing
code would satisfy it — and the subtracted items are restored and the draft redone. Only on `PASS`
is the new body published, with the title marked `(V2)`, then `(V3)`.

This is the same anti-weakening rule the `implement` worker follows about tests, one level up:
**you may not shrink the contract to make it satisfiable.**

### `--refactor <fn> [<fn>…]`

Cuts **one** ticket whose Definition of Done is *nothing broke*, from a list of function
names — normally pasted straight out of `complexity-check`'s exempt heading, which lists the
violations the CC gate declined to block because this branch did not make them worse. Names
may be given bare or as `<path>:<fn>`; a bare name matching more than one definition stops
with the candidates listed rather than guessing.

The drafted ticket carries the literal marker `**Mode:** refactor`, which is what `:run`
reads at intake to take the refactor path: no phase-0 tests, no mutation or adversary round
over them, no `vacuity-check`. Its observable behaviors are the CC targets with their
measured before-values, and its DoD is the invariant in three parts — **the suite green
before, the same suite green after, and no test file modified**. Two of three is a failure:
a suite green at both ends because a failing test disappeared in the middle is green and
proves nothing.

Why it exists: a refactor and a feature prove themselves by opposite evidence, and until
`cc_exempt_pre_existing` defaulted to `true` the CC gate forced them into one branch — the
implementer decomposed a pre-existing giant to get past the gate, and the refactor landed
with no DoD item and no guard. This mode is where that work goes instead.

<a id="slopstopgrill"></a>
## `/slopstop:grill [topic]` — interview a plan until it holds

```
/slopstop:grill
/slopstop:grill <a plan, or a rough idea>
```

Interviews you relentlessly about a plan or design, resolving each branch of the decision tree
until nothing ambiguous is left. One question at a time, never a batched questionnaire; every
question comes with a recommended answer and the reasoning behind it, so you are choosing between
argued positions rather than facing a blank prompt. Where a question can be answered by reading the
codebase, it reads the codebase instead of asking.

Usable standalone, and also called by [`:design`](#slopstopdesign-topic) (Step 2) and by
[`:tickets --retrofit`](#slopstoptickets-run-id).

---

# Utilities

<a id="slopstopgh-init"></a>
## `/slopstop:gh-init` — bootstrap a GitHub repo

```
/slopstop:gh-init
/slopstop:gh-init --workflow 3 --prefix BILL
```

Creates the status labels the workflow needs, writes a `.project-conf.toml` for the repo, and seeds
the gitignored `scratch/` and `.slopstop/` directories. **Idempotent** — safe to re-run. The fast
path for step 1 of setting up a new project; see [SETUP-GUIDE.md](SETUP-GUIDE.md) for the manual
equivalent. `--workflow` and `--prefix` skip the two interactive questions, so it runs unattended.

<a id="slopstopdoc-sync"></a>
## `/slopstop:doc-sync` — mirror `design/` to the project's doc store

```
/slopstop:doc-sync
```

One-way push of all `design/*.md` files to the project's documentation store — GitHub wiki (for
`system = "github"`) or Linear Docs (for `system = "linear"`). `design/` is the source of truth;
the doc-store copy is overwritten on each sync. Orphan pages — previously synced, now deleted from
`design/` — are pruned.

- Warns if `design/` has uncommitted changes (it pushes working-tree state, not the committed
  version).
- For GitHub: the wiki must be initialized via the web UI before the first sync — `git push` to an
  uninitialized wiki fails.
- **Do not run in the same turn as edits to `design/`.** The sync reads source files while
  concurrent writes modify them, producing mid-edit snapshots. Finish all edits first, then sync.

---

<a id="the-eleven-workers"></a>
# The eleven workers — what runs inside a run

**These are not commands.** You do not invoke them; there is no `/slopstop:implement` for a human
to type. They are skills the three orchestrators launch as agents, each one a **leaf**: it takes
explicit arguments, does one thing, returns a result, and interacts with nobody. Workers never
launch workers — if a worker seems to need a sub-worker, that is the orchestrator's job.

They are listed here because knowing what runs inside `:run` is how you read its report, and
because a verdict line quoted at you (`ADVERSARY GOAL DEFECT`, `REVIEW BLOCKED`, `VIOLATIONS: …`)
came from one of these.

| worker | what it does | returns |
|---|---|---|
| `investigate` | map the codebase for one ticket, writing nothing to disk | findings + a **predicted file map** |
| `red-tests` | write the phase-0 failing tests that define the ticket's contract | test files, node-ids, test command, stub paths, observed failure output |
| `mutation-check` | prove each red test is red for the **right** reason — not an import error, a typo, a missing fixture | per-test verdict + `MUTATION CHECK PASS` / `FAIL: n of m` / `BLOCKED` |
| `adversary` | **one** round of attack on a target against its stated goals, verifying every claim against the real repo | numbered findings + `ADVERSARY PASS` / `FAIL: n` / `GOAL DEFECT: n` / `BLOCKED` |
| `implement` | make the failing tests pass. Writes source only, **never touches the tests** | changes made, tests before/after, findings reported-not-fixed |
| `review` | clean-context review of the diff, in its own forked context so the session that wrote the code never reviews it | `REVIEW CLEAN` / `APPLIED: n` / `BLOCKED` |
| `slop-check` | judgment pass for AI slop — tests rewritten to pass, inverted assertions, tautologies, swallowed errors. Reports only, never fixes | findings with signal + severity + verdict |
| `vacuity-check` | **mechanically prove** whether each test would already have passed before the branch, by re-running it at the base commit in a scratch worktree | per-node-id `vacuous` / `meaningful` / `could-not-determine` + verdict |
| `complexity-check` | cyclomatic-complexity gate over the diff (lizard), against thresholds the orchestrator passes in | breaching functions + `CC CLEAN` / `VIOLATIONS: …` / `SKIPPED` / `BLOCKED` |
| `create-ticket` | publish drafted tickets — the only place backend-specific creation lives | letter→key map + `CREATE CLEAN` / `PARTIAL` / `BLOCKED` |
| `archive` | push each tracking file to the ticket as its own comment. Moves nothing, deletes nothing | per-file push report + `ARCHIVE CLEAN` / `PARTIAL` / `BLOCKED` |

`slop-check` and `vacuity-check` are **complementary, not redundant**. `slop-check` asks the
vacuity question as a reasoned read — "what would have to break for this to go red?" —
`vacuity-check` runs the test against the base commit and *proves* it. The judgment pass catches
what no mechanism can; the mechanical pass catches what a confident reader talks themselves out of.

Three rules govern the whole roster, and they are why the workers stay this small:

- **One reader of config.** The orchestrator reads `.project-conf.toml` and passes every resolved
  value as an explicit argument. **A worker given no value blocks; it never falls back to a default
  it carries.** Two readers of one config is two answers to one question.
- **One writer of state.** The orchestrator writes `run.jsonl`; no worker writes it and no worker
  resolves a tracking dir. A worker that needs something persisted returns it.
- **Checking work runs one tier above the work it checks.** `ticket_adversary` defaults to huge
  while `tickets` is large. That ladder is the point of `[stage_tiers]`; it is never flattened.

Every worker can return `BLOCKED`, which means *the arguments were wrong* — so it does **not**
consume a round of any loop, and a caller that treats it as a `FAIL` will burn its cap without ever
running the check.

---

<a id="runjsonl"></a>
# `run.jsonl` — state, resume point, and timing in one file

Every orchestrator records **each stage transition, timestamped**, into an append-only JSONL log:
`:design` and `:tickets` into the run dir, `:run` into **each ticket's own tracking dir**, one file
per ticket. It is simultaneously three things, which is why there is only one of it:

1. **The state machine** — where each ticket has got to.
2. **The resume point** — a long multi-ticket run gets compacted, and anything the orchestrator
   only *remembered* is gone. State lives on disk: read before acting, append after.
3. **The timing record** — every transition is timestamped by definition, so the log read end to
   end *is* the timing data. There is no second artifact.

```json
{"ticket":"BILL-501","stage":"red-tests","event":"started","at":"2026-08-06T14:02:11Z"}
{"ticket":"BILL-501","stage":"red-tests","event":"finished","at":"2026-08-06T14:07:48Z","result":"4 tests, all red"}
```

**Human waits are spans too, and that is the load-bearing part.** Whenever an orchestrator blocks
on a person it brackets the wait with a `waiting_for_user` span — opened in the same step that
asks, closed in the same step that reads the answer. Wall clock alone is meaningless: one stage
span once measured 45,843 seconds because someone went to bed, and one interactive ticket clocked
550.9 minutes wall against 45.5 minutes of actual agent work. The orchestrator is the thing doing
the blocking, so it is the only thing that can record it, and nothing downstream has to guess.

| quantity | computation |
|---|---|
| wall clock | `last.at − first.at` |
| human idle | `Σ` `waiting_for_user` spans |
| **active** | `wall − human_idle` |
| agent-seconds | `Σ` worker spans — *exceeds* active under parallelism, like CPU-seconds vs elapsed |
| unattributed | active minus the union of attributed spans — **reported, never redistributed** |

**When validation fails, no timing is reported at all** — the unclosed spans are named and the run
stops. A `started` with no close is indistinguishable from a short span unless something looks, and
a broken record must not be able to produce a plausible-looking summary. That is not hypothetical:
the predecessor system wrote a three-key metrics file with no `started_at` and no `completed_at`,
at the wrong path, and it **passed every check that existed** while its numbers flowed downstream
as though complete.

Each ticket also records its **change size** — `lines_changed`, `files_changed`, `paths`, and a
provisional `tier` label — as a `note` once the diff exists. Nothing reads it yet and nothing skips
anything. It is deliberate groundwork: the next feature is **size-based skipping**, shortening the
process when a change is genuinely small, and it is blocked on nothing but timing reliable enough
to correlate cost against size instead of guessing.

Timing can only ever answer half that question, and it is the less important half. Durations tell
you what is *expensive*; they cannot tell you what is *unsafe to skip*, which is a categorical
property of what a gate protects. The mechanical gates above are never skippable at any size, for
any reason — "it was only a small change" is the same excuse as "nobody was watching."

---

<a id="what-happened-to-the-old-commands"></a>
# What happened to the old commands

| gone | where its work went |
|---|---|
| `:start` | `:run` stage 1 (`intake`) and stage 3 (`branch`) |
| `:plan` | `:run` stages 2 and 4–8 — the `investigate`, `red-tests`, `adversary`, and `implement` workers |
| `:update` | deleted with `progress.md`. `run.jsonl` is the checkpoint, mechanically |
| `:pr` | `:run` stages 9–12; its two mechanical gates became the `slop-check` and `complexity-check` workers |
| `:merge` | `:run` stage 13 |
| `:archive` | `:run` stage 15. `archive` survives as a **worker**, not a command |
| `:document` | `:run` stage 15 — the `archive` worker pushes the tracking files to the ticket |
| `:update-ticket` | it was `:update` + `:document` chained; both are gone |
| `:focus` | deleted with the metering router — there is no attribution left to re-point |
| `:create-gh` | not lifecycle work, and removed with the router-era tooling; create issues directly |
| `:single-ticket` | absorbed into [`:tickets --retrofit`](#slopstoptickets-run-id) |

Their handoff machinery — "Autonomous mode" blocks, "Stage end / `Next:`" sections, per-stage
confirm steps, resume modes — is **deleted outright**, not relocated. It was a large fraction of
those skill bodies and existed only because each stage was a separate interactive session that had
to hand off to the next one. `:merge` alone was ten steps, four of them handoff bookkeeping.

> **There is no `/slopstop:pause`.** It appears in older documentation and in draft design notes
> under `design/`, but no such skill has ever shipped. `:run` resumes from `run.jsonl` on disk, so
> there is nothing to checkpoint by hand.

---

## See also

- **[WORKFLOW.md](WORKFLOW.md)** — the lifecycle as one diagram, start to finish.
- **[walkthrough/](walkthrough/)** — a real run, annotated minute by minute.
- **[CONFIG.md](CONFIG.md)** — every `.project-conf.toml` setting these commands read.
- **[SETUP-GUIDE.md](SETUP-GUIDE.md)** — installation, MCP servers, and project initialization.
