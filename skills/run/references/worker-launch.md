# Launching a worker — the one definition

Every orchestrator (`:design`, `:tickets`, `:run`) launches workers this way. Read this
instead of writing your own form. Four different launch dialects is the thing this
reorganization exists to delete.

## The form

```
Agent(subagent_type: "slopstop-effort-<resolved effort>",   # general-purpose if it does not resolve
      model: <resolved: stage → tier → model>,
      isolation: "worktree",                                # every ticket worker; see next section
      description: "<what this launch is> <TICKET>",        # the ticket key is REQUIRED — see below
      prompt: "Invoke Skill({skill: \"slopstop:<worker>\", args: \"<args>\"}) and follow it
               exactly. Return its report verbatim as your result.")
```

**Every `description` ends with the ticket key, without exception.** It is the only thing
that attributes a launch to a ticket. `run.jsonl` is per-ticket; the harness transcript is
not — one session's `subagents/` holds every ticket that session drove.
Why: `derive.py`'s `attribute()` falls back to the last key seen in time order — nearly always
right when tickets run serially, a coin flip when they interleave.

That is the whole mechanism. No headless `claude -p`. No router env vars. No bespoke
per-worker prompt templates — **the worker skill is the prompt**; a template that restates it
is a second copy that will drift.

**`isolation: "worktree"` is a real flag and it is how a worker gets its worktree.**
Why: previously documented as nonexistent (BILL-559, probed) — both the old claim and its
suggested alternative (`EnterWorktree` from a subagent) fail.

**`subagent_type` selects the effort carrier** — `slopstop-effort-<level>` — with
`general-purpose` as the fallback when it does not resolve. Custom types ship via
`install-for-project.sh` (`.claude/agents/`, project scope) and via a plugin's `agents/`
directory.

## Pointing a worker at a worktree

**The worker does not enter a worktree. It is launched into one.** `isolation: "worktree"`
puts the agent in a fresh worktree before its first tool call and pins it there.

The branch differs three ways: the **first** worker of a ticket, every one after it, and a
**read-only** worker that takes no branch at all:

```text
# FIRST worker of a ticket — it renames the branch it was given
Agent(subagent_type: "slopstop-effort-<resolved>", model: <resolved>, isolation: "worktree",
      prompt: "First run `git branch -m <type>/<TICKET>`.
               Then run `pwd` and `git branch --show-current`, and confirm pwd is under
               .claude/worktrees/ and the branch is <type>/<TICKET>.
               If either is wrong, STOP: return
               `<WORKER> BLOCKED: not on the ticket branch in a worktree — <pwd>, <branch>`
               and do NOT invoke the skill.
               Only then invoke Skill({skill: \"slopstop:<worker>\", args: \"…\"}) and
               follow it exactly.
               THEN, BEFORE REPORTING: `git add -A` and commit everything you produced,
               subject `[<TICKET>] <what this stage produced>`. If you produced nothing,
               commit nothing and say so explicitly.
               Return the skill's report verbatim, then end with three lines:
               `WORKTREE: <pwd>`, `BRANCH: <branch>`,
               `COMMIT: <sha>` — or `COMMIT: none — <why nothing was produced>`.")

# EVERY LATER worker — it switches to the branch the previous one committed to
Agent(subagent_type: "slopstop-effort-<resolved>", model: <resolved>, isolation: "worktree",
      prompt: "First run `git switch <type>/<TICKET>`.
               Then run `pwd` and `git branch --show-current`, and confirm pwd is under
               .claude/worktrees/ and the branch is <type>/<TICKET>.
               … same guard, same skill invocation, same commit step, same trailing
               WORKTREE:/BRANCH:/COMMIT: lines.")

# READ-ONLY worker — takes no branch, so any number may run at once
Agent(subagent_type: "slopstop-effort-<resolved>", model: <resolved>, isolation: "worktree",
      prompt: "First run `git switch --detach <TIP-SHA>`.
               Then run `pwd` and `git rev-parse HEAD`, and confirm pwd is under
               .claude/worktrees/ and HEAD is exactly <TIP-SHA>.
               If either is wrong, STOP: return
               `<WORKER> BLOCKED: not at the ticket tip in a worktree — <pwd>, <HEAD>`
               and do NOT invoke the skill.
               Only then invoke Skill({skill: \"slopstop:<worker>\", args: \"…\"}) and
               follow it exactly.
               You are detached and produce nothing: do not commit.
               Return the skill's report verbatim, then end with three lines:
               `WORKTREE: <pwd>`, `BRANCH: detached at <TIP-SHA>`,
               `COMMIT: none — read-only gate`.")
```

