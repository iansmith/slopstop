# PR CC Gate — Full Implementation

## BASE_SHA and CHANGED_CODE detection

```bash
BASE_SHA=$(git merge-base HEAD origin/$(git remote show origin | awk '/HEAD branch/{print $NF}') 2>/dev/null \
           || git merge-base HEAD origin/master 2>/dev/null \
           || git merge-base HEAD origin/main 2>/dev/null \
           || echo "HEAD~1")
# lizard-supported extensions (extend this list if your project uses others)
CHANGED_CODE=$(git diff --name-only "$BASE_SHA"..HEAD \
  | grep -E '\.(py|js|ts|jsx|tsx|java|go|rs|c|cpp|cc|h|hpp|cs|kt|swift|scala|php|rb)$')
```

If `CHANGED_CODE` is empty: skip this gate.

## Lizard availability — auto-install cascade

```bash
if   command -v lizard              &>/dev/null; then CC_CMD="lizard"
elif python3 -c "import lizard" 2>/dev/null;    then CC_CMD="python3 -m lizard"
else
  echo "  CC gate: lizard not installed — installing now..."
  pip install lizard --quiet 2>/dev/null \
    || pip3 install lizard --quiet 2>/dev/null \
    || python3 -m pip install lizard --quiet 2>/dev/null \
    || true
  if   command -v lizard           &>/dev/null; then CC_CMD="lizard"
  elif python3 -c "import lizard" 2>/dev/null; then CC_CMD="python3 -m lizard"
  else echo "  CC gate: lizard install failed — skipping. Fix: pip install lizard"; CC_CMD=""; fi
fi
```

If `CC_CMD` is empty: skip with the warning above and continue to Step 1.

## Run CC analysis

```bash
CC_JSON=$($CC_CMD --json $CHANGED_CODE 2>/dev/null)
```

lizard's JSON output has a top-level `function_list` array; each entry has `name`, `cyclomatic_complexity`, `start_line`, `filename`, and `nloc`. Read both thresholds from `.project-conf.toml`:

- `cc_warn_threshold` from `[autonomous] cc_warn_threshold` (default: **10**)
- `cc_reject_threshold` from `[autonomous] cc_reject_threshold` (default: **15**)

Parse `CC_JSON`. For each function in `function_list`:
- `cyclomatic_complexity > cc_reject_threshold` → **🔴 violation** (hard-gate)
- `cc_warn_threshold < cyclomatic_complexity ≤ cc_reject_threshold` → **🟡 elevated** (warning)

## NEW_FUNC_NAMES extraction

Identify which violations were introduced in this PR — look for the function name on definition-introduction lines in the diff:

```bash
NEW_FUNC_NAMES=$(git diff "$BASE_SHA"..HEAD \
  | grep '^+' \
  | grep -oP '(?:def |func |function |fn |public |private |protected |static )\K\w+(?=\s*[\(\{])')
```

A violation is tagged `[new in this PR]` if its `name` matches a token in `NEW_FUNC_NAMES`, else `[pre-existing]`.

## CC report format

```
CC gate: N 🔴 violation(s), M 🟡 elevated (threshold = T)

  🔴 Over threshold (CC > T):
    backup_scheduler.py:42  run_backup          CC=34  grade=E  [new in this PR]
    ...

  🟡 Elevated (W < CC ≤ T, where W = cc_warn_threshold):
    backup_scheduler.py:88  _schedule_next      CC=18  grade=C  [pre-existing]
    ...
```

## CC-gate bypass — benchmark override record

When `on_test_failure = "benchmark-continue"` causes the CC gate to be bypassed, merge this into `<metrics_emit_path>/<TICKET>/pipeline.json`:

```json
{
  "benchmark_overrides": [
    {
      "step": "pre_pr_cc_gate",
      "cc_reject_threshold": "<T>",
      "cc_violations": [
        {"file": "<path>", "function": "<name>", "cc": "<n>", "grade": "<R>", "introduced_in_pr": "<true|false>"}
      ],
      "cc_elevated_count": "<M>",
      "action": "benchmark-continue — proceeded despite CC violations for baseline comparison"
    }
  ]
}
```

If `benchmark_overrides` already exists in the file (from a prior invocation or from the test-failure gate in the same run), **append** to the array rather than replacing it.
