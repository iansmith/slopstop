# Plan: Phase 0 Mechanics (Step 0 detail)

Steps 0a through 0e in full — the *procedure*, including 0c-stub (stubs for
not-yet-existing surface), which sits between 0c and 0d. Three companion files carry the
*reasoning*, and this file points at each rather than restating it: test-writing
priority order and the full freeze rationale in `plan-red-tests.md`, output templates in
`plan-test-results.md`, the gap finder in `plan-adversary-gaps.md`.

One deliberate exception: the two Phase 0 invariants (only-failing-tests-may-be-frozen,
and the freeze itself) appear in **three** places — here, in the `:plan` spine, and in
`plan-red-tests.md`. That is not drift. Every known evasion of the tamper gate works by
not reading the file that states them, so they are stated wherever a session might stop
reading. If you change one, change all three.

## When Phase 0 does not apply: prose-only changes

**A change that alters only documentation prose gets no Phase 0 red tests.** Skip
straight to implementation and review.

A test asserting that a particular English sentence appears in a markdown file pins
*wording*, not behavior. It cannot fail for a reason review would miss, and it turns
every later legitimate reword into a red suite — which then costs a ticket, an
adversary pass, and a judgement call about whether updating it is tampering. That is
pure overhead, and it is the dominant cost on a repo whose product is mostly prose.

The exception is narrow and worth keeping: **structural invariants that a human cannot
check by reading.** A mirrored file matching its reference byte-for-byte, a derivation
still present in the script that implements a gate, a file existing where a manifest
says it does. Those are properties, not phrasing. Test those; do not test that a
paragraph is worded a particular way.

### Record it — `:pr` Step 2d reads this

Taking this path, write exactly this line into `task_plan.md`:

```
**Phase 0:** none — prose-only change
```

**This is the marker, and it is the whole interface.** `:pr` Step 2d hard-stops when no
Phase 0 red-test commit exists, and this line is its one sanctioned exemption
(`~/.claude/commands/slopstop-pr-refs/pr-slop-detection.md` § Step 2d). Write it verbatim —
`:pr` matches the literal string `**Phase 0:** none`, so a paraphrase reads as no marker at
all and the tamper gate stops the PR.

Record it **positively**, and do not rely on the absence of anything. The exemption used to
work only because a prose-only run happened not to cache a `**Test command:**` line — a
side-effect, not a contract, and one any later session could undo by resolving the test
command for an unrelated reason.

Everything below applies to changes with executable behavior.

## 0a. Identify the test command for the project

Look in `task_plan.md` for a `**Test command:**` line. If present, use it. Otherwise
auto-detect from the cwd using the shared table:
→ Read `~/.claude/commands/slopstop-plan-refs/test-command-resolution.md`

If none match (or multiple plausibly do), ask once: `"What's the test command? (paste
it, or 'skip')"`. On a real answer, cache it by writing `**Test command:** <cmd>` at
the top of `task_plan.md`. On `skip`: warn and continue to Step 1 without Phase 0.

## 0b. Establish the regression baseline and identify expected behaviors

Run the existing suite **first**. Record as the **regression baseline**:
`N passing, M failing, K errors`, noting pre-existing failures separately. Step 3a's
commit gate compares against this, so it has to be captured before anything changes.

Then read `task_plan.md`'s `## Original description` and list the expected behaviors,
constrained by `$ARGUMENTS`.

## 0c. Write the red tests

Find where existing tests live. Add new tests for the expected behavior. Each must
have a clear name, use the existing framework and fixtures, and actually exercise the
behavior — **no stub tests** (a test that asserts nothing, or asserts only what it
itself set up), no skipped tests.

That forbids stub *tests*. It says nothing about production **stubs**, which 0c-stub
below introduces on purpose — the two senses of the word are different things and
only one is banned here.

