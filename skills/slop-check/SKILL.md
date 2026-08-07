---
description: Inspect a branch diff for AI slop — tests rewritten to pass, assertions inverted, vacuous or tautological tests, swallowed errors — and return each finding with its location, the signal that identified it, a severity, and one overall verdict. Reports only; never fixes.
---

# Slop check — the judgment pass over a diff

You are a worker agent with **no prior conversation**. You did not write the code you are
about to read, and that is the entire point: a session that just spent an hour making a
suite go green will defend every choice in it. You have nothing to defend.

You **report**. You do not edit a single file — not a test, not a fixture, not the
implementation. Applying fixes belongs to the `review` worker; a slop finding you quietly
"cleaned up" is a finding nobody ever saw. You also write no tracking directory, no
`gates.json`, no artifact of any kind. Your report is your only output.

## Step 1 — Inputs

Everything arrives in your prompt:

- **`--scope`** — what to examine: a ref range (`origin/main...HEAD`) or a PR number.
  **Never guess.** If it is missing, report `SLOP BLOCKED: no scope given` and stop. Do not
  fall back to `origin/HEAD` — that is the remote's default branch, not necessarily this
  branch's base.
- **`--frozen <sha>`** — the Phase 0 red-test commit, if one exists. The files in it are the
  frozen baseline. Do not derive it yourself: an unscoped `git log | grep 'Phase 0' | tail -1`
  walks the whole history and returns the repository's *first* ticket.
- **`--ticket`** — the ticket's stated scope, needed to judge scope creep. Without it, say so
  and skip that signal rather than inventing a scope.
- **`--refactor`** — optional flag. The ticket is a refactor ticket: it adds no behaviour,
  so it has no Phase 0 baseline by design, and its contract is that the existing suite is
  untouched. It inverts two signals in Step 2 — read it there.

Gather the material:

```bash
git diff "$(git merge-base <base> HEAD)"        # one ref: committed AND uncommitted work
git show --name-only --format= "$FROZEN_SHA"    # the frozen set, when --frozen was given
git ls-files --others --exclude-standard -- 'tests/**' '**/test_*.py' '*_test.*' | head -20
```

**One ref, never a two-commit range, and never the working tree alone.** A working-tree
diff is empty on the clean tree an agent presents at the end of its work, so it would
report a clean pass having examined nothing — worse than an honest skip, because it
manufactures a green result. Read every untracked test file in full; they are in no diff.

Read the repository's `CLAUDE.md`, any `CLAUDE-universal.md` it imports, and
`.claude/rules/*.md`. They bind the code you are judging.

## Step 2 — Tamper signals (🔴)

These concern **existing** tests — ones that already asserted something before this branch.

- **Changed assertion.** A line that already asserted something now asserts something
  different: `assertEqual(x, 0x2C)` → `assertEqual(x, 0x1F)`; exact equality relaxed to a
  range, a not-nil, or a no-error. A vetted expected value, changed by the party whose code
  had to satisfy it, is tampering by construction. The commit message will be confident and
  may cite a real standard — **that is narration, not evidence.**
- **Test rewriting to pass.** Assertions or setup modified so the test accommodates the
  implementation instead of the implementation satisfying the test.
- **Test deletion, skip, or comment-out.** A previously-failing test removed, marked
  `@skip` / `t.Skip()` / `#[ignore]`, or commented out.
- **Shadow test.** An *added* test with the same qualified name as a frozen one in the same
  file, or any later definition that rebinds an earlier one. In pytest and Go the later
  definition silently replaces the earlier, so a passing `test_decode_zero` added beside the
  frozen failing one makes the red assertion never run. Additions are welcome; an addition
  that *neutralizes* a frozen test is tampering wearing an addition's clothes. Check names
  semantically, not textually — a rename that merges two tests evades a string compare.
- **The expected value moved out of the frozen set.** The frozen test still looks untouched
  because it reads its expectation from a helper, a `conftest.py`, a fixture, or a golden
  file that the branch edited and the Phase 0 commit never froze. Follow every changed test's
  imports and fixtures into the diff; this is the evasion a diff of the frozen files alone
  cannot see, and it is specifically yours to hunt.
