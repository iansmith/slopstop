# Plan: Autonomous Behavior Detail

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

## Phase 0 — unexpected test pass (Step 0d)

When some or all Phase 0 tests pass on the current code, the interactive path offers `revise / continue / abort`. In autonomous mode, consult `[autonomous] on_phase0_tests_pass`:

| Value | Action |
|---|---|
| `continue` (**default**) | log `"[autonomous] Phase 0 tests pass unexpectedly — continuing per on_phase0_tests_pass=continue"` and proceed to Step 1 |
| `ask` | ask interactively (same as non-autonomous) — stalls a headless run; set explicitly only when a human is monitoring |
| `abort` | log the counts and stop: `"[autonomous] Phase 0 tests pass unexpectedly — aborting per on_phase0_tests_pass=abort"` |

## Parallel fanout — Step 6 launch confirmation (and Step 4c cap)

`on_parallel_agents` governs **two** points in the parallel path:

**Step 6 launch confirmation** (applies whenever ≥2 items are parallel-safe, i.e. any parallel plan). The interactive path asks `yes / save-only / abort`. In autonomous mode, consult `[autonomous] on_parallel_agents`:

| Value | Action |
|---|---|
| `proceed` (**default**) | proceed as if `yes` — create worktrees and launch agents |
| `ask` | ask interactively — stalls a headless run; set explicitly only when a human is monitoring |
| `serial` | stop as if `save-only` — plan is saved, log `"[autonomous] on_parallel_agents=serial — plan saved, execute work items manually or re-run in serial mode"` |
| `abort` | stop: `"[autonomous] on_parallel_agents=abort — aborting fanout"` |

**Step 4c cap** (only reached when the plan recommends >4 parallel agents). The interactive path offers `merge / proceed / abort`. In autonomous mode, apply the same `on_parallel_agents` key: `proceed` → run all K agents; `serial` or `abort` → stop with the same messages as above. The cap-specific `merge` option (combine items into ≤4 units) has no autonomous equivalent — `serial` is the fallback if you want to avoid large fanouts.

## Adversary gap finder (Step 0f)

When the adversary finds gap tests, the interactive path presents them and asks `add all / add selected / skip`. In autonomous mode, consult `[autonomous] on_test_gaps`:

| Value | Action |
|---|---|
| `add-all` (**default**) | automatically add all gap tests and verify RED; log `"[autonomous] on_test_gaps=add-all — adding N gap tests"` |
| `ask` | ask interactively (same as non-autonomous) — stalls a headless run; set explicitly only when a human is monitoring |
| `skip` | skip adversary findings without adding; log `"[autonomous] on_test_gaps=skip — adversary ran but findings skipped"` |

## Metrics emit (Step 0d)

After Phase 0 tests are committed, post a comment on the **ticket** with the header
`## slopstop signals` followed by a fenced `json` block carrying the Phase 0 test counts:

````
## slopstop signals

```json
{
  "phase0_tests_red": <count of failing tests>,
  "phase0_tests_pass_unexpected": <count of tests that passed when they shouldn't have, or 0>
}
```
````

`tools/metrics/signals.py` parses every `## slopstop signals` comment on the ticket and its
PR and merges them newest-wins per key, so a fresh post each time Step 0d runs is
sufficient — there is no local stub file to merge into.
