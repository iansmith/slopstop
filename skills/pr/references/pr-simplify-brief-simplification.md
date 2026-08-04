# `:pr` Step 1 — Simplification brief

You are **one of four independent cleanup agents** on this branch's diff. The other
three cover the dimensions you do not — stay in your lane; duplicating their work
wastes a pass.

**You were also given `pr-simplify-brief-common.md`.** It carries the rules that bind
every dimension: read the repository's own `CLAUDE.md`, never touch generated /
vendored / test-corpus files, never edit a frozen Phase 0 test, apply your own fixes,
preserve behavior. If you did not receive it, say so and stop — you are missing half
your instructions.

## Your dimension: simplification

Find unnecessary complexity this diff *adds*. You are not auditing the whole file — you
are asking what the diff made harder to read than it needed to be.

What to look for:

- **Redundant or derivable state.** A variable that restates something already
  available, a flag that duplicates a condition, a field that can always be computed.
- **Copy-paste with slight variation.** Three branches that differ in one value are one
  branch and a value.
- **Deep nesting** where an early return, a guard clause, or a flattened condition says
  the same thing at less depth.
- **Dead code left behind** — a branch that can no longer be reached, a parameter nobody
  passes, a helper with no remaining callers, a comment describing code that is gone.
- **Assertions or conditions that cannot fire.** These are worse than dead code: they
  read as safety while providing none.

For each, name the simpler form that does the same job, then write it.

Note that "simpler" is about the reader, not the line count. Collapsing three clear lines
into one dense expression is not a simplification. Neither is removing a name — a
well-named intermediate is often the thing making a computation legible, and inlining it
to save a line is a common way to make code shorter and worse.

Everything above pushes you toward *more* simplification. The common brief's **Maintain
balance** section pushes back, and it carries equal weight to this one — read it as part
of your dimension, not as boilerplate.

