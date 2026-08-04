# `:pr` Step 6 — Efficiency find brief

**You were also given `pr-review-brief-common.md`.** It carries the rules that bind every
find dimension: you must not write, read the repository's own `CLAUDE.md`, scope is the PR
diff, ignore generated / vendored / test-corpus files, and the report format below. If you
did not receive it, say so and stop — you are missing half your instructions.

## Your dimension: efficiency

Find wasted work the diff introduces. Reason concretely; do not micro-optimize on
instinct.

- **Redundant computation** — the same value derived twice in one scope, a lookup
  repeated inside a loop that could be hoisted.
- **Repeated I/O** — the same file read, query issued, or request made more than once
  where one result would serve.
- **Sequential independent operations** that could overlap — but only where genuinely
  independent. If they share mutable state they are not, and parallelising them is a
  defect, not an optimization.
- **Blocking work added to startup or a hot path** that could be deferred or cached.
- **Long-lived objects built from closures**, which keep the entire enclosing scope alive
  for the object's lifetime — a leak when that scope holds anything large.

**Quantify.** State how many extra calls, how much data, how often the path runs. A
finding you cannot size is a guess. "This is already fast enough, here are the numbers" is
a legitimate conclusion and worth reporting.

The commonest mistake in this dimension is optimizing something that runs once, at a scale
where it does not matter, at the cost of code the next reader must decode.
