# Plan: Test Result Output Templates (Step 0d detail)

## All new tests fail (RED state established)

```
Phase 0: <N> red tests written and failing as expected. RED state established.
  <test 1 name>  FAIL
  <test 2 name>  FAIL
  ...

Proceeding to investigation.
```

## Assertion not reached (not yet red)

Emitted when a test fails on a missing symbol, import, or compile error rather than
on its assertion — the compile error is not evidence, since the assertion itself
was never exercised.

```
Phase 0: <n> test(s) failed before reaching an assertion — not yet red.
  <test id>  FAIL  (assertion not reached — <missing symbol / import error>)
  ...

Add the stub per Step 0c-stub and commit it separately as
"[$TICKET] Stubs for <summary>", then re-run 0d.
```

## Some or all new tests pass (unexpected)

```
Phase 0: <N> of <M> new tests PASS on the current code.

  <test name>  PASS  (expected to fail; bug may not be present or test is wrong)
  ...

Either the ticket's reported bug is already fixed, or the tests aren't exercising the right behavior. What would you like to do?

  - revise:        I'll re-read the ticket and rewrite the passing tests to actually exercise the buggy behavior.
  - continue:      Proceed anyway (you've decided the tests are correct and the ticket is questionable).
  - abort:         Stop here. Plan not generated.
```

## Tests don't run cleanly

```
Phase 0: tests don't run cleanly.

<captured error output>

Fix the test harness, or revise the tests, and re-run /slopstop:plan.
```