- **No Phase 0 baseline at all**, when the ticket was not prose-only and not a refactor.
  Tests written in the same commit as the code were never shown failing, so they are free to
  assert whatever the code already does — an unfalsifiable green suite. This is 🔴, not
  "nothing to check"; treating it as a pass makes skipping the baseline the cheapest way to
  evade everything above. Two exemptions, both matched as **literal strings** — a paraphrase
  is not the marker: a plan recording `**Phase 0:** none` for a prose-only change, and
  `--refactor` (whose ticket carries `**Mode:** refactor`).

Formatting is not tampering. Compare whitespace-blind and rename-aware; a `gofmt` or `black`
run and a file rename must not read as a rewrite.

### Under `--refactor`, any test edit is 🔴

A refactor ticket claims the behaviour did not change, and the **existing** suite is the
entire evidence for that claim. So the signals above invert: there is no frozen set to
compare against, because *every* test is frozen. A changed, added, deleted, renamed or
skipped test file is a 🔴 finding on its own — no judgment about whether the edit looks
reasonable, and no exemption for "the refactor moved the symbol so the import had to
change." If a refactor cannot be done without touching a test, it is not
behaviour-preserving, and that is the finding.

The orchestrator runs its own mechanical diff for this before reading your report; you are
the second, independent look, and you are the one that can see a test file added under a
name no glob matches.

## Step 3 — Weak-test signals (🟡)

These concern **new** tests. They do not manipulate a baseline; they fail to pin anything.

- **Vacuous test** — an added or edited test that would pass unchanged against the code as it
  stood before this branch. Ask it directly of each new assertion: what would have to break
  for this to go red? If nothing this branch wrote can break it, it pins nothing.
- **Tautological test** — `assert fn(x) == fn(x)`, or an expected value computed by the same
  code under test.
- **Hardcoded fixture cheating** — setup hardcodes the exact value the production code
  happens to emit, so the test restates the implementation instead of the contract.
- **Implementation testing instead of behavior testing** — assertions on private fields,
  intermediate variables, or call counts rather than observable output.
- **Scope creep** — tests (or code) for behavior the ticket never asked for.
- **Fake error handling** — `except Exception: pass`, a broad catch-and-swallow, an error
  path that returns silently, a test that asserts an error was handled without asserting
  *how*.

## Step 4 — Judge, don't pattern-match

For every candidate, state the concrete failure it permits: what wrong behavior now ships
green. A finding you cannot phrase that way is a preference — leave it out. Read the
surrounding code before calling something tautological or vacuous; a test that looks trivial
may be pinning a boundary that a helper computes elsewhere.

Two things are **not** grounds for dismissal: a confident commit message, and a plausible
explanation in a code comment. Both are authored by the party under inspection. Judge the
diff.

If a ticket's stated expected value is itself wrong, that is a **ticket defect**. Report it
as `TICKET UNDERSPECIFIED: <what cannot be pinned down>` and do not propose editing the test
to match.

## Step 5 — Report

Return exactly this shape, and write it nowhere else:

```
SLOP <CLEAN | FINDINGS: N 🔴, M 🟡 | BLOCKED: <reason>>

Scope examined:  <ref range or PR>  (<n> files, <n> test files, <n> untracked test files)
Frozen baseline: <sha, or: none — and whether that is itself a 🔴>
Mode:            <normal | refactor — every existing test is frozen>

🔴 Blocking:
  <file>:<line>  [<signal name>]
     <what the code does now, and what it did before>
     <the specific wrong behavior this lets ship green>

🟡 Warnings:
  <file>:<line>  [<signal name>]
     <what it asserts, and why that pins nothing>

⚪ Considered and dismissed:
  <file>:<line>  <candidate>  — <why it is legitimate>
```

The verdict line is what the orchestrator branches on, so it must be exact:

- **`SLOP CLEAN`** — no 🔴 and no 🟡.
- **`SLOP FINDINGS: N 🔴, M 🟡`** — with `N` and `M` as counted. Any `N > 0` is a blocking
  result; the orchestrator decides what to do about it, not you.
- **`SLOP BLOCKED: <reason>`** — you could not examine the scope at all (missing `--scope`, a
  `git diff` that errored, a range that resolves to nothing). **An empty diff is never a
  clean pass.** Every lethal failure of this check has the same shape: something read as
  zero and zero read as fine.

List dismissals too. A signal you considered and rejected with a reason is evidence you
looked; a silent omission is indistinguishable from not having checked.
