# Charter — slopstop reorganization

> Provenance: Claude · 2026-08-06 · `/slopstop:grill` session · branch `minor_fix`
> Companion to `design/prd-slopstop-reorg.md`. **Rules only** — design detail lives in the PRD.

These are the constraints every commit and every agent on this reorg must respect. Restate
the relevant ones verbatim in any agent prompt (universal §6) — agents start with no prior
context and will not follow rules they cannot see.

---

## C1 — slopstop's process does not run on this work

No ticket, no `:start`, no `:plan`, no `:pr` gate, no DoD. This branch is `minor_fix` with
no ticket prefix, deliberately. Do not create a BILL ticket for it and do not add
`Refs:`/`Closes:` trailers.

The goal is untouched. Only the implementation changes. Any change that alters what
slopstop *asks of consuming repos* is out of scope for this branch.

## C2 — One launch mechanism, no exceptions

Every worker is launched as:

```
Agent(subagent_type: "slopstop-worker-<effort>", model: <resolved from stage_tiers → tiers>,
      prompt: <invoke the worker skill>)
```

No headless `claude -p`. No `Skill()` invocation of a worker. No bespoke per-agent prompt
templates.

**Worker skill frontmatter carries `description` and `disable-model-invocation` only.** No
`model`, no `effort`, no `context: fork` — model is passed by the caller so per-project
`[tiers]` still applies, and effort comes from the subagent definition.

If a new site seems to need a different mechanism, that is a finding to raise, not a
licence to add a fifth dialect. Four dialects is the problem being deleted.

## C3 — Orchestrators are top-level; workers never launch workers

Whether a `context: fork` skill can be invoked from inside a subagent is **undocumented**.
Design around it. Do not probe it mid-implementation and do not assume either answer.

## C3a — The orchestrator is the sole reader of `.project-conf.toml`

No worker reads config. The orchestrator resolves every value — tiers, thresholds, flags —
applying documented defaults for absent keys, and passes the resolved values as explicit
arguments. A worker given no value **blocks**; it never falls back to a default it carries
itself.

Two readers of one config is two answers to one question. A worker defaulting to 5/10 while
the orchestrator resolved 8/15 measures against a threshold nobody configured, and reports
the wrong bound with total confidence.

This is the config twin of C4: one reader, one writer, no divergence.

## C4 — The orchestrator is the sole writer of `run.jsonl`

No worker writes to a tracking directory. No worker resolves a tracking directory. If a
worker appears to need to write, it returns the content and the orchestrator persists it.

`run.jsonl` is **append-only**. Never rewrite it, never compact it, never delete a line.

## C5 — Verify harness capability claims against the docs before designing on them

This repo has now been wrong three times about what the harness supports — `context: fork`
twice, and `effort:` in subagent frontmatter once. Two of those cost real work.

Before writing any rule that depends on what a skill, subagent, or tool can do: check
the official docs and cite them. If the docs are silent, say "the docs do not state this"
and design so the answer does not matter. Never write "X is impossible" without a citation.

When a check overturns a claim already written into the skills, grep for **every** copy and
fix them all in the same pass — BILL-333's was in nine skill files plus `CONFIG.md` plus a
design doc.

## C6 — `CLAUDE-universal.md` may change, but only with Ian's confirmation

Editing it **is in scope and expected** for this reorg — the rules describe a process this
branch is rewriting, so some of them will need to change (Ian, 2026-08-06).

Two constraints remain:

1. **Propose the exact diff and get Ian's confirmation before writing it.** It is mirrored
   byte-identically into every consuming repo, so a change here is a change to nine repos'
   rules. Never edit it as a side effect of some other change.
2. **Ian owns propagation.** Do not run `migrate-universal-block.py --apply`, and do not
   edit any other repo's copy. Make the change in this repo's reference copy only and tell
   him it is ready.

A project-specific exception that does not belong in every repo still goes in slopstop's
own `CLAUDE.md`, below the `@CLAUDE-universal.md` import, headed
`## <Topic> (overrides universal §N)`.

## C7 — Git

- Never `git push --force`, `git reset --hard`, `git commit --no-verify`, or
  `gh pr merge --admin`.
- **Never rebase a pushed branch.** Carry master in with `git merge master`.
- One PR off `minor_fix`. Do not branch off `minor_fix` for sub-work that will be merged
  separately, and do not stack.
- `gh pr merge --merge` — never squash, never rebase-merge.
- Co-Authored-By trailer naming the model that actually authored the commit.

## C8 — Deletions must be complete

A deletion that leaves references behind is not done. When removing a skill, a module, or
a config key, sweep every site: skill bodies, reference files, `manifest.txt`, both
installers, `CONFIG.md`, `COMMANDS.md`, `WORKFLOW.md`, `README.md`, `plugin.json`,
`.project-conf.toml.example`, and `walkthrough/`.

Stale references to deleted machinery are the specific defect this reorg exists to stop
producing.

## C9 — No new tests, and no test-shaped substitutes

Do not add a pytest file, a `conftest.py`, a CI workflow, or a shell script whose job is
to assert on markdown content. Do not "temporarily" keep a test to be deleted later.

`router/`'s Go tests stay untouched — do not extend them either.

If something feels like it needs a test to be safe, that is a signal to remove the failure
mode structurally (as the installer glob does), not to reintroduce a suite.

## C10 — Extraction precedes deletion

The worker skills are extracted *from* the stage skills being deleted. Never delete a
source skill before its extracted content is committed. Phase order in the PRD §6 is
binding.

## C11 — Do not use `open`

Never use `open` to display a file. It disrupts the user's screen. This applies to agents
and to the main session alike.

## C13 — Every Python file is surfaced and justified

Ian, 2026-08-06: the repo accumulated ~45 tracked `.py` files, almost all of them test
machinery. That is not to happen again by drift.

- **Report every Python file retained or created, at every phase boundary**, with the
  reason it exists and who runs it. Not a summary — the list.
- A new `.py` file needs an explicit reason that is not "a test needs it". This reorg is
  deleting the test suite; a helper module whose only consumer is a test is deleted with it.
- `conftest.py` in particular is pure pytest infrastructure and goes with `tests/`. Nothing
  outside `tests/` may import from it. Check before deleting: `CSV_COLUMNS` and the
  `changed_line_ranges`/`touched` overlap predicate lived there and are now restated in
  `skills/complexity-check/SKILL.md`.

## C12 — Surface rule/implementation disagreements, do not resolve them silently

This repo is the tool the other projects' rules run on, so a rule and its implementation
can drift apart. When they disagree, say so rather than quietly following one. That is a
report to Ian, not a decision to make alone.