**A branch can be checked out in exactly one worktree, so same-branch workers serialize.**
This is why the read-only brief exists. Read-only-ness makes workers safe to run
**detached**, which is what buys the parallelism.
Why: BILL-597 — stage 9 launched three gates onto one branch; two died on `git switch` with
`fatal: '<branch>' is already used by worktree at …`.

**Use read-only only for workers that produce nothing by contract** — `slop-check`,
`vacuity-check`, `complexity-check`, `duplication-check`. A worker that makes something needs the branch.

**The guard is stronger for read-only.** A branch-name check accepts whatever the branch
points at *now*; the tip-sha check pins the exact commit the orchestrator measured.

**`--ignore-other-worktrees` is the wrong answer.** It restores parallelism by weakening the
guard. Named here so it is not re-derived.

**The commit is the handoff.** A worker's worktree is removed when it finishes; anything
uncommitted is gone. The branch is the only thing that survives the boundary.

**The orchestrator verifies the commit from the main worktree before removing anything:**

```bash
git log --oneline <base>..<type>/<TICKET>     # did the branch actually advance?
git -C <worktreePath> status --porcelain      # is anything still uncommitted there?
```

**Trust the two commands, not the report.** A worker reporting `COMMIT: <sha>` on a branch
that did not move is reporting something that did not happen.

**A READ-ONLY worker is exempt from the handoff but not from the check.** It is detached, so
`COMMIT: none — read-only gate` is expected and a branch that did not move is correct. A
dirty `status --porcelain` on a read-only worker means it wrote when its contract says it
cannot — still a stop, for the opposite reason.

**A worktree with uncommitted work is not removed. That is a stop.** Removing it destroys
output; continuing without it hands the next worker a branch missing what it should build on.

**Never resume a worker with `SendMessage` to preserve uncommitted work.** It preserves work
but is not the handoff: a resumed worker re-enters the same context, defeating
fresh-worker-per-stage. It also puts two stages under one `agent_id`, breaking cost
attribution in `hook-events.jsonl`. If the temptation arises, the commit step is missing; fix
that instead.
Why: BILL-562 — a `red-tests` worker ran 19.2 min, left files uncommitted with zero commits,
and the orchestrator resumed it instead of fixing the missing commit step.

**Rename first, switch after — not two spellings of one thing.** A rename leaves no residue.
A switch abandons the auto-created `worktree-agent-<id>` branch; that orphan is the
orchestrator's to delete when it removes the worktree.

**The guard checks `pwd` *and* the branch, and the redundancy is load-bearing.** Right
worktree + wrong branch = changes on someone else's history. Right branch + wrong worktree =
shared checkout. Neither check catches the other's failure.

**Read the worktree path from the worker's report, never from the launch result.**
`worktreeBranch` in the launch result is the launch-time name and is not updated by
rename/switch (BILL-559, probed).

### What was tried and does not work

| shape | result |
|---|---|
| plain `Agent()` from repo root | **refused** — not an isolated worktree |
| `Agent(isolation: "worktree")` then `EnterWorktree(path:)` | **inert** — pin never moves |
| `Agent(cwd: …)` | **silently ignored** — lands in repo root |
| subagent of a session inside a worktree | works, but raises an unsuppressible approval prompt |

`Agent(cwd: …)` is what the second row's error message tells you to do, and it fails silently.

**Isolation is enforced from both sides.** While in a worktree, Claude Code blocks edits
targeting the main checkout, commands whose cwd resolves there, and git redirected into it
(`git -C`, `--git-dir`, `GIT_DIR`, `GIT_WORK_TREE`, `cd` before git). The orchestrator runs
its own main-worktree commands itself — see `handoff-verification.md`.

