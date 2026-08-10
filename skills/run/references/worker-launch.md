# Launching a worker — the one definition

Every orchestrator (`:design`, `:tickets`, `:run`) launches workers this way. Read this
instead of writing your own form. Four different launch dialects is the thing this
reorganization exists to delete.

## The form

```
Agent(subagent_type: "slopstop-effort-<resolved effort>",   # general-purpose if it does not resolve
      model: <resolved: stage → tier → model>,
      prompt: "Invoke Skill({skill: \"slopstop:<worker>\", args: \"<args>\"}) and follow it
               exactly. Return its report verbatim as your result.")
```

That is the whole mechanism. No headless `claude -p`. No worktree flags. No router env
vars. No bespoke per-worker prompt templates — **the worker skill is the prompt**; a
template that restates it is a second copy that will drift.

**`subagent_type` selects the effort carrier** — `slopstop-effort-<level>` — with
`general-purpose` as the fallback when it does not resolve. Custom types **do** ship:
`install-for-project.sh` writes `.claude/agents/` (project scope, priority 3) and a plugin
ships an `agents/` directory (priority 5). This paragraph previously said the opposite; see
the Effort section for what was wrong and how it was probed.

## Pointing a worker at a worktree

`Agent()` has **no cwd parameter**. A worker that must work in a ticket's worktree is told to
enter it, as the first thing it does:

```
Agent(subagent_type: "slopstop-effort-<resolved>",
      model: <resolved>,
      prompt: "First call EnterWorktree(path: \".claude/worktrees/<TICKET>\"). Then invoke
               Skill({skill: \"slopstop:<worker>\", args: \"…\"}) and follow it exactly.
               Return its report verbatim as your result.")
```

**This works and needed no contract change** (BILL-466, probed): a subagent entering a
worktree reported its own `pwd` inside it, and every path a worker uses stays relative. The
feared alternative — absolute paths threaded through `implement`, `red-tests`,
`mutation-check`, `vacuity-check` and `complexity-check` — is not required.

**`.claude/worktrees/` is the only location this works from.** Outside it, `EnterWorktree`
raises an approval prompt no permission rule suppresses. See `:run`'s `## Worktrees`.

**Isolation is enforced from the other side too, and that is a feature.** While a session is
in a worktree, Claude Code blocks edits targeting the main checkout, commands whose working
directory resolves there, and **git redirected into it — `git -C`, `--git-dir`, `GIT_DIR`,
`GIT_WORK_TREE`, or a `cd` before running git.** A worker cannot corrupt the main checkout
even by trying, which is the containment the whole scheme is for. It also means orchestrator
instructions written as `git -C <the branch's checkout>` do not survive being handed to a
worker inside a worktree; the orchestrator runs those from the main worktree itself.

## Model — resolved by the orchestrator, passed explicitly

Two hops, both from `.project-conf.toml`: **stage → tier → model**.

`[stage_tiers]` maps a stage to a tier name; `[tiers.<name>]` maps that to a model family
and optional version pin. A missing key takes its documented default (`CONFIG.md`); a
missing table never errors.

Pass the resolved model on the `Agent()` call. **Do not put `model` in a worker skill's
frontmatter.** `Skill()` has no model parameter, so a worker carrying its own model would
be a fleet-wide constant — and per-project `[tiers]` is live and genuinely varies today.
Hardcoding it would silently break every project that re-tiered.

**Adversarial and checking work runs one tier above the work it checks.** That ladder is
the point of `[stage_tiers]` — `ticket_adversary` defaults to `huge` while `tickets` is
`large`. Resolve it; never flatten it to "same model as everything else".

## Effort — carried by the subagent type

The `Agent()` tool has no `effort` parameter. Effort comes from the **subagent definition's**
frontmatter, which is a documented field:

> `effort` — Effort level when this subagent is active. **Overrides the session effort
> level.** Options: `low`, `medium`, `high`, `xhigh`, `max`.

So slopstop ships one definition per level — `slopstop-effort-low` … `slopstop-effort-max` —
carrying nothing but an effort. **Resolve the effort, then use it as `subagent_type`:**

