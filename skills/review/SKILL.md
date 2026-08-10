---
description: One round of clean-context code review of a diff — find, verify each finding against the real code, apply what survives, report a verdict. Runs in its own forked context so the session that wrote the code never reviews it.
---

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
Skill(skill: "slopstop:review", args: "--scope <ref-range-or-PR> --mode <autonomous|interactive> --frozen <sha>")
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

**You may prove a finding by mutation, and you must restore what you touched.** Perturb the
production code, observe the suite, restore it exactly, then run a control mutation to prove
the suite was watching at all. **One definition, in `worker-launch.md`** — the probe-file
naming, the `git status` check before you return, and why a control mutation is not optional.
Do not restate it here; do not invent a variant. This was the protocol you were already
following on real runs before anyone wrote it down (BILL-542).

**Never mutate a frozen Phase 0 test to prove anything.** That is the tamper hard-stop
described above, and it proves the assertion *runs* rather than that it is *right*.

Classify each confirmed finding 🔴 should-fix / 🟡 could-fix / ⚪ skip. ⚪ covers three
different things and they are not interchangeable: premise wrong, contradicts an
established convention (a reasoned rejection — the codebase wins), and stylistic nit.

## Severity and class — cited, never restated

Every confirmed finding also carries a **severity** and a **class**. Both definitions live
in `skills/adversary/SKILL.md` — read them there. They are not repeated here, deliberately:
two copies of a vocabulary is how the two halves of stage 10b end up grading on different
scales, and one of them would drift first.

- **severity** — `blocker` / `major` / `minor`, per `adversary`'s **§Severity**. Its rule
  that *"a preference you cannot state a concrete consequence for is not a finding"* is the
  same rule as this skill's *"a finding you cannot state a failure for is a preference"*.
  One standard, said twice by two skills that both have to hold it.
- **class** — `behavioural` / `presentational`, per `adversary`'s **§Class**. Adopted rather
  than declined so that stage 10b's two workers report on the same axes: 10b runs this
  worker *and* `adversary`, and a comparison between a classified half and an unclassified
  one measures the instrumentation, not the code.

Severity and class are independent of each other, exactly as in `adversary` — a `blocker`
can be presentational, a `minor` can be behavioural.

**Severity is not the 🔴/🟡/⚪ gate above, and neither replaces the other.** The gate answers
*do I fix this, in this mode*; severity answers *how bad is it*. They correlate and do not
coincide: a `major` is 🔴 in one codebase and 🟡 in another depending on what the diff is
for. Keep both.

**Refuted and unconfirmed findings carry no severity.** A finding whose premise is wrong is
not a small defect, it is not a defect. Give them their reason, leave them out of the
counts — a severity on a refuted finding puts it back into a distribution it was removed
from.

## Apply

| `--mode` | 🔴 | 🟡 | ⚪ nit | ⚪ premise-wrong / convention | unconfirmed |
|---|---|---|---|---|---|
| `autonomous` | fix | fix | fix | never | never |
| `interactive` | fix | report | report | never | never |

**A confirmed 🔴 is never left unfixed**, in either mode.

Apply with `Edit`. Do not hand findings back for the caller to apply — the caller is the
context this fork exists to exclude.

**Before returning, run the project's formatter over the files you touched.** One definition, in `worker-launch.md` — the project's own formatter, never a named one, and only the files this worker changed.

## Report

End with exactly one verdict line, spelled exactly as shown:

```
REVIEW CLEAN | reported <r> (blocker <b>, major <M>, minor <m>)
REVIEW APPLIED: <n> | applied <n> (blocker <b>, major <M>, minor <m>) | reported <r> (blocker <b>, major <M>, minor <m>)
REVIEW BLOCKED: <reason>
```

- **`REVIEW CLEAN`** — you applied nothing this round. Either there was nothing to fix, or
  everything found was reported rather than applied under `interactive`. The caller stops.
- **`REVIEW APPLIED: <n>`** — you applied `<n>` fixes. The caller commits and runs another
  round.
- **`REVIEW BLOCKED: <reason>`** — you could not proceed. The caller stops and surfaces it.

**The leading token is the contract.** Everything from `REVIEW` up to the first `|` is what
the caller branches on, and it is unchanged from what it has always been. The counts are a
suffix. Write the whole line; a caller that reads only the token still behaves correctly,
which is the point — this addition cannot break a reader that predates it.

**`REVIEW BLOCKED` takes no counts.** It means *the arguments were wrong* — you never got as
far as having findings. It is not a severity and must never be written as one.

**The verdict keys on what you applied, not on what you found.** That is deliberate: under
`interactive` a branch with only 🟡 findings would otherwise never converge, and would burn
all five rounds re-finding the same ones. The counts are what tell the caller what you
found; the token is what tells it what to do next. Do not collapse them.

### The two numbers that are not the same number

**`<n>` is applied. `<r>` is reported-not-applied. They are different findings, and neither
is the total.** A round that finds five things, fixes three and reports two is
`REVIEW APPLIED: 3 | applied 3 (…) | reported 2 (…)`. The `applied` triple **must sum to
`<n>`** and the `reported` triple **must sum to `<r>`** — that is a check you run on your own
line before returning it, not a coincidence.

Reported-not-applied is a real category and it must stay visible: declining to edit inside a
frozen Phase 0 file is *correct* behaviour under the frozen-test rule, and a line that
folded it in with the applied fixes would erase the fact that you hit a boundary and
respected it. Refuted and unconfirmed findings are in neither triple — see above.

**`REVIEW CLEAN` can never carry a reported `blocker`.** A confirmed 🔴 is never left
unfixed in either mode, so `blocker ≥ 1` on a `CLEAN` line is a self-contradiction. If you
find yourself about to write one, you have either mis-severitied the finding or wrongly
declined to fix it. Resolve it before returning; do not emit the line.

Then list, one line each, `file:line — <severity>/<class> — summary` for everything applied
and everything reported for human judgment, and `file:line — refuted — <reason>` for
everything refuted or unconfirmed (no severity, no class).
