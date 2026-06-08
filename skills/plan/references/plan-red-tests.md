# Plan: Red Tests Priority Order (Step 0c detail)

Write tests in this priority order — the most commonly missed cases come first:

1. **Edge / boundary cases** (empty inputs, zero, max values, off-by-one boundaries, empty collections, missing optional fields). These are the cases most likely to be overlooked in the implementation and to slip through a "happy-path-only" review. Write at least two boundary tests per new behavior.

2. **Error / rejection cases** (invalid inputs, conflicting states, operations attempted out of order, missing required values). Each error condition the ticket mentions should have a test that verifies the correct error is raised / the correct early-exit behavior occurs.

3. **Cross-feature interaction cases** (how does the new behavior compose with features already implemented in prior work?). If this ticket extends a system that already handles cases A, B, C — write tests that pass A/B/C data through the new code path to ensure the new feature doesn't shadow or break existing handling. These are the regressions most likely to surface in later checkpoints, so catching them in red form NOW locks in the requirement.

4. **Happy-path cases** (the basic "it works" test). One or two is enough — coverage here is already the most natural thing to write, so don't over-index on it at the expense of the three categories above.
