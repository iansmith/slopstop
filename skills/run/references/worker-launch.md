# Launching a worker — the one definition

Every orchestrator (`:design`, `:tickets`, `:run`) launches workers this way. Read this
instead of writing your own form. Four different launch dialects is the thing this
reorganization exists to delete.

## The form

```
Agent(subagent_type: "general-purpose",
      model: <resolved: stage → tier → model>,
      prompt: "Invoke Skill({skill: \"slopstop:<worker>\", args: \"<args>\"}) and follow it
               exactly. Return its report verbatim as your result.")
```

That is the whole mechanism. No headless `claude -p`. No worktree flags. No router env
vars. No bespoke per-worker prompt templates — **the worker skill is the prompt**; a
template that restates it is a second copy that will drift.

**`subagent_type` is always `general-purpose`.** It is the one type that exists everywhere.
Custom subagent types cannot ship: the plugin installs skills into `.claude/commands/`, and
there is no mechanism to install `.claude/agents/` definitions into a consuming repo. A
`subagent_type: "slopstop-worker"` would resolve in this repo and fail in all nine others,
which is exactly backwards for a tool whose purpose is to run elsewhere.

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

## Effort — inherited, not passed

The `Agent()` tool takes `model` but has **no documented `effort` parameter**. Effort on
that path comes from a subagent definition's frontmatter, and per the shipping constraint
above there are no custom subagent definitions. So **worker effort inherits from the
session**, and per-stage effort tuning is not available.

This is a known, accepted limitation. Do not work around it by putting `effort` in worker
frontmatter — that reintroduces the un-configurable-per-project problem `model` has, for a
field the caller cannot override at all.

## The orchestrator is the sole reader of `.project-conf.toml`

Workers read no config. The orchestrator resolves every value — tiers, thresholds, flags —
applies documented defaults for absent keys, and passes resolved values as explicit
arguments. **A worker given no value blocks; it never falls back to a default it carries.**

Two readers of one config is two answers to one question. A worker defaulting to CC 5/10
while the orchestrator resolved 8/15 measures against a threshold nobody configured, and
names the wrong bound with total confidence.

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

## The worker roster

Eleven workers. Arguments are what the orchestrator must pass; every worker **blocks rather
than guesses** a missing one.

| worker | takes | returns |
|---|---|---|
| `investigate` | the ticket | findings + a **predicted file map** |
| `red-tests` | the ticket + its DoD | test files, node-ids, test command, stub paths, observed failure output |
| `mutation-check` | `--tests` `--node-ids` `--command` `--targets` `--stubs` | per-node-id verdict + `MUTATION CHECK PASS` / `FAIL: n of m` / `BLOCKED` |
| `adversary` | `--target` `--goals` `--caliber` `--round` `--prior` | numbered findings with severity + `ADVERSARY PASS` / `FAIL: n` / `GOAL DEFECT` |
| `implement` | the ticket, the plan, the failing tests | changes made, tests before/after, findings reported-not-fixed |
| `review` | `--scope` `--mode` `--frozen` | `REVIEW CLEAN` / `APPLIED: n` / `BLOCKED` |
| `slop-check` | `--scope` `--ticket` `--frozen` | findings with signal + severity + verdict |
| `vacuity-check` | `--base` `--frozen` `--node-ids` `--test-files` `--stubs` `--command` | per-node-id `vacuous` / `meaningful` / `could-not-determine` + verdict |
| `complexity-check` | `--base` `--repo` `--warn` `--reject` `--exempt-pre-existing` `--file-nloc-warn` | breaching functions + `CC CLEAN` / `VIOLATIONS: …` / `SKIPPED` / `BLOCKED` |
| `create-ticket` | `--system` `--prefix` `--draft` `--tracking-dir` `--archive-dir` + backend coords | letter→key map + `CREATE CLEAN` / `PARTIAL` / `BLOCKED` |
| `archive` | `--ticket` `--dir` `--system` + backend coords | per-file push report + `ARCHIVE CLEAN` / `PARTIAL` / `BLOCKED` |

**`--base` and `--frozen` mean the same thing everywhere.** `--base` is the commit the
branch diverged from; `--frozen` is the Phase 0 red-test commit. Two concepts, two names,
no synonyms.

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
