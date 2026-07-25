# Plan: Phase 0 Mechanics (Step 0 detail)

Steps 0a through 0e in full — the *procedure*. Three companion files carry the
*reasoning*, and this file points at each rather than restating it: test-writing
priority order and the full freeze rationale in `plan-red-tests.md`, output templates in
`plan-test-results.md`, the gap finder in `plan-adversary-gaps.md`.

One deliberate exception: the two Phase 0 invariants (only-failing-tests-may-be-frozen,
and the freeze itself) appear in **three** places — here, in the `:plan` spine, and in
`plan-red-tests.md`. That is not drift. Every known evasion of the tamper gate works by
not reading the file that states them, so they are stated wherever a session might stop
reading. If you change one, change all three.

## 0a. Identify the test command for the project

Look in `task_plan.md` for a `**Test command:**` line. If present, use it. Otherwise
auto-detect from the cwd:

| Indicator | Test command |
|---|---|
| `Taskfile.yml` with a `test:` task | `task test` |
| `Makefile` with a `test:` target | `make test` |
| `package.json` with a `"test"` script + `pnpm-lock.yaml` | `pnpm test` |
| `package.json` with a `"test"` script + `yarn.lock` | `yarn test` |
| `package.json` with a `"test"` script (else) | `npm test` |
| `Cargo.toml` | `cargo test` |
| `go.mod` | `go test ./...` |
| `pyproject.toml` with pytest config | `pytest` |

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
behavior — no stubs, no skipped tests.

Priority order (most commonly missed first): edge/boundary → error/rejection →
cross-feature interaction → happy-path. Full guidance with examples:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-red-tests.md`

Record test file path(s) and names — they become Done-when criteria in Step 2.

## 0d. Run the tests; report results

Run the command from 0a. Three outcomes:

- **All new tests fail** → RED established. Print results, continue to Step 1.
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

**This commit freezes the tests.** You may ADD tests; you may not change an expected
value, loosen an assertion, skip or delete one, or amend/rebase this commit. A failing
red test says the *code* is wrong; the only sanctioned way to green it is to change the
code. If the ticket's expected value is itself wrong, take the `TICKET UNDERSPECIFIED`
halt (TD-4a) — it consumes no attempt.

Enforcement is mechanical and reads this commit as the baseline: `:pr` Step 2d (solo)
and `:run`'s tamper check (fleet).

Why a green "red" test voids the entire chain, plus the full freeze rationale:
→ Read `~/.claude/commands/slopstop-plan-refs/plan-red-tests.md`
