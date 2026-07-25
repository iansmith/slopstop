# Plan: Serial Paths (Step 3 hand-off and Step 3a detail)

Two different serial paths live here. **Non-autonomous `:plan` stops at Step 3** and
hands off to the human; **autonomous `:plan` continues into Step 3a** and implements.

## Step 3 — the non-autonomous serial hand-off

Fewer than 2 items parallel-safe, and autonomous mode is off. Print this, then stop:

```
Serial execution — no agents needed.
Plan written to $TRACKING_DIR/$TICKET/task_plan.md.
Run /slopstop:update as you go to checkpoint progress; /slopstop:pr when ready.
Leave implementation work UNCOMMITTED until :pr — the simplify pass in :pr Step 1
runs against the working tree and needs the changes to be unstaged/uncommitted.
Commit only after :pr has run simplify and you have staged the result.
```

The uncommitted-until-`:pr` instruction is the load-bearing line: `:pr` Step 1 skips
the simplify pass entirely when `$DIRTY` is empty, so work committed early is work
that never gets simplified, and universal §1 makes that pass mandatory before a commit.

## Step 3a — autonomous serial implementation

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
