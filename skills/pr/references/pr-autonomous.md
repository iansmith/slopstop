# PR Autonomous Behavior — Full Reference

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

## Simplify confirmation (Step 1)

When the simplify agent modifies the working tree, the interactive path asks `continue / abort`. In autonomous mode, consult `[autonomous] on_simplify_changes`:

| Value | Action |
|---|---|
| `accept` (**default**) | log `"[autonomous] simplify changes accepted per on_simplify_changes=accept"` and proceed to Step 2 |
| `ask` | ask interactively — stalls a headless run; set explicitly only when a human is monitoring |
| `reject` | log the delta line count and stop: `"[autonomous] simplify changes rejected per on_simplify_changes=reject"` |

Once the simplify pass finishes, post a comment on the **PR** with the header
`## slopstop signals` followed by a fenced `json` block carrying the line delta (lines
added + removed from the before/after diff, `0` if skipped/rejected/no changes):

````
## slopstop signals

```json
{"simplify_line_delta": <N>}
```
````

`tools/metrics/signals.py` parses every `## slopstop signals` comment on the ticket and
its PR and merges them newest-wins per key — this is the only step that owns
`simplify_line_delta`.

## Test failure (Step 2c)

When tests fail, the interactive path offers `fix / commit anyway / abort`. In autonomous mode, consult `[autonomous] on_test_failure`:

| Value | Action |
|---|---|
| `abort` (**default**) | log the failure summary and stop: `"[autonomous] tests failed — aborting per on_test_failure=abort"` |
| `ask` | ask interactively — stalls a headless run; set explicitly only when a human is monitoring |
| `commit-anyway` | log and continue to Step 3 with `Note: N test(s) failing at commit time` body line |
| `benchmark-continue` | log, post a `## slopstop signals` PR comment with a `benchmark_overrides` entry (same format as Step 0's benchmark override record, with `"step": "pre_commit_test"`), continue to Step 3 with a prominent `⚠️ BENCHMARK OVERRIDE: N test(s) failing` note in the commit body and PR body |

`benchmark-continue` also governs the Step 0 pre-PR gate — it is the single config key that controls both places where test failures can block a PR.

## Red-findings fix loop (Step 6-claude) — removed in BILL-429

`on_red_findings` used to drive a second fix loop from *this* session: it re-invoked
`/code-review`, capped at 3 iterations, and applied findings directly to the working tree.
All three properties are now wrong:

- **The caller does not apply findings.** A fresh agent applies each one, serially
  (`pr-claude-review.md`). Caller-applies is precisely the contamination path BILL-429
  closes — the session that wrote the code deciding which criticisms of it are valid.
- **The cap is 5, and it lives in one place** — `pr-verification-classification.md` Step
  7e, shared by all three backends. A 3-iteration counter here contradicts it.
- **`/code-review` cannot be invoked by a skill.** It is `disable-model-invocation`; every
  call site that appeared to launch it was inert.

Autonomous routing of review findings is now the severity table in
`pr-verification-classification.md`, which reads no config key at all.

`on_red_findings` is **not read by any step**, and neither is `[pr_review] fix`. The
pre-flight check that warned when a project set both therefore has no condition left to
fire on, and is gone with them. The keys still exist; removing them, and making their
presence a config-load failure, is #433. Until then, setting either has no effect — a
safer end state than the loop they used to start.

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
