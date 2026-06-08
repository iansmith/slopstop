# Plan: Serial Implementation Detail (Step 3a detail)

Execute each work item from the plan in order. For each item:

1. Read the item's **Detailed steps** from `task_plan.md`.
2. Implement the changes described.
3. Run the **full** test suite (not just the item's specific tests): `<test_command>`.
4. Verify two things — both must be true before you commit:
   a. The item's **Done when** test(s) turn green.
   b. **No regressions**: every test that was in the regression baseline (Step 0b) and was passing before this item's implementation is still passing. Any baseline-passing test that is now failing is a regression introduced by this item — fix it before committing.
5. If the item's own tests are green but regressions are present: diagnose the regression, fix it, re-run the full suite. Do NOT commit until both conditions hold.
6. Commit: `git add -A && git commit -m "[$TICKET] <item name>"` with the standard Co-Authored-By trailer.

## After all items are implemented

- Run the full test suite one final time.
- All Phase 0 red tests must be green. All regression-baseline tests must still pass.
- Print a completion summary:
  ```
  Serial implementation complete — $TICKET.
  Items implemented: <N>
  Tests: <pass_count> passed, <fail_count> failed
  Phase 0 red tests: all green / <N> still failing
  Regressions vs. baseline: none / <N> tests regressed
  Ready for /slopstop:pr
  ```

If any item's tests cannot be made green after reasonable debugging effort (including fixing any regressions they introduce), commit what's done with a `[BENCH-N] WIP:` prefix, note the failure and the specific regression in `progress.md`, and stop — do not proceed to items that depend on the failing one.
