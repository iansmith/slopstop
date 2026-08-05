# PR Autonomous Behavior — Full Reference

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.


## Test failure (Step 2c)

When tests fail, the interactive path offers `fix / commit anyway / abort`. In autonomous mode, consult `[autonomous] on_test_failure`:

| Value | Action |
|---|---|
| `abort` (**default**) | log the failure summary and stop: `"[autonomous] tests failed — aborting per on_test_failure=abort"` |
| `ask` | ask interactively — stalls a headless run; set explicitly only when a human is monitoring |
| `commit-anyway` | log and continue to Step 3 with `Note: N test(s) failing at commit time` body line |
| `benchmark-continue` | log, post a `## slopstop signals` PR comment with a `benchmark_overrides` entry (same format as Step 0's benchmark override record, with `"step": "pre_commit_test"`), continue to Step 3 with a prominent `⚠️ BENCHMARK OVERRIDE: N test(s) failing` note in the commit body and PR body |

`benchmark-continue` also governs the Step 0 pre-PR gate — it is the single config key that controls both places where test failures can block a PR.

## Red-test tamper gate (Step 2d)

Mechanical, and **not** governed by `on_slop_findings`. When 🔴 (a red-test assertion changed after the RED commit, a test removed or skipped, or no RED commit at all), the interactive path asks for an override reason. In autonomous mode, consult `[autonomous] on_redtest_tamper`:

| Value | Action |
|---|---|
| `hard-stop` (**default**) | stop on any 🔴; no override allowed; log `"[autonomous] on_redtest_tamper=hard-stop — red-test tampering detected, refusing to proceed"` |
| `warn` | log the finding to the ticket and post a `## slopstop signals` PR comment with a `benchmark_overrides` entry, continue. Use only while evaluating a new model tier — `:run`'s tamper check remains the external backstop. |

There is deliberately **no `skip`**. `on_slop_findings` defaults to `skip` itself (a judgment gate, not a mechanical one — `:run`'s tamper check remains the external backstop for fleet agents), so a shared knob here would silently disable this gate too, for exactly the agents it exists to police. This gate's default stays the strict value, not the permissive one: it polices ground-truth facts (was there a recorded RED commit, was an assertion changed), not a judgment call, so there is no scenario where skipping it by default is the safe choice.

## Slop detection (Step 2e)

When 🔴 slop findings are present, the interactive path asks for an override reason. In autonomous mode, consult `[autonomous] on_slop_findings`:

| Value | Action |
|---|---|
| `skip` (**default**) | skip slop detection entirely; log `"[autonomous] on_slop_findings=skip — slop detection bypassed"` |
| `ask` | ask interactively (same as non-autonomous) — stalls a headless run; set explicitly only when a human is monitoring |
| `hard-stop` | if any 🔴 findings present: hard-stop, no override allowed; log `"[autonomous] on_slop_findings=hard-stop — stopping on 🔴 slop findings, no override allowed"` |

> **Note:** `on_slop_findings` is only consulted when Step 2e actually runs. Passing `--no-adversary` or `--no-test` skips Step 2e entirely before this config is checked — those flags override `on_slop_findings`, including `hard-stop`. **Neither flag skips Step 2d**: the tamper gate is keyed to a recorded fact (does `task_plan.md` record a Phase 0 baseline?), never to an argument the policed agent supplies.