```
Agent(subagent_type: "slopstop-effort-<resolved>",
      model: <resolved: stage → tier → model>,
      prompt: "Invoke Skill({skill: \"slopstop:<worker>\", args: \"<args>\"}) …")
```

`model` still travels on the call and the definitions deliberately set none, so this is
tier × effort with **five files instead of twenty**.

**Effort resolves `[tiers.<name>].effort`, defaulting to the session's** when the key is
absent. A stage may request **lower** than its tier — see `:run`'s 10b rule for invariant
tickets — but never higher: the tier is the ceiling.

**Fall back to `general-purpose` if the type does not resolve, and say so in the report.**
There is a window after `.claude/agents/` is first created where a launch can fail with
`Agent type not found`; a silent fallback would drop the effort while the run still looked
configured, which is the shape this whole mechanism was mis-documented as for months.

> **Corrected 2026-08-07 (BILL-486).** This section previously read *"there are no custom
> subagent definitions, so worker effort inherits from the session, and per-stage effort
> tuning is not available."* Every clause was false. Custom definitions ship two ways —
> `.claude/agents/` at project scope, and a plugin's `agents/` directory — and
> `install-for-project.sh` now writes the former. **Probed, not assumed:** a project-scope
> definition launched, and its `tools:` restriction applied, proving the frontmatter block is
> honoured. Fourth time this repo has been wrong about a harness capability; the fix was a
> sweep, not a patch.

## The orchestrator is the sole reader of `.project-conf.toml`

Workers read no config. The orchestrator resolves every value — tiers, thresholds, flags —
applies documented defaults for absent keys, and passes resolved values as explicit
arguments. **A worker given no value blocks; it never falls back to a default it carries.**

Two readers of one config is two answers to one question. A worker defaulting to CC 5/10
while the orchestrator resolved 8/15 measures against a threshold nobody configured, and
names the wrong bound with total confidence.

## A worker that writes code formats what it touched — the one definition

**Before returning, run the project's formatter over the files you changed.** Every
code-touching worker does this: `implement`, `red-tests`, `review`, `adversary`,
`mutation-check`. Reference this paragraph; do not restate it (universal §5).

**The project's formatter, never a named one.** Do not write `gofmt`, `black`, `prettier` or
`rustfmt` into a skill. This fleet alone spans Go, Python and TypeScript, so a hardcoded tool
is wrong in most repos and silently does nothing in the rest. Look at what the project already
uses — its config, its CI, its existing style — and use that. **A project with no formatter is
not an error**: the instruction is a no-op there, and the worker says so rather than blocking.

**Only the files you touched. Never the tree.** This is a prohibition, not an omission.
`server-v2` carries **110 unformatted files** repo-wide; a worker that formats what it can
reach would turn a four-file diff into a 110-file one — destroying the review, swamping the
slop and complexity gates, and leaving the tamper check unable to tell a reformat from a
rewrite. The blast radius is not hypothetical, it is measured.

**Formatting reports; it does not gate.** A formatter that errors or is absent is noted in the
worker's result and nothing else. A worker whose real work succeeded must not fail on cosmetics.

Why this is here rather than left to each skill: it *was* left to each skill, and only
`red-tests` had it. The same run formatted its tests and left its implementation unformatted —
which is how a repo accumulates 110 unformatted files while every gate reports clean.

## Proving a finding by mutation — the one definition

**A worker may temporarily edit production code to prove a finding, and must restore it.**
`adversary` and `review` have both been doing this on real runs for months — perturb the
code, observe what the suite does, restore, then run a control mutation to prove the suite
was actually watching. It works, it is why their findings are trustworthy, and until
BILL-542 it was written down **nowhere**: `grep -i "mutat\|revert" skills/adversary/SKILL.md
skills/review/SKILL.md` returned nothing. An undocumented protocol is one that varies by
model and by run, and its absence is what let two checkers be launched into the same working
tree with nothing warning the orchestrator they would collide.

The protocol, in order, every time:

1. **Perturb.** Change the production code so the behaviour under test is broken. Never the
   test — a frozen Phase 0 test is a tamper hard-stop, and mutating the assertion proves the
   assertion runs, not that it is right.
2. **Observe.** Run the relevant tests. The finding survives only if the suite responds the
   way the finding predicts.
