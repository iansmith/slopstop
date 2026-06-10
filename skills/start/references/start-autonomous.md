# Autonomous behavior detail

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`.

## Branch-type selection (Step 4b)

If `[autonomous] branch_type = "<type>"` is set, skip the interactive prompt and use the configured value as `$TYPE`. The label/title heuristic is still computed (logged for audit) but not shown. `branch_type` must be a Conventional-Commits prefix (`fix`, `feat`, `chore`, `docs`, `refactor`, `perf`, `test`, `ci`, `build`, `deploy`, `revert`) or a custom token passing `git check-ref-format`. If format check fails, fall back to interactive prompt and report: `"[autonomous] branch_type='<value>' is an invalid branch-name component — asking interactively."`.

## Base-ref selection (Step 4c)

When cwd is on a non-default branch, skip the warn-and-ask prompt. Use `$ORIGIN_REMOTE/$DEFAULT_BRANCH` and log: `"[autonomous] cwd is on '$CURRENT_BRANCH' — branching off $ORIGIN_REMOTE/$DEFAULT_BRANCH (clean default)."`.

## Metrics emit (Step 6)

If `[autonomous] metrics_emit_path` is set, write an initial `pipeline.json` stub to `<metrics_emit_path>/<ARGUMENTS>/pipeline.json` when seeding the tracking dir. The stub records the ticket, start timestamp, and branch — giving the `slopbench collect` subcommand something to locate before `:pr` and `:merge` fill in signal counts.

```json
{
  "ticket": "$ARGUMENTS",
  "started_at": "<ISO timestamp>",
  "branch": "$NEW_BRANCH",
  "phase0_tests_red": null,
  "phase0_tests_pass_unexpected": null,
  "simplify_line_delta": null,
  "review_red_count": null,
  "review_yellow_count": null,
  "merge_strategy": null,
  "completed_at": null
}
```

## End-of-run output (Step 6 summary)

Omit any trailing offer or question about what to run next (e.g., "Want me to run `/slopstop-plan`?", "Shall I proceed?"). Output only the factual completion summary. The orchestrator drives the sequence.
