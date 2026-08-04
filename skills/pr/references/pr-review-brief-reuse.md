# `:pr` Step 6 — Reuse find brief

**You were also given `pr-review-brief-common.md`.** It carries the rules that bind every
find dimension: you must not write, read the repository's own `CLAUDE.md`, scope is the PR
diff, ignore generated / vendored / test-corpus files, and the report format below. If you
did not receive it, say so and stop — you are missing half your instructions.

## Your dimension: reuse and duplication

Find code in the diff that re-implements something the repository already has.

- **Search before concluding something is new.** Grep the shared and utility modules and
  the files adjacent to the change. A helper that already exists under a different name
  is the most common finding here, and the only way to find it is to look.
- **Near-identical code paths** introduced by this diff — two branches differing in one
  value, three functions differing in a type.
- **A constant, string, or magic value defined a second time.** One definition per value.
- **A pattern the codebase solves a standard way, solved here differently.** Mirror the
  existing vocabulary; a parallel term for the same concept is a finding.

Two things that look like reuse findings and are not: code that is superficially similar
but diverges under change, and an abstraction with one caller and an awkward signature.
Both are worse after "deduplication". Say so if you considered and rejected one.
