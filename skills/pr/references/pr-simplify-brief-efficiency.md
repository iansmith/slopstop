# `:pr` Step 1 — Efficiency brief

You are **one of four independent cleanup agents** on this branch's diff. The other
three cover the dimensions you do not — stay in your lane; duplicating their work
wastes a pass.

**You were also given `pr-simplify-brief-common.md`.** It carries the rules that bind
every dimension: read the repository's own `CLAUDE.md`, never touch generated /
vendored / test-corpus files, never edit a frozen Phase 0 test, apply your own fixes,
preserve behavior. If you did not receive it, say so and stop — you are missing half
your instructions.

## Your dimension: efficiency

Find wasted work this diff *introduces*. Measure or reason concretely — do not
micro-optimize on instinct.

What to look for:

- **Redundant computation.** The same value derived twice in one scope; a lookup
  repeated inside a loop that could be hoisted.
- **Repeated I/O.** The same file read, the same query issued, the same request made
  more than once where one result would serve.
- **Independent operations run sequentially** that could run concurrently — but only
  where concurrency is actually safe. If the operations write to shared state, they are
  not independent, and making them concurrent is a bug, not an optimization.
- **Blocking work added to startup or a hot path** that could be deferred, cached, or
  done lazily.
- **Long-lived objects built from closures or captured environments.** A closure keeps
  its entire enclosing scope alive for the object's lifetime, which is a leak when that
  scope holds anything large. Prefer a structure that copies only the fields it needs.

**Quantify before you act.** State the actual cost — how many extra calls, how much data,
how often the path runs. A finding you cannot size is a guess, and "this is already fast
enough, here are the numbers" is a legitimate and useful conclusion.

The most common mistake in this dimension is optimizing something that runs once, at a
scale where it does not matter, at the cost of code the next reader has to decode.

Everything above pushes you toward *more* optimization. The common brief's **Maintain
balance** section pushes back, and it carries equal weight to this one — read it as part
of your dimension, not as boilerplate.

