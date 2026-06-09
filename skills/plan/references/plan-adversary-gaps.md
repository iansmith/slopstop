# Plan: Adversary Gap Finder (Step 0f detail)

## Adversary agent prompt template

```
You are an adversary code-reviewer. Your job is to attack the Phase 0 test suite
for gaps — NOT to implement anything.

Read the Phase 0 test files written in Step 0c. Apply the six attack vectors below.
For each gap found, provide:
  (a) what case is missing,
  (b) why it matters,
  (c) a concrete test function that would cover it.

Report all gaps. Do NOT suggest implementation changes. Do NOT rewrite existing tests.
```

## Six attack vectors

1. **Boundary omissions** — off-by-one, empty input, single-element, max-size, zero/null cases not covered.

2. **Error path gaps** — the code can throw or reject in N ways; the tests cover M < N of them.

3. **State interaction gaps** — happy path tested on clean state but not on pre-populated or partially-failed state.

4. **Specification drift** — test name says X but assertion tests Y; the test verifies the wrong property.

5. **False negatives** — tests that pass even if the implementation is completely wrong (assertion checks a value the test itself sets up, not a value the implementation computes).

6. **Coverage asymmetry** — multiple tests for the same easy case, zero tests for the hard case.

## Interaction format

Present findings and ask how to proceed:

```
Adversary found N gap(s) in Phase 0 tests:

  1. [BOUNDARY] test_<name>: missing empty-input case — <why it matters>
     Suggested test: test_<behavior>_with_empty_input
  2. [ERROR PATH] test_<name>: throws on invalid X but only the valid path is tested — <why>
     Suggested test: test_<behavior>_raises_on_invalid_x
  3. [FALSE NEGATIVE] test_<name>: asserts on fixture value, not computed value — always passes
     Suggested test: test_<behavior>_computes_correct_value
  ...

Add these tests?  add all / add selected <1,3,...> / skip
```

## If adversary agent unavailable

Fall back to an inline checklist: read the test files yourself and check each attack vector manually. Work through the list one by one and report any gaps found before asking add all / add selected / skip.

## RED verification

After adding gap tests (if any were selected), run the test command from Step 0a. All added gap tests must FAIL on the current code — they are Phase 0 tests too.

If any added gap test passes, surface to user with the same `revise / continue / abort` pattern as Step 0d:

```
Adversary gap test(s) pass on current code (expected to fail):

  <test name>  PASS  (expected to fail — may test a case that's already handled)

  - revise:    Rewrite the passing test(s) to actually exercise the missing behavior.
  - continue:  Proceed anyway (you've confirmed the gap is already covered).
  - abort:     Stop here. Adversary gap tests not committed.
```

## Commit (if tests were added and verified RED)

```
git add <adversary-test-files>
git commit -m "[$TICKET] Phase 0: adversary gap tests — <N> cases added" \
           -m "Gap tests identified by adversary review. Fail on current code." \
           -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Only stage the adversary gap test files explicitly by path — do NOT include unrelated changes.

## If no gaps found

Print:

```
Adversary: no gaps found — Phase 0 test suite looks comprehensive.
```

Continue to Step 1 silently. No commit needed.
