# `:pr` Step 1 — brief common to all four dimensions

Every Step 1 agent is given this file **and** its one dimension brief. Kept in one file
so a change to a shared rule cannot land in three briefs and miss the fourth; the
dispatch in `pr-simplify.md` concatenates the two, exactly as it concatenates the diff
and frozen-test instructions.

## Read this repository's own rules first

**Read `CLAUDE.md` at the repository root** (and any `CLAUDE-universal.md` it imports,
and any `.claude/rules/*.md`). Those rules bind you and **override anything in these
briefs that conflicts** — including the guidance below, which is deliberately generic.

Do not treat this brief as a summary of them. It is not, and it must not become one:
`CLAUDE-universal.md` is propagated byte-identically across every repository slopstop is
installed in, and a paraphrase here would drift out of sync with it silently. Read the
real file.

These briefs name **no language's conventions**. slopstop ships one brief set to
repositories spanning six languages and a 200x size range; a rule correct in one is wrong
in the others, and a plausible-looking wrong rule is worse than no rule. Where a brief
gives a language-specific example, it illustrates an idea — it is never a rule to apply.

## Do not touch these, ever

Some files are correct precisely because nobody has improved them. This is the one thing
`CLAUDE.md` may not tell you, so it is stated here:

- **Generated files.** Edit the source and regenerate; never hand-edit the output.
- **Vendored dependencies** — third-party code checked into the tree.
- **Test corpora and fixtures that must stay byte-exact** — conformance suites, golden
  files, recorded fixtures. "Improving" one silently invalidates every test that depends
  on it, and the failure surfaces far from your change.

You will not always be told which trees these are. Check `CLAUDE.md` and `.gitignore`,
and treat any directory named for test data, vendoring, generation, or third-party code
as off-limits unless the ticket explicitly says otherwise.

## Frozen Phase 0 tests

**Never modify a frozen Phase 0 test file.** The frozen set is the test files present in
the Phase 0 red-test commit — the commit whose subject matches `Phase 0: red tests`.
Identify it with:

```bash
git log --format='%H %s' | grep -m1 'Phase 0: red tests'
git show --stat --format= <that-sha>          # the listed test files are frozen
```

A frozen test's shape *is* its contract. Editing one turns a quality pass into a tamper
hard-stop two steps later, attributed to you.

## You apply your own fixes

Edit the working tree directly. Do not return a list of findings for the calling session
to act on — that session wrote this code, and is exactly the context that would rationalise
keeping it.

**Scope is the branch diff**, not the whole repository. Read wider than the diff to
understand it; change only what the diff touches, unless a fix genuinely requires an
adjacent line.

## Behavior must not change

Your changes are refactors. If you cannot convince yourself a change is
behavior-preserving, leave it and say so — a note costs nothing, a silent behavior change
costs a debugging session. The suite runs after you, but it is a backstop, not a licence.

## Sibling-convention guard

Before flagging an error-wrap, docstring, or boilerplate construct as redundant, read 2-3
sibling functions in the same file. If the pattern is the established local convention, do
**not** flag it — consistency with neighbours outranks local terseness.

## Report

- What you changed, file by file, and why.
- What you considered and deliberately did not change, and why.
- Anything outside your dimension, flagged for the human — do not fix it.
