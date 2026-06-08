# PR Test Failure Gate — Structured Summary and Override Record

## Structured summary format (Step 0b)

When the pre-PR test suite fails, print:

```
Pre-PR gate: tests failing.

  Regressions (tests that used to pass and now fail):
    <test name> — <brief failure reason>
    ...

  Expected failures (Phase 0 red tests not yet green):
    <test name>
    ...

  <N total failing, M regressions, K expected>
```

## Test-failure bypass — benchmark override record

When `on_test_failure = "benchmark-continue"` causes the test-failure gate (Step 0b) to be bypassed, merge this into `<metrics_emit_path>/<TICKET>/pipeline.json` (create if absent):

```json
{
  "benchmark_overrides": [
    {
      "step": "pre_pr_gate",
      "regression_count": "<M>",
      "expected_failure_count": "<K>",
      "total_failing": "<N>",
      "failing_tests": ["<test name>", "..."],
      "action": "benchmark-continue — proceeded despite failures for baseline comparison"
    }
  ]
}
```

If `benchmark_overrides` already exists in the file, **append** to the array rather than replacing it. This creates a full audit trail of every gate that was bypassed during the run.