**One hole: `worktree.symlinkDirectories`.** A symlinked directory is the same physical
directory everywhere. Writes through it are not isolated. Whether Claude Code follows the
link before its path check is **not established** (undocumented, not probed). Assume it does
not. **Symlink only read-mostly, shared-by-design data** — font corpora, fixture trees,
package caches. Never build outputs, never anything two tickets could touch at once.

## The containment contract — in every worktree launch

Universal section 6 says a worktree agent commits only to its own branch. **Necessary, not sufficient.** Each
rule below closes an observed way out of the box:

- **Do not locate "the root."** `git rev-parse --show-toplevel` or walking upward finds the
  shared checkout. (The orchestrator's tracking-dir resolution uses `--git-common-dir`
  deliberately — see `tracking-dir-resolution.md`.)
- **Commit nowhere but this worktree's branch.**
- **Write nothing in another repo or checkout — including untracked and scratch files.**
- **One ticket. Neither expand nor contract it.** A cleanup is not this ticket's work
  (universal section 3). A skipped piece is a `DROP` for 10b to find.

**The first three are enforced by Claude Code's worktree pin.** The fourth is not — it is
caught after the fact by stage 8a's file-map check and 10b's adversary. Prose is the only
control at write time.

### A `BLOCKED` from the worktree guard is terminal — unless `pwd` shows containment held

The orchestrator **stops the ticket**. No relaunch with containment as prose, no absolute
path substitution, no deviation-and-continue.

**Two causes, only one terminal:**

- **Containment failed** — the worker is not where it must be. Terminal.
- **The orchestrator asked for something impossible** — the worker *is* contained but the
  launch was wrong (two workers on one branch, wrong tip sha, missing path). Fix the launch
  and relaunch with the guard untouched.

**The test is mechanical:**

- `pwd` **under `.claude/worktrees/`** — caller error. Fix the launch, relaunch, do not
  charge as an attempt.
- `pwd` **anywhere else or missing** — containment failed. Terminal.

No third branch. A worker's explanation is not a `pwd`.

**What this never licenses:** relaxing the guard, `--ignore-other-worktrees`, containment as
prose, or recording a deviation and continuing.

**`--add-dir` grants are the orchestrator's to make** where a worker legitimately needs a
path outside its worktree.

## Model — resolved by the orchestrator, passed explicitly

Two hops from `.project-conf.toml`: **stage -> tier -> model**.

`[stage_tiers]` maps stage to tier name; `[tiers.<name>]` maps that to model family and
optional version pin. Missing keys take documented defaults (`CONFIG.md`).

Pass the resolved model on the `Agent()` call. **Do not put `model` in a worker skill's
frontmatter** — `Skill()` has no model parameter, so it would be a fleet-wide constant that
silently breaks every project using `[tiers]`.

**Adversarial/checking work runs one tier above the work it checks.** That ladder is the
point of `[stage_tiers]`.

## Effort — carried by the subagent type

`Agent()` has no `effort` parameter. Effort comes from the subagent definition's frontmatter
(`effort` field, options: `low`/`medium`/`high`/`xhigh`/`max`). Slopstop ships one
definition per level — `slopstop-effort-low` through `slopstop-effort-max`. `model` still
travels on the call; definitions set none — tier x effort with **five files instead of
twenty**.

**Effort resolves from `[tiers.<name>].effort`, defaulting to the session's** when absent. A
stage may request **lower** than its tier but never higher: the tier is the ceiling.

**Fall back to `general-purpose` if the type does not resolve, and say so in the report.**

## The orchestrator is the sole reader of `.project-conf.toml`

Workers read no config. The orchestrator resolves every value and passes resolved values as
explicit arguments. **A worker given no value blocks; it never falls back to a default it
carries.** Two readers of one config is two answers to one question.

## A worker that writes code formats what it touched

**Before returning, run the project's formatter over the files you changed.** Every
code-touching worker does this: `implement`, `red-tests`, `review`, `adversary`,
`mutation-check`. Reference this paragraph; do not restate it (universal section 5).