3. **Restore.** Put the file back exactly. **`git status` must be clean of the probe before
   you return** — see below.
4. **Control.** Mutate something the suite *should* catch and confirm it dies. A suite that
   stays green under a control mutation was never watching, and a "confirmed" finding taken
   from it is worthless.

**Name every probe file `zz_probe_tmp_*`.** One prefix, so a stray one is greppable and
obviously not production, and so a second worker can recognise it as somebody else's.

**Restoration is not best-effort.** Before returning, `git status --porcelain` over the files
you touched must show only edits you intend to hand back — never a probe. A round that ends
with a mutation still applied hands the next stage a sabotaged tree and attributes the
breakage to whoever runs next. If you cannot restore, say so in your verdict **by name and
path** and treat it as a blocking failure of your own round; do not report a clean verdict
over a dirty tree.

**Two mutating workers must never share a working tree at the same time.** This is not
theoretical: PLTF-2562 launched 10b's two agents in parallel and *"they contaminated each
other — the adversary observed the reviewer's `zz_probe_tmp_test`"*. The caller owns this —
see `handoff-verification.md` for how 10b serializes them.

## Workers never launch workers

Whether a skill can be invoked from inside a subagent in the way these workers are is
**not documented** — only the top-level case is. So orchestrators run at top level and
workers are leaves. Nothing nests.

If a worker seems to need a sub-worker, that is the orchestrator's job: have the worker
return, then launch the next one.

## Bracket every launch in `run.jsonl`

Write the `started` line **in the same step that launches**, and the `finished`/`failed`
line **in the same step that receives the result**. Never as a separate thing to remember.
→ Read `run-jsonl.md` for the schema and the validation rules.

**That same step also writes the launch note** — the resolved
`(worker, tier, model, effort, subagent_type, subagent_type_used)` tuple. One note per
launch, so a `gates` span carrying two workers writes two. The shape is defined once, in
`run-jsonl.md`; do not restate it here.

Record `subagent_type_used` from what actually resolved, **including when it is
`general-purpose`**. The fallback above is legitimate; a fallback that only appears in a
report nobody keeps is not — it leaves the run reading as configured while the effort has
quietly reverted to the session's.

**Before writing `started`, check no span is already open.** If one is, you skipped a close
one stage ago and this is the last moment its true end time is still knowable.

## The worker roster

Eleven workers. Arguments are what the orchestrator must pass; every worker **blocks rather
than guesses** a missing one.

| worker | takes | returns |
|---|---|---|
| `investigate` | the ticket | findings + a **predicted file map** |
| `red-tests` | the ticket + its DoD, `--backfill` | test files, node-ids, test command, stub paths, observed failure output (or, under `--backfill`, the behaviour each test pins) |
| `mutation-check` | `--tests` `--node-ids` `--command` `--targets` `--stubs` `--backfill` `--implemented` | per-node-id verdict + `MUTATION CHECK PASS` / `FAIL: n of m` / `BLOCKED`; under `--backfill` **or `--implemented`**, `PINNED: n of n` / `NOT PINNED: n of m`. Launched twice per run — stage 5 against the stubs, stage 9 with `--implemented` against `$OWN`'s production diff |
| `adversary` | `--target` `--goals` `--caliber` `--round` `--prior` `--baseline` | numbered findings with severity + `ADVERSARY PASS` / `FAIL: n` / `GOAL DEFECT: n` / `BLOCKED` |
| `implement` | the ticket, the plan, the failing tests, `--refactor` | changes made, tests before/after, findings reported-not-fixed |
| `review` | `--scope` `--mode` `--frozen` | findings with severity + class, and `REVIEW CLEAN \| reported r (…)` / `APPLIED: n \| applied n (…) \| reported r (…)` / `BLOCKED` (no counts). Branch on the token left of the first `\|` |
| `slop-check` | `--scope` `--ticket` `--frozen` `--refactor` `--backfill` | findings with signal + severity + verdict |
| `vacuity-check` | `--base` `--frozen` `--node-ids` `--test-files` `--stubs` `--command` | per-node-id `vacuous` / `meaningful` / `could-not-determine` + verdict |
| `complexity-check` | `--base` `--repo` `--warn` `--reject` `--exempt-pre-existing` `--file-nloc-warn` | breaching functions + `CC CLEAN` / `VIOLATIONS: …` / `SKIPPED` / `BLOCKED` |
| `create-ticket` | `--system` `--prefix` `--draft` `--tracking-dir` `--archive-dir` + backend coords | letter→key map + `CREATE CLEAN` / `PARTIAL` / `BLOCKED` |
| `archive` | `--ticket` `--dir` `--system` + backend coords | per-file push report + `ARCHIVE CLEAN` / `PARTIAL` / `BLOCKED` |

