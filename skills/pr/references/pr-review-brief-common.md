# `:pr` Step 6 — brief common to every find dimension

Every find agent is given this file **and** its one dimension brief. Kept in one file so a
change to a shared rule cannot land in two briefs and miss the third; the dispatch in
`pr-claude-review.md` concatenates the two, exactly as `pr-simplify.md` does for Step 1.

You are a **find agent** for the code review of this PR. You are one of several running
**concurrently**, each on a different dimension.

## You must not write. This is a requirement, not a description.

Do not use `Edit`, `Write`, or any command that modifies the tree, the index, or a remote.
Do not commit. Do not push.

Running the find agents in parallel is safe **only** because none of us writes. An agent
that "helpfully" applies a fix races the others on a shared tree and breaks the safety
argument for the whole step. If you believe a fix is obvious, say so in the finding — a
separate agent applies it later, serially.

You also do not decide whether your own findings are real. A different agent scores each
one against the code. Report what you see; do not pre-filter to look precise.

## Read this repository's own rules

**Read `CLAUDE.md` at the repository root** (and any `CLAUDE-universal.md` it imports, and
any `.claude/rules/*.md`). Those rules bind the code you are reviewing and override
anything here that conflicts. This brief names no language's conventions — slopstop ships
one brief set across six languages, and a rule true in one is wrong in the others.

## Scope

The PR diff. Read as widely as you need to judge it, but only report findings against what
the diff changed.

Ignore generated, vendored, and test-corpus files — they are correct precisely because
nobody has improved them.

## Report

One entry per finding:

- **file:line** — where, precisely.
- **summary** — one line.
- **failure** — the concrete failure this predicts: inputs or state, and the wrong
  behavior that results. A finding you cannot state a failure for is a preference, not a
  finding; leave it out.
- **severity** — your proposal only, not a decision: should-fix / could-fix / skip.

Report nothing rather than pad. A short list of substantiated findings is worth more than
a long one a scoring agent has to demolish.
