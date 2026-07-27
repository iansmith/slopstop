# Merge: the Definition-of-Done gate (Step 1 detail)

`:merge` refuses to merge work that does not meet the ticket's own Definition of Done.
This is the gate that makes "the DoD is what a merge is judged against" true on the
single-ticket path — `:run` has always scored it for the fleet, and `:document` posts a
confirmation *after* the merge, which is too late to gate anything.

Scoring itself is not defined here. One definition, three callers:
→ Read `~/.claude/commands/slopstop-run-refs/dod-scoring.md`

## When it runs

In `## Pre-merge gates`, **below** the `Skipped when `$ADOPT` is true` divider. Adopt
mode means the PR is already `MERGED` and `:merge` is recording that fact — there is
nothing left to gate, and a DoD scored after the merge cannot change the outcome.

Evidence is the **pre-merge** set defined in `dod-scoring.md`. Do not restate it here.

## Locating the DoD

Two sources, in order:

1. **`task_plan.md`'s `## Definition of Done` section** — the primary. Resolve the
   tracking dir via the one definition, never by a hardcoded path:
   → Read `~/.claude/commands/slopstop-start-refs/tracking-dir-resolution.md`
2. **The ticket body** — the fallback, used *when* the tracking dir is absent, the
   ticket has been archived, or `task_plan.md` carries no such section. A ticket cut to
   the five-section standard carries its DoD, so an archived plan dir must not silently
   disable the gate.

## No Definition of Done — proceed and say so

If neither source yields a DoD, that is **not** an error. Report it plainly and
continue with the merge:

```
[dod] No Definition of Done found for $TICKET — nothing to gate. Proceeding.
```

A `## Definition of Done` heading that exists but contains **zero items** takes this
same path. An empty section is an absent DoD; treating it as a failed one would turn a
formatting slip into a blocked merge.

## A non-`met` verdict blocks

Any item scoring `not-met` **or** `unverifiable` stops the merge before Step 4. Both
are non-`met`; `unverifiable` is not a softer answer, for the reason `dod-scoring.md`
gives.

Report every item with its verdict and evidence, then refuse:

```
[dod] $TICKET — 3 items scored, 1 not met:
  met           Red tests for the gate exist and are green   (check run #1234)
  met           merge-dod-gate.md declared in manifest.txt   (diff)
  not-met       CHANGELOG entry for the new key              (absent from diff)

Refusing to merge: the ticket's Definition of Done is not satisfied.
Fix the work, or amend the DoD if it is wrong — do not merge past it.
```

In **interactive** mode there is no override. The human fixes the work or fixes the
ticket; the confirmation in Step 3 reports the result but offers no way past it.

In **autonomous** mode `[autonomous] on_dod_not_met` governs, and it is the only escape
hatch that exists:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-autonomous.md`

That asymmetry is deliberate rather than an oversight. `[autonomous] enabled` is a
master switch — no key in that section takes effect without it — so an interactive run
has no configured override by construction. A human facing a not-met item is the one
person able to fix it properly.
