# `:pr` Step 1 — Reuse brief

You are **one of four independent cleanup agents** on this branch's diff. The other
three cover the dimensions you do not — stay in your lane; duplicating their work
wastes a pass.

**You were also given `pr-simplify-brief-common.md`.** It carries the rules that bind
every dimension: read the repository's own `CLAUDE.md`, never touch generated /
vendored / test-corpus files, never edit a frozen Phase 0 test, apply your own fixes,
preserve behavior. If you did not receive it, say so and stop — you are missing half
your instructions.

## Your dimension: reuse

Find code in the diff that re-implements something the repository already has.

**Search before you conclude something is new.** Grep the shared and utility modules,
and the files adjacent to the change. A helper that already exists under a different
name is the single most common finding here, and the only way to find it is to look.

What to look for:

- A function that duplicates an existing helper's job, in whole or in part.
- Two or more near-identical code paths introduced by this diff. If the repository's
  rules put dedupe in scope, extract the helper and migrate every duplicate in the same
  pass — leaving one call site un-migrated is how the next duplicate gets written.
- A constant, string, or magic value defined a second time. One definition per value;
  if something needs renaming, update every reference rather than adding an alias.
- A pattern the codebase already solves a standard way, solved here a different way.
  Mirror the existing vocabulary; do not invent a parallel term for the same concept.

When you find a duplicate, **name the existing helper and call it** rather than leaving
a comment suggesting someone might.

Two things that look like reuse findings and are not: code that is superficially similar
but diverges under change, and an abstraction extracted so early that it has one caller
and an awkward signature. Both are worse after "deduplication" than before.

## Maintain balance — the failure mode of your own dimension

Every instruction above pushes you toward *more* extraction. This section pushes back, and
it carries equal weight. Avoid changes that:

- Reduce code clarity or maintainability
- Create overly clever solutions that are hard to understand
- Combine too many concerns into a single function or component
- Remove helpful abstractions that improve organization
- Prioritize "fewer lines" over readability
- Make the code harder to debug or extend

**When a change trades clarity for extraction, do not make it.** A reviewer who cannot
follow the result will not be able to maintain it, and the cost lands later on someone
with less context than you have now.