**The project's formatter, never a named one.** Do not hardcode `gofmt`, `black`,
`prettier`, or `rustfmt`. Look at what the project already uses. A project with no formatter
is not an error — the instruction is a no-op there.

**Only the files you touched. Never the tree.** This is a prohibition.
Why: `server-v2` carries 110 unformatted files; a whole-tree format turns a 4-file diff into
110, destroying the review and swamping every gate.

**Formatting reports; it does not gate.** A formatter that errors or is absent is noted, not
a stop.

## Proving a finding by mutation — the one definition

**A worker may temporarily edit production code to prove a finding, and must restore it.**
`adversary` and `review` both do this. The protocol, in order, every time:

1. **Perturb.** Change production code so the behaviour under test breaks. Never the test —
   mutating the assertion proves it runs, not that it is right.

   **One exception: `mutation-check`'s vacuity probe** (Step 4). That probe asks whether an
   assertion would fail against *anything*, so it varies the test's expected value. It runs
   under the same restore-and-prove discipline. Every other worker stays on the production side.
2. **Observe.** Run the relevant tests. The finding survives only if the suite responds as
   predicted.
3. **Restore.** Put the file back exactly. `git status` must be clean of the probe before
   return.
4. **Control.** Mutate something the suite *should* catch and confirm it dies. A suite that
   stays green under a control mutation was never watching.

**Name every probe file `zz_probe_tmp_*`.** One prefix — greppable, obviously not production,
recognizable by a second worker.

**Restoration is not best-effort.** `git status --porcelain` over touched files must show only
intended edits, never a probe. A round ending with a mutation still applied hands the next
stage a sabotaged tree. If you cannot restore, report it by name and path as a blocking
failure; do not report a clean verdict over a dirty tree.

**Two mutating workers must never share a working tree at the same time.**
Why: PLTF-2562 — parallel 10b agents contaminated each other. See `handoff-verification.md`
for how 10b serializes them.

## Workers never launch workers

Whether `Skill()` works from inside a subagent is **not documented** — only the top-level
case is. Orchestrators run at top level; workers are leaves. Nothing nests. If a worker
seems to need a sub-worker, have it return and let the orchestrator launch the next one.

## Bracket every launch in `run.jsonl`

Write the `started` line **in the same step that launches**, and the `finished`/`failed`
line **in the same step that receives the result**. Never as a separate thing to remember.
Read `run-jsonl.md` for the schema.

**That same step writes the launch note** — the resolved
`(worker, tier, model, effort, subagent_type, subagent_type_used)` tuple. One note per
launch. The shape is defined once in `run-jsonl.md`.

Record `subagent_type_used` from what actually resolved, **including `general-purpose`**.

**Before writing `started`, check no span is already open.** If one is, you skipped a close
one stage ago.

## The worker roster

Eleven workers. Every worker **blocks rather than guesses** a missing argument.

