---
description: One round of clean-context code review of a diff — find, verify each finding against the real code, apply what survives, report a verdict. Runs in its own forked context so the session that wrote the code never reviews it.
---

<!-- GENERATED from slopstop 4ef0f85 by install-for-project.sh — do not edit.
     Edit skills/review/ in the slopstop repo and re-run. (universal §5) -->

# One round of clean-context review

You run as a **worker agent**: no access to the conversation that invoked you. That is
the point. A session that has spent an hour justifying a design will justify it again when
asked to review it, and PR #411 shipped a clean `step_6: pass` from exactly that
arrangement.

You do **one round**. The caller loops on a fresh fork until you report clean or five
rounds have run. Round N+1 has no memory of round N, so it can neither defend nor
rationalise the previous round's fixes.

## Arguments — you have no conversation, so everything comes through here

The caller invokes you as:

```
Skill(skill: "slopstop-review", args: "--scope <ref-range-or-PR> --mode <autonomous|interactive> --frozen <sha>")
```

- **`--scope`** — what to review. Either a PR number (`123`) or a ref range
  (`origin/main...HEAD`). **Never guess.** You cannot see `$PR`, `$BASE` or
  `$ORIGIN_REMOTE` — those live in the caller's session, not yours. If `--scope` is
  missing or empty, report `REVIEW BLOCKED: no scope given` and stop. Do not fall back to
  `origin/HEAD`, which is the remote's *default* branch and may not be this PR's base.
- **`--mode`** — decides the apply table below. You cannot read `.project-conf.toml` for
  it and must not try. Missing → treat as `interactive`, the conservative choice.
- **`--frozen`** — the Phase 0 red-test commit sha. Files in that commit are frozen; see
  below. Missing → report `REVIEW BLOCKED: no frozen-test baseline given` rather than
  deriving one, because a wrong baseline causes a tamper hard-stop attributed to you.

## Read the repository's own rules first

**Read `CLAUDE.md` at the repository root**, plus any `CLAUDE-universal.md` it imports and
any `.claude/rules/*.md`. Those bind the code you are reviewing and override anything here
that conflicts. A forked skill receives project context, so they are available to you.

This file names **no language's conventions**. slopstop is installed across repositories
spanning six languages and a 200× size range; a rule true in one is wrong in the others.

## What you must not touch

**Frozen Phase 0 tests.** The frozen set is the files in the commit passed as `--frozen`:

```bash
git show --name-only --format= "$FROZEN_SHA"
```

A frozen test's shape *is* its contract. Editing one turns this review into a tamper
hard-stop two steps later, attributed to you. Do not derive the sha yourself — an unscoped
`git log | grep 'Phase 0: red tests' | tail -1` walks the entire history and returns the
repository's *first* ticket, not this one.

**Generated files, vendored dependencies, and byte-exact test corpora.** They are correct
precisely because nobody improved them; "improving" one silently invalidates every test
depending on it. Check `CLAUDE.md` and `.gitignore`, and treat any directory named for test
data, vendoring or generation as off-limits unless the ticket says otherwise.

## Find

Read every hunk in `--scope` as a careful senior engineer would:

- **Correctness** — inverted conditions, off-by-one, null dereference, missing `await`,
  dropped error handling, removed guards, broken callers of a changed signature, races.
- **Reuse** — code re-implementing something the repo already has. Grep the shared and
  utility modules before concluding something is new.
- **Simplification** — redundant or derivable state, copy-paste with slight variation, dead
  code, conditions that cannot fire.
- **Efficiency** — repeated I/O, work in a hot path, a closure holding a large scope alive.
  Quantify it or drop it.
- **Altitude** — is the change at the right depth, or a bandaid over a cause one level
  down? A special case bolted onto shared infrastructure usually means the mechanism does
  not do what its callers need.

**Every finding needs a concrete scenario in which the code misbehaves** — inputs or state,
and the wrong result. A finding you cannot state a failure for is a preference; leave it out.

## Verify before acting

Open the cited code and **reproduce the premise**. A finding survives only if the code
actually does what the finding claims.

- **confirmed** — reproduced against the real code.
- **not confirmed** — could not. This includes "plausible but unverified".

**An unconfirmed finding is never applied, in either mode.** Acting on an unverified
finding is the same defect as dismissing a verified one, pointed the other way. Record it
with the reason; never drop it silently.

Classify each confirmed finding 🔴 should-fix / 🟡 could-fix / ⚪ skip. ⚪ covers three
different things and they are not interchangeable: premise wrong, contradicts an
established convention (a reasoned rejection — the codebase wins), and stylistic nit.

## Apply

| `--mode` | 🔴 | 🟡 | ⚪ nit | ⚪ premise-wrong / convention | unconfirmed |
|---|---|---|---|---|---|
| `autonomous` | fix | fix | fix | never | never |
| `interactive` | fix | report | report | never | never |

**A confirmed 🔴 is never left unfixed**, in either mode.

Apply with `Edit`. Do not hand findings back for the caller to apply — the caller is the
context this fork exists to exclude.

## Report

End with exactly one verdict line, spelled exactly as shown:

- **`REVIEW CLEAN`** — you applied nothing this round. Either there was nothing to fix, or
  everything found was reported rather than applied under `interactive`. The caller stops.
- **`REVIEW APPLIED: <n>`** — you applied `<n>` fixes. The caller commits and runs another
  round.
- **`REVIEW BLOCKED: <reason>`** — you could not proceed. The caller stops and surfaces it.

**The verdict keys on what you applied, not on what you found.** That is deliberate: under
`interactive` a branch with only 🟡 findings would otherwise never converge, and would burn
all five rounds re-finding the same ones.

Then list, one line each: `file:line — summary` for everything applied, everything reported
for human judgment, and everything refuted with its reason.
