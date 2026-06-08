# PR Autonomous Behavior — Full Reference

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

## Simplify confirmation (Step 1)

When the simplify agent modifies the working tree, the interactive path asks `continue / abort`. In autonomous mode, consult `[autonomous] on_simplify_changes`:

| Value | Action |
|---|---|
| `ask` (default) | ask interactively |
| `accept` | log `"[autonomous] simplify changes accepted per on_simplify_changes=accept"` and proceed to Step 2 |
| `reject` | log the delta line count and stop: `"[autonomous] simplify changes rejected per on_simplify_changes=reject"` |

Record the simplify line delta (lines added + removed from the before/after diff) for the metrics emit below.

## Test failure (Step 2c)

When tests fail, the interactive path offers `fix / commit anyway / abort`. In autonomous mode, consult `[autonomous] on_test_failure`:

| Value | Action |
|---|---|
| `ask` (default) | ask interactively |
| `abort` | log the failure summary and stop: `"[autonomous] tests failed — aborting per on_test_failure=abort"` |
| `commit-anyway` | log and continue to Step 3 with `Note: N test(s) failing at commit time` body line |
| `benchmark-continue` | log, write an override record to `pipeline.json` (same format as Step 0's benchmark override record, with `"step": "pre_commit_test"`), continue to Step 3 with a prominent `⚠️ BENCHMARK OVERRIDE: N test(s) failing` note in the commit body and PR body |

`benchmark-continue` also governs the Step 0 pre-PR gate — it is the single config key that controls both places where test failures can block a PR.

## Red-findings fix loop (Step 6-claude, `on_red_findings`)

After `/code-review` completes, the interactive path presents findings and stops. In autonomous mode, consult `[autonomous] on_red_findings` (Claude backend only — `$PR_BACKEND == "claude"`):

| Value | Action |
|---|---|
| `ask` (default) | present findings and stop (same as non-autonomous) |
| `skip` | log 🔴 finding count, do NOT apply fixes, proceed to Step 8 |
| `fix-and-retry` | enter the fix-and-retry loop below |

> **Conflict with `[pr_review] fix = true`**: Do NOT set both `fix = true` in `[pr_review]` AND `on_red_findings = "fix-and-retry"` in `[autonomous]`. `fix = true` causes `/code-review` to auto-commit fixes itself; `fix-and-retry` then tries to apply them again, double-committing. If both are set, **abort `:pr` with an error**: `"[autonomous] config error: on_red_findings=fix-and-retry conflicts with [pr_review] fix=true. Set [pr_review] fix=false or change on_red_findings. Aborting."` Do not silently degrade.

**`fix-and-retry` loop** (max 3 iterations; terminates early when 🔴 count reaches 0 or no iteration reduces it):

1. For each 🔴 finding: apply the fix directly to the working tree (instruct the agent to make the change, guided by the finding's file/line/description).
2. Re-run the test suite (Step 2b's test command). If tests fail: stash the applied-but-uncommitted fixes (`git stash push -m "$TICKET autonomous fix-and-retry abandoned — tests failed"`) and log the stash ref so the user can `git stash pop` to inspect. Then break out of the loop.
3. Commit all applied fixes:
   ```
   git commit -m "$(cat <<'EOF'
   [$TICKET] code-review fix-and-retry (iteration N)

   Refs: $TICKET
   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
   EOF
   )"
   ```
4. Push: `git push origin $BRANCH`.
5. Re-run Step 6-claude (invoke `/code-review` again with the same effort). Increment iteration counter.
6. If 🔴 count is 0 after the review: clean ✅, proceed to Step 8.
7. (Iterations 2+ only) If 🔴 count didn't decrease from the previous iteration: log `"[autonomous] fix-and-retry: 🔴 count did not decrease after iteration N — stopping loop to avoid spin"` and proceed to Step 8 with the remaining findings. Iteration 1 always runs regardless of count — there is no "previous" to compare against.
8. If max iterations reached: log remaining 🔴 count and proceed to Step 8.

## Metrics emit (Step 8)

After the review step completes (and after the fix-and-retry loop if applicable), if `[autonomous] metrics_emit_path` is set, merge the following fields into `<metrics_emit_path>/<TICKET>/pipeline.json`. If the file does not exist (e.g. `:start` ran without `metrics_emit_path` set), create it with these fields plus `{"ticket": "$TICKET"}`:

```json
{
  "simplify_line_delta": "<total lines changed by simplify, or 0 if skipped/rejected/no changes>",
  "review_red_count": "<final 🔴 count after any fix-and-retry loops, or 0 if clean>",
  "review_yellow_count": "<final 🟡 count, or 0>",
  "cc_violation_count": "<number of 🔴 CC violations at PR time, or 0>",
  "cc_elevated_count": "<number of 🟡 elevated functions at PR time, or 0>",
  "cc_max": "<highest CC value seen across modified files, or 0 if radon skipped>"
}
```
