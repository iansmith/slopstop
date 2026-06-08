# Plan: Autonomous Behavior Detail

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

## Phase 0 — unexpected test pass (Step 0d)

When some or all Phase 0 tests pass on the current code, the interactive path offers `revise / continue / abort`. In autonomous mode, consult `[autonomous] on_phase0_tests_pass`:

| Value | Action |
|---|---|
| `ask` (default) | ask interactively (same as non-autonomous) |
| `continue` | log `"[autonomous] Phase 0 tests pass unexpectedly — continuing per on_phase0_tests_pass=continue"` and proceed to Step 1 |
| `abort` | log the counts and stop: `"[autonomous] Phase 0 tests pass unexpectedly — aborting per on_phase0_tests_pass=abort"` |

## Parallel fanout — Step 6 launch confirmation (and Step 4c cap)

`on_parallel_agents` governs **two** points in the parallel path:

**Step 6 launch confirmation** (applies whenever ≥2 items are parallel-safe, i.e. any parallel plan). The interactive path asks `yes / save-only / abort`. In autonomous mode, consult `[autonomous] on_parallel_agents`:

| Value | Action |
|---|---|
| `ask` (default) | ask interactively |
| `proceed` | proceed as if `yes` — create worktrees and launch agents |
| `serial` | stop as if `save-only` — plan is saved, log `"[autonomous] on_parallel_agents=serial — plan saved, execute work items manually or re-run in serial mode"` |
| `abort` | stop: `"[autonomous] on_parallel_agents=abort — aborting fanout"` |

**Step 4c cap** (only reached when the plan recommends >4 parallel agents). The interactive path offers `merge / proceed / abort`. In autonomous mode, apply the same `on_parallel_agents` key: `proceed` → run all K agents; `serial` or `abort` → stop with the same messages as above. The cap-specific `merge` option (combine items into ≤4 units) has no autonomous equivalent — `serial` is the fallback if you want to avoid large fanouts.

## Metrics emit (Step 0d)

After Phase 0 tests are committed, if `[autonomous] metrics_emit_path` is set, update the `pipeline.json` stub (written by `:start`) with the Phase 0 test counts:

```json
{
  "phase0_tests_red": <count of failing tests>,
  "phase0_tests_pass_unexpected": <count of tests that passed when they shouldn't have, or 0>
}
```

Merge these fields into the existing stub (don't overwrite the whole file). If the stub doesn't exist yet (`:start` was called without `metrics_emit_path`), create it with just these fields plus `"ticket": "$TICKET"`.
