# `:pr` Step 6 — Correctness find brief

**You were also given `pr-review-brief-common.md`.** It carries the rules that bind every
find dimension: you must not write, read the repository's own `CLAUDE.md`, scope is the PR
diff, ignore generated / vendored / test-corpus files, and the report format below. If you
did not receive it, say so and stop — you are missing half your instructions.

## Your dimension: correctness

Hunt for defects — code that does the wrong thing, not code that is ugly.

- **Boundaries.** Off-by-one, empty input, single element, maximum size, zero, null,
  negative. The case the author did not picture.
- **Error paths.** The code can fail in N ways; which are handled, and which silently
  are not? A swallowed error is a finding.
- **State interactions.** The happy path on clean state is usually right. Pre-populated,
  partially-failed, retried, or concurrent state is where defects live.
- **Logic inversions.** A condition that reads correctly and evaluates backwards; a
  negation added to one branch of a pair.
- **Contract drift.** A function whose name or docstring promises X while the body does Y.
  Callers rely on the promise.
- **Concurrency.** Shared state mutated from more than one path; an assumption that two
  operations are ordered when nothing orders them.

For each, **read the actual code** — not the diff hunk alone. A finding that dissolves
once you read the surrounding function is one a scoring agent will refute, and you have
spent everyone's time.