| worker | takes | returns |
|---|---|---|
| `investigate` | the ticket | findings + a **predicted file map** |
| `red-tests` | the ticket + its DoD, `--backfill` | test files, node-ids, test command, stub paths, observed failure output (or, under `--backfill`, the behaviour each test pins) |
| `mutation-check` | `--tests` `--node-ids` `--command` `--targets` `--stubs` `--backfill` `--implemented` | per-node-id verdict + `MUTATION CHECK PASS` / `FAIL: n of m` / `BLOCKED`; under `--backfill` **or `--implemented`**, `PINNED: n of n` / `NOT PINNED: n of m`. Launched twice per run — stage 5 against stubs, stage 9 with `--implemented` against `$OWN`'s production diff |
| `adversary` | `--target` `--goals` `--caliber` `--round` `--prior` `--baseline` | numbered findings with severity + `ADVERSARY PASS` / `FAIL: n` / `GOAL DEFECT: n` / `BLOCKED` |
| `implement` | the ticket, the plan, the failing tests, `--refactor` | changes made, tests before/after, findings reported-not-fixed |
| `review` | `--scope` `--mode` `--frozen` | findings with severity + class, and `REVIEW CLEAN \| reported r (…)` / `APPLIED: n \| applied n (…) \| reported r (…)` / `BLOCKED` (no counts). Branch on the token left of the first `\|` |
| `slop-check` | `--scope` `--ticket` `--frozen` `--refactor` `--backfill` | findings with signal + severity + verdict |
| `vacuity-check` | `--base` `--frozen` `--node-ids` `--test-files` `--stubs` `--command` | per-node-id `vacuous` / `meaningful` / `could-not-determine` + verdict |
| `complexity-check` | `--base` `--repo` `--warn` `--reject` `--exempt-pre-existing` `--file-nloc-warn` | breaching functions + `CC CLEAN` / `VIOLATIONS: …` / `SKIPPED` / `BLOCKED` |
| `duplication-check` | `--base` `--repo` `--min-lines` `--exempt-pre-existing` `--exclude-paths` | clone groups + `DUP CLEAN` / `VIOLATIONS: …` / `SKIPPED` / `BLOCKED` |
| `create-ticket` | `--system` `--prefix` `--draft` `--tracking-dir` `--archive-dir` + backend coords | letter->key map + `CREATE CLEAN` / `PARTIAL` / `BLOCKED` |
| `archive` | `--ticket` `--dir` `--system` + backend coords | per-file push report + `ARCHIVE CLEAN` / `PARTIAL` / `BLOCKED` |

`--baseline` (adversary only) is a **previous version of the target**, not `--prior` (the
previous round's *findings*).

`--refactor` and `--backfill` are the two **invariant-mode** flags:

- `--refactor` — the ticket adds no behaviour; existing suite is its guard. No test file may
  be modified.
- `--backfill` — the ticket adds no production code; tests are green from the start and
  `mutation-check` is its guard. No production file may be modified.

Both are set from the ticket's **label** (`slopstop-refactor` / `slopstop-backfill`), never
inferred by a worker. **Never both at once** — the orchestrator stops at intake. Neither is
`--mode` (`review`'s interactive/autonomous switch). The one definition of all three modes is
`:run`'s invariant-tickets section.

Every worker can return `BLOCKED`. A caller that loops must branch on it explicitly:
`BLOCKED` means arguments were wrong, does **not** consume a round, and a loop treating it as
`FAIL` burns its cap without running the check.

**`--base` and `--frozen` mean the same thing everywhere.** `--base` = commit the branch
diverged from; `--frozen` = Phase 0 red-test commit. Two concepts, two names, no synonyms.

**`--base` is the *derived* divergence point, not the recorded fork sha**, whenever the two
differ (i.e. once a branch has carried the integration branch in). The orchestrator derives it
(`:run`'s `$OWN` section) because doing so needs `.project-conf.toml`, which no worker reads.
A worker cannot repair a stale `--base`; its only defence is to **report which sha it measured
from**.

## Data flow — what the orchestrator must thread

Workers are leaves and share nothing. **Every value below travels only because the
orchestrator carries it.**

```
investigate ──> predicted file map ──> conflict scheduling (which tickets run together)

red-tests ──┬─> node-ids, --command, --stubs, --tests ──> mutation-check   (stage 5: the STUBS)
            ├─> node-ids, --command, --stubs, --test-files ──> vacuity-check
            └─> the Phase 0 commit sha ──> --frozen ──> slop-check, review, vacuity-check

implement ──> $OWN's production files ──> --targets --implemented ──> mutation-check
                                                          (stage 9: the REAL IMPLEMENTATION)

branch point ──> --base ──> vacuity-check, complexity-check, duplication-check

.project-conf.toml ──> resolved CC thresholds ──> complexity-check
                   ──> resolved DUP thresholds ──> duplication-check
```

**`mutation-check` is fed twice, from two different producers.** Stage 5 mutates what
`red-tests` stubbed (*"is this test red for the right reason?"*); stage 9 mutates what
`implement` wrote (*"does anything pin it?"*). Same worker, same mechanism, two questions —
told apart by `--implemented` and by the stage in `run.jsonl`.

**Capture `--frozen` when the Phase 0 commit is made** — the only moment it is unambiguous.
Recovering it later by scanning history is the derivation every worker is forbidden to do.