`--baseline` (adversary only) is a **previous version of the target**, required by the
`scope-subtraction` caliber. It is not `--prior`, which is the previous round's *findings*.

`--refactor` and `--backfill` are the two **invariant-mode** flags, each with one meaning
everywhere and each the mirror of the other:

- `--refactor` — **the ticket adds no behaviour**, so it has no Phase 0 baseline and the
  existing suite is its guard. No test file may be modified.
- `--backfill` — **the ticket adds no production code**, so its tests are green from the
  start and `mutation-check` is its guard. No production file may be modified.

Both are set by the orchestrator from the ticket's **label** — `slopstop-refactor` or
`slopstop-backfill` — never inferred by a worker from the diff or from the ticket body, and
**never both at once**: a ticket carrying both labels could change nothing at all, and the
orchestrator stops it at intake rather than launching anything. Neither is `--mode`, which is `review`'s
interactive/autonomous switch. The one definition of all three modes is `:run`'s
invariant-tickets section; this table only records who takes the flags.

Every worker can return `BLOCKED`. A caller that loops must branch on it explicitly:
`BLOCKED` means the arguments were wrong, so it does **not** consume a round, and a loop
that treats it as a `FAIL` will burn its cap without ever running the check.

**`--base` and `--frozen` mean the same thing everywhere.** `--base` is the commit the
branch diverged from; `--frozen` is the Phase 0 red-test commit. Two concepts, two names,
no synonyms.

**`--base` is the *derived* divergence point, not the recorded fork sha**, whenever the two
differ — i.e. once a branch has carried the integration branch in. The orchestrator derives it
(`:run`'s `$OWN` section) because doing so needs the integration branch's name from
`.project-conf.toml`, which no worker reads. A worker cannot repair a stale `--base`: the
`merge-base` it could run against the value it was given returns that same value. So this one
is entirely on the caller, and a worker's only defence is to **report which sha it measured
from**.

## Data flow — what the orchestrator must thread

Workers are leaves and share nothing. **Every value below travels only because the
orchestrator carries it.** This is the part with no safety net: a worker told to derive a
sha itself would guess, and a wrong `--base` measures the wrong range while looking
perfectly healthy.

```
investigate ──► predicted file map ──► conflict scheduling (which tickets run together)

red-tests ──┬─► node-ids, --command, --stubs, --tests ──► mutation-check   (stage 5: the STUBS)
            ├─► node-ids, --command, --stubs, --test-files ──► vacuity-check
            └─► the Phase 0 commit sha ──► --frozen ──► slop-check, review, vacuity-check

implement ──► $OWN's production files ──► --targets --implemented ──► mutation-check
                                                          (stage 9: the REAL IMPLEMENTATION)

branch point ──► --base ──► vacuity-check, complexity-check

.project-conf.toml ──► resolved CC thresholds ──► complexity-check
```

**`mutation-check` is fed twice, from two different producers, and that is the point.** Stage
5 mutates what `red-tests` stubbed and asks *"is this test red for the right reason?"*; stage
9 mutates what `implement` actually wrote and asks *"does anything pin it?"* Same worker, same
mechanism, two questions — told apart by `--implemented` on the call and by the stage in
`run.jsonl`. Feeding stage 9 from `red-tests` instead of from `$OWN` would re-run stage 5 with
extra steps (BILL-538).

**Capture `--frozen` when the Phase 0 commit is made** — that is the only moment it is
unambiguous. Recovering it later by scanning history (`git log | grep 'Phase 0' | tail -1`)
is the derivation every worker is explicitly forbidden to do, and it is wrong on any branch
with more than one such commit.
