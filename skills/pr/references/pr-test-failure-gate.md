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

When `on_test_failure = "benchmark-continue"` causes the test-failure gate (Step 0b) to be bypassed, post a comment on the **PR** with the header `## slopstop signals` followed by a fenced `json` block:

````
## slopstop signals

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
````

`tools/metrics/signals.py` parses every `## slopstop signals` comment on the ticket and
its PR and merges them newest-wins per key, so each bypass posts its own comment rather
than appending to a shared file — there is no file to append into. The comment stream
itself is the audit trail: every bypass is visible in the PR's history even though the
merged record keeps only the most recently posted `benchmark_overrides` value.
