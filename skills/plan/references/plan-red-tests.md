# Plan: Red Tests Priority Order (Step 0c detail)

Write tests in this priority order — the most commonly missed cases come first:

1. **Edge / boundary cases** (empty inputs, zero, max values, off-by-one boundaries, empty collections, missing optional fields). These are the cases most likely to be overlooked in the implementation and to slip through a "happy-path-only" review. Write at least two boundary tests per new behavior.

2. **Error / rejection cases** (invalid inputs, conflicting states, operations attempted out of order, missing required values). Each error condition the ticket mentions should have a test that verifies the correct error is raised / the correct early-exit behavior occurs.

3. **Cross-feature interaction cases** (how does the new behavior compose with features already implemented in prior work?). If this ticket extends a system that already handles cases A, B, C — write tests that pass A/B/C data through the new code path to ensure the new feature doesn't shadow or break existing handling. These are the regressions most likely to surface in later checkpoints, so catching them in red form NOW locks in the requirement.

4. **Happy-path cases** (the basic "it works" test). One or two is enough — coverage here is already the most natural thing to write, so don't over-index on it at the expense of the three categories above.

## Step 0e — why the baseline must actually be RED

The freeze, the `:pr` Step 2d tamper gate, and `:run` Gate 0 all rest on one premise: **the
commit titled `Phase 0: red tests` contains tests that were observed FAILING.** Everything
downstream diffs against it and asks *"did this change?"* — never *"was it ever red?"*

So a green test frozen as the baseline makes every later diff **clean by construction**.
The gates all pass. The suite is green. And nothing was ever proven.

That is why `on_phase0_tests_pass` may not authorize the commit. It governs what the agent
does *next* — revise, continue, abort — but a test that passed at 0d is not a red test, and
staging it as one is not a judgment call the config gets to make. If nothing failed, there
is no Phase 0 commit; a missing baseline is itself 🔴 / FAIL downstream, which is the
correct and honest outcome.

**The cheapest evasion of the whole freeze was never changing an assertion — it is never
writing a falsifying one.** SOP-110 (sophie, `stt-20260713-1938`) took exactly that route:
tests shipped in the same commit as the code, never shown failing, free to assert whatever
the code already did. Every gate was green.

The commit body claims *"They fail on current code."* That claim is load-bearing. Keep it
true.

## Formatting the baseline

Run the project's formatter over the staged test files **before** committing. The tamper
diff is whitespace-blind, but a canonical baseline means a later `gofmt`/`black` run
produces no hunks at all — so the gate never has to distinguish a reformat from a rewrite,
and a false positive can never cost a ticket.
