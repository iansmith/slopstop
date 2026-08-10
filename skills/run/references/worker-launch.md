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
| `mutation-check` | `--tests` `--node-ids` `--command` `--targets` `--stubs` `--backfill` | per-node-id verdict + `MUTATION CHECK PASS` / `FAIL: n of m` / `BLOCKED`; under `--backfill`, `PINNED: n of n` / `NOT PINNED: n of m` |
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

red-tests ──┬─► node-ids, --command, --stubs, --tests ──► mutation-check
            ├─► node-ids, --command, --stubs, --test-files ──► vacuity-check
            └─► the Phase 0 commit sha ──► --frozen ──► slop-check, review, vacuity-check

branch point ──► --base ──► vacuity-check, complexity-check

.project-conf.toml ──► resolved CC thresholds ──► complexity-check
```

**Capture `--frozen` when the Phase 0 commit is made** — that is the only moment it is
unambiguous. Recovering it later by scanning history (`git log | grep 'Phase 0' | tail -1`)
is the derivation every worker is explicitly forbidden to do, and it is wrong on any branch
with more than one such commit.