Priority order (most commonly missed first): edge/boundary → error/rejection →
cross-feature interaction → happy-path. Full guidance with examples:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-red-tests.md`

Record test file path(s) and names — they become Done-when criteria in Step 2.

## 0c-stub. Stubs, when a red test needs surface that does not exist yet

A red test against a missing symbol fails at **compile/import** — the assertion is never
reached. That is not evidence: the test could assert something already true and still
"fail". Add a stub so the test reaches its assertion and fails *there*.

**A stub is non-satisfying by construction.** It must be structurally incapable of making
any Phase 0 test pass: return a **sentinel that reaches and fails the assertion** — a
value that cannot equal anything asserted. A zero value, empty collection, or default
that might coincidentally satisfy an assertion is forbidden.

`panic("not implemented") and raise NotImplementedError are not permitted stub bodies: they fail without reaching the assertion.`
Same defect as the compile error, under a different name.

**Stubs go in the Phase 0 commit, alongside the tests.** They are not frozen: Step 0e
records `meta.frozen` as the **test files** it staged, and both tamper gates read that,
so implementing a stub is an ordinary code change. Keep them minimal — a stub is
scaffolding, and one still present unchanged at the end of the ticket is a failure.

Step 0e also records the stub paths themselves, as `meta.stubs`. That list is what lets
`:pr` Step 2f rebuild this exact sentinel later: without it, a test written against a stub
cannot even be collected against the base commit, and the vacuity gate returns
inconclusive for the entire class of tickets that introduce new surface. The sentinel rule
above is what makes that reconstruction sound — a stub that cannot satisfy any assertion
turns "the test still passes" into real evidence of a vacuous test.

**Re-run the 0b regression baseline before committing.** A stub is real production surface
and can break an existing test; unchecked, that breakage surfaces later at Step 3a blamed
on the wrong work item.

## 0d. Run the tests; report results

Run the command from 0a. Four outcomes:

- **All new tests fail** → RED established. Print results, continue to Step 1.
- **A test fails without reaching its assertion** — a missing symbol, an import or
  compile error → **not yet red.** The assertion was never exercised, so nothing was
  proven about it. Go back to 0c-stub and add the stub, then re-run. Do not freeze
  this: a compile error is not evidence that the expected value is wrong, only that
  the surface is absent.
- **Some or all pass** → surface to the user with revise / continue / abort.
  **Whatever is chosen, a test that passed here is NOT red and must not enter 0e's
  commit** — a passing "red" test asserts what the code already does, which is
  exactly the unfalsifiable-suite failure the freeze exists to prevent. Revise it
  until it fails, or take the `TICKET UNDERSPECIFIED` halt if the ticket's
  expectation is what's wrong.
- **Tests don't run** → stop with the captured error output.

Record which tests failed. 0e stages **only those**.

> **`continue` is a dead end, by design.** If every red test passed and you continue
> anyway, 0e writes **no Phase 0 commit** — and `:pr` Step 2d then fires 🔴 *"no
> Phase 0 red-test commit"* and hard-stops. That is not a bug to route around: a
> suite that cannot fail proves nothing, so there is no honest path from here to a
> PR. The real options are **revise** until the tests fail, or **halt**
> (`TICKET UNDERSPECIFIED`) if the ticket's expectation is the thing that's wrong.
> `on_phase0_tests_pass = "continue"` buys an agent nothing but a later stop.

Exact output-format templates for each outcome:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-test-results.md`

## 0e. Commit the red tests — and freeze them

**Only tests observed FAILING at 0d may enter this commit** (see 0d above — the rule
and its consequence are stated there). Format the staged test files before committing,
so the baseline is canonical and a later formatting run produces no hunks.

```
git add <the-tests-from-0c-that-FAILED-at-0d>
git commit -m "[$TICKET] Phase 0: red tests for <one-line summary of behaviors>" \
           -m "These tests describe the expected post-fix behavior. They fail on current code." \
           -m "Co-Authored-By: Claude <model> using slopstop <noreply@anthropic.com>"
```

Stage only the red-test files, **by path** — never unrelated uncommitted work.

`git add <path>` stages the **whole file**, so a file holding both a test that failed
at 0d and one that passed contaminates the baseline with a green test — the exact thing
the line above forbids. When that happens, either isolate the failing tests in their own
file or stage hunk-by-hunk (`git add -p`). Before committing, check
`git diff --cached` and confirm it contains only tests observed failing at 0d.

**Record the baseline in `gates.json`** — write `meta.red_sha` (this commit's sha),
`meta.frozen` (the **test file paths** you staged, excluding any stubs) and `meta.stubs`
(the **stub file paths** you staged, and nothing else — `[]` when the ticket needed none).
The tamper gates read the first two rather than re-deriving them from the commit, which is
what keeps stubs in the same commit from being frozen; `:pr` Step 2f reads `meta.stubs` to
reconstruct the sentinel when it re-runs a changed test against the base. Schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`.

Record `meta.stubs` **because you staged it**, never by asking later what in the commit
was not a test. You know the list here and nowhere downstream does; "the non-test files in
the Phase 0 commit" would sweep in anything that rode along, which is the same
re-derivation hazard `meta.frozen` exists to remove, pointed the other way. Write `[]`
rather than omitting the key — Step 2f treats an absent key as an old `gates.json` and
falls back, while `[]` tells it there was genuinely nothing to copy.

**This commit freezes the tests.** You may ADD tests; you may not change an expected
value, loosen an assertion, skip or delete one, or amend/rebase this commit. A failing
red test says the *code* is wrong; the only sanctioned way to green it is to change the
code. If the ticket's expected value is itself wrong, take the `TICKET UNDERSPECIFIED`
halt (TD-4a) — it consumes no attempt.

Enforcement is mechanical and reads this commit as the baseline: `:pr` Step 2d (solo)
and `:run`'s tamper check (fleet).

Why a green "red" test voids the entire chain, plus the full freeze rationale:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-red-tests.md`
