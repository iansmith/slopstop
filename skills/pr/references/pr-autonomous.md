# PR Autonomous Behavior — Full Reference

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

## Simplify confirmation (Step 1)

When the simplify agent modifies the working tree, the interactive path asks `continue / abort`. In autonomous mode, consult `[autonomous] on_simplify_changes`:

| Value | Action |
|---|---|
| `accept` (**default**) | log `"[autonomous] simplify changes accepted per on_simplify_changes=accept"` and proceed to Step 2 |
| `ask` | ask interactively — stalls a headless run; set explicitly only when a human is monitoring |
| `reject` | log the delta line count and stop: `"[autonomous] simplify changes rejected per on_simplify_changes=reject"` |

Record the simplify line delta (lines added + removed from the before/after diff) for the metrics emit below.

## Test failure (Step 2c)

When tests fail, the interactive path offers `fix / commit anyway / abort`. In autonomous mode, consult `[autonomous] on_test_failure`:

| Value | Action |
|---|---|
| `abort` (**default**) | log the failure summary and stop: `"[autonomous] tests failed — aborting per on_test_failure=abort"` |
| `ask` | ask interactively — stalls a headless run; set explicitly only when a human is monitoring |
| `commit-anyway` | log and continue to Step 3 with `Note: N test(s) failing at commit time` body line |
| `benchmark-continue` | log, write an override record to `pipeline.json` (same format as Step 0's benchmark override record, with `"step": "pre_commit_test"`), continue to Step 3 with a prominent `⚠️ BENCHMARK OVERRIDE: N test(s) failing` note in the commit body and PR body |

`benchmark-continue` also governs the Step 0 pre-PR gate — it is the single config key that controls both places where test failures can block a PR.

## Red-findings fix loop (Step 6-claude, `on_red_findings`)

After `/code-review` completes, the interactive path presents findings and stops. In autonomous mode, consult `[autonomous] on_red_findings` (Claude backend only — `$PR_BACKEND == "claude"`):

| Value | Action |
|---|---|
| `fix-and-retry` (**default**) | enter the fix-and-retry loop below |
| `ask` | present findings and stop (same as non-autonomous) — stalls a headless run; set explicitly only when a human is monitoring |
| `skip` | log finding counts, do NOT apply fixes, proceed to Step 7f |

Every verified-real finding gets fixed, not just 🔴 — a 🟡 "could fix" finding (including a small documentation-only one) still costs nothing to apply once `/code-review` has confirmed it's real, and the reviewer isn't earning its keep if half its output is ignored by policy. Only ⚪ (premise wrong, contradicts convention, pure stylistic nit) is never auto-applied.

`on_red_findings` is only consulted when `[pr_review] fix = false` (the default) — see **Pre-flight config validation** below for what happens when `fix = true` is also set.

**`fix-and-retry` loop** (max 3 iterations; terminates early when the 🔴+🟡 count reaches 0 or no iteration reduces it):

1. For each 🔴 and 🟡 finding: apply the fix directly to the working tree (instruct the agent to make the change, guided by the finding's file/line/description).
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
4. Push: `git push $PR_REMOTE $BRANCH`.
5. Re-run Step 6-claude (invoke `/code-review` again with the same effort). Increment iteration counter.
6. If the 🔴+🟡 count is 0 after the review: clean ✅, proceed to Step 7f.
7. (Iterations 2+ only) If the 🔴+🟡 count didn't decrease from the previous iteration: log `"[autonomous] fix-and-retry: finding count did not decrease after iteration N — stopping loop to avoid spin"` and proceed to Step 7f with the remaining findings. Iteration 1 always runs regardless of count — there is no "previous" to compare against.
8. If max iterations reached (a real, repeated problem — not a first-attempt hiccup): log remaining finding count and proceed to Step 7f.

### Pre-flight redundancy check

`[pr_review] fix = true` and `[autonomous] on_red_findings` govern the same job at two different moments and are never both live: `fix = true` makes Step 6-claude's own `--fix` loop self-contained (see `pr-claude-review.md`), and that path never reaches this section — `on_red_findings` only matters when `fix = false`. Since `on_red_findings` now defaults to `fix-and-retry`, most `fix = true` autonomous projects will never touch `on_red_findings` at all, and that's fine — nothing to flag. The only case worth a note is when a project *explicitly* sets `on_red_findings = "fix-and-retry"` while also having `fix = true`: that explicit setting is a harmless no-op (it's simply never consulted), but silent no-ops are confusing, so `pr/SKILL.md`'s Pre-flight warns once and continues rather than hard-stopping — this isn't a serious problem, just informational. See `pr/SKILL.md` Pre-flight for the actual check.

## Red-test tamper gate (Step 2d)

Mechanical, and **not** governed by `on_slop_findings`. When 🔴 (a red-test assertion changed after the RED commit, a test removed or skipped, or no RED commit at all), the interactive path asks for an override reason. In autonomous mode, consult `[autonomous] on_redtest_tamper`:

| Value | Action |
|---|---|
| `hard-stop` (**default**) | stop on any 🔴; no override allowed; log `"[autonomous] on_redtest_tamper=hard-stop — red-test tampering detected, refusing to proceed"` |
| `warn` | log the finding to the ticket and `pipeline.json`, continue. Use only while evaluating a new model tier — `:run` Gate 0 remains the external backstop. |

There is deliberately **no `skip`**. `on_slop_findings` defaults to `skip` itself (a judgment gate, not a mechanical one — `:run` Gate 0 remains the external backstop for fleet agents), so a shared knob here would silently disable this gate too, for exactly the agents it exists to police. This gate's default stays the strict value, not the permissive one: it polices ground-truth facts (was there a recorded RED commit, was an assertion changed), not a judgment call, so there is no scenario where skipping it by default is the safe choice.

## Slop detection (Step 2e)

When 🔴 slop findings are present, the interactive path asks for an override reason. In autonomous mode, consult `[autonomous] on_slop_findings`:

| Value | Action |
|---|---|
| `skip` (**default**) | skip slop detection entirely; log `"[autonomous] on_slop_findings=skip — slop detection bypassed"` |
| `ask` | ask interactively (same as non-autonomous) — stalls a headless run; set explicitly only when a human is monitoring |
| `hard-stop` | if any 🔴 findings present: hard-stop, no override allowed; log `"[autonomous] on_slop_findings=hard-stop — stopping on 🔴 slop findings, no override allowed"` |

> **Note:** `on_slop_findings` is only consulted when Step 2e actually runs. Passing `--no-adversary` or `--no-test` skips Step 2e entirely before this config is checked — those flags override `on_slop_findings`, including `hard-stop`. **Neither flag skips Step 2d**: the tamper gate is keyed to a recorded fact (does `task_plan.md` record a Phase 0 baseline?), never to an argument the policed agent supplies.

## Metrics emit (Step 8)

After the review step completes (and after the fix-and-retry loop if applicable), if `[autonomous] metrics_emit_path` is set, merge the following fields into `<metrics_emit_path>/<TICKET>/pipeline.json`. If the file does not exist (e.g. `:start` ran without `metrics_emit_path` set), create it with these fields plus `{"ticket": "$TICKET"}`:

All six fields are integers (bare numbers, not strings):

| Field | Meaning |
|---|---|
| `simplify_line_delta` | total lines changed by simplify, or `0` if skipped/rejected/no changes |
| `review_red_count` | final 🔴 count after any fix-and-retry loops, or `0` if clean |
| `review_yellow_count` | final 🟡 count, or `0` |
| `cc_violation_count` | number of 🔴 CC violations at PR time, or `0` |
| `cc_elevated_count` | number of 🟡 elevated functions at PR time, or `0` |
| `cc_max` | highest CC value seen across modified files, or `0` if lizard not installed |

```json
{
  "simplify_line_delta": 0,
  "review_red_count": 0,
  "review_yellow_count": 0,
  "cc_violation_count": 0,
  "cc_elevated_count": 0,
  "cc_max": 0
}
```
