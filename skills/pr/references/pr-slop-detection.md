# PR Slop Detection Gate — Full Reference

## Slop-detection agent prompt

Spawn an agent with these instructions:

> "Review the uncommitted diff (`git diff HEAD`). For each modified or added test file, check whether any of the slop patterns below are present. For each finding, report: pattern type (🔴 or 🟡), file:line, what the code does, and why it's a slop pattern."

## Slop pattern catalog

### 🔴 Hard-stop patterns (require explicit override to proceed)

| Pattern | Description |
|---|---|
| **Test rewriting to pass** | Modifying an existing test's assertions or setup to make it pass rather than fixing the underlying code |
| **Expectation inversion** | Changing `assert X == expected` to `assert X == actual`, or relaxing an assertion threshold so the current output becomes the accepted value |
| **Test deletion or skip** | Removing a test or marking it `@skip` / `@pytest.mark.skip` that was previously failing |

### 🟡 Warning patterns (surface and warn; user can proceed without override)

| Pattern | Description |
|---|---|
| **Implementation testing instead of behavior testing** | New tests assert on internal state (private fields, intermediate variables, call counts) rather than observable outputs |
| **Tautological tests** | `assert fn(x) == fn(x)` or expected value derived from the same code under test |
| **Scope creep tests** | New tests added that test behavior unrelated to the ticket's stated scope |
| **Fake error handling** | `except Exception: pass`, broad catch-and-swallow, or error paths that return silently |
| **Hardcoded fixture cheating** | Test setup hardcodes the exact value the production code produces, making the test trivially pass |

## Interactive override flow (when 🔴 findings present)

```
STOP — slop-detection found 🔴 findings:

  🔴 test_foo.py:42  [TEST REWRITING]
     assert expected_result == 99  → was: assert expected_result == compute(x)
     Reason: assertion was relaxed to match implementation output rather than expected behavior.

Proceed requires an explicit override reason. This will be recorded in pipeline.json.
Enter override reason (or 'abort' to stop): _
```

Record to `<metrics_emit_path>/<TICKET>/pipeline.json` using the `benchmark_overrides` append-to-array pattern (create file if absent):

```json
{
  "benchmark_overrides": [
    {
      "step": "pre_pr_slop_gate",
      "slop_findings": [
        {"severity": "🔴", "pattern": "test_rewriting", "file": "test_foo.py", "line": 42, "detail": "..."}
      ],
      "action": "override — <user's reason>"
    }
  ]
}
```

If `benchmark_overrides` already exists in the file, **append** to the array rather than replacing it.

## 🟡 Warnings presentation (non-blocking)

```
⚠️  Slop-detection found 🟡 warnings (not blocking):

  🟡 test_bar.py:18  [SCOPE CREEP]
     New test added for feature Y, unrelated to BILL-88's stated scope.

Proceeding to commit. Address these in a follow-up if needed.
```

## Clean pass

```
Slop detection: clean ✅ — no slop patterns found.
```

## Autonomous path

When running in autonomous mode (`[autonomous] enabled = true`), consult `[autonomous] on_slop_findings`:

| Value | Action |
|---|---|
| `ask` (default) | ask interactively (same as non-autonomous) |
| `skip` | skip slop detection entirely; log `"[autonomous] on_slop_findings=skip — slop detection bypassed"` |
| `hard-stop` | if any 🔴 findings present: hard-stop, no override allowed; log `"[autonomous] on_slop_findings=hard-stop — stopping on 🔴 slop findings, no override allowed"` |
