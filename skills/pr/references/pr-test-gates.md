# PR: Test Gates — Step 0 (pre-PR health) and Step 2 (pre-commit)

Both steps run the suite, and Step 0a said "same logic as Step 2a" — so the test-command
resolution lives here **once** and both steps use it.

## Identifying the test command

Both steps share rungs 1 and 2 — but **not** rung 3, and the difference is load-bearing:

1. a `**Test command:**` line in `task_plan.md`;
2. auto-detect from project files. The table is **not** restated here — it lives in
   one place:
   → Read `~/.claude/commands/slopstop-plan-refs/test-command-resolution.md`
3. **Step 2 only** — ask the user once, and cache the answer by writing the
   `**Test command:**` line into `task_plan.md`.

**Step 0 never asks.** If neither rung 1 nor rung 2 determines a command, Step 0 skips
itself with a warning and continues to Step 1: it is a health check, not a hard
requirement, and a prompt here would stall exactly the headless `--inline` and autonomous
runs that can't answer one. Do not "unify" the ladder — Step 0a's two rungs and Step 2a's
three are a deliberate asymmetry.

## Step 0b — run the full suite and evaluate

Execute the command with its **full output redirected to a file in the tracking dir**, and
capture the exit status on the line immediately following — the same C5 capping rule the
shared reference states:

```bash
( eval "$TEST_CMD" ) > "$TRACKING_DIR/$TICKET/step_0b.output" 2>&1
STATUS=$?
```

Classification **reads the output back from that file** — never from a truncated stream —
so every failing test stays visible to the classifier; nothing in this path pipes the
output through a truncating filter:

- **Pass (`$STATUS` = 0):** print `"Pre-PR gate: all tests passing. Proceeding."`, continue to Step 1.
- **Fail:** classify every failing test found in the file, in full, as **Regression** (it
  passed at Phase 0 time) or **Expected failure** (a Phase 0 red test for THIS ticket, not
  yet green). The distinction decides the outcome:
  - **Any regressions** → hard stop in autonomous mode (the default), or ask interactively.
    With `benchmark-continue`: proceed, write an override record, and put a prominent
    warning in the PR body.
  - **Only expected failures** → warn, and let the user (or autonomous config) decide.

Only the decisive lines (the failures actually driving the verdict) are quoted into
context; the file is the durable, complete record.

Structured summary format and the benchmark override record JSON:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-test-failure-gate.md`

Write a `step_0b` entry to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) recording the pass/fail result,
with `detail` set to the output filename.

## Step 0c — cyclomatic complexity gate

`CHANGED_CODE` = source files with lizard-supported extensions modified since the branch
point. **Empty → skip the gate.** `lizard` unavailable → skip.

Thresholds from `.project-conf.toml`: `cc_warn_threshold` (default **5**, 🟡) and
`cc_reject_threshold` (default **10**, 🔴). Both are **inclusive lower bounds** — CC 5–9
warns, CC 10 or above rejects.

- **🔴 violations** → hard stop interactively; autonomous benchmark-continue writes a
  `pipeline.json` record and a `⚠️ BENCHMARK OVERRIDE (CC)` note in the PR body.
- **Only 🟡 elevated** → proceed, and append a **Complexity notes** section to the PR body.
- **Measurement failed** (lizard exited non-zero) → 🔴 gate error, reported with lizard's
  stderr. Not a skip: a gate that could not measure must not read as a clean pass.

If `cc_exempt_pre_existing = true` (default **false**), a 🔴 violation this branch did
not touch — by line-range overlap with the diff, not by function name — is exempted from
the hard-gate but still printed under its own heading. Off by default: every project
behaves as above until it opts in.

Full shell implementation (`BASE_SHA`, `CHANGED_CODE` detection, lizard auto-install
cascade, the `--csv` column contract and quote-aware parse, the line-range scope test,
report format, remedies, override JSON):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-cc-gate.md`

Write a `step_0c` entry to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) recording the result. `step_0c` is
never tier-gateable.

## Step 2 — run the tests before committing

Skipped by `--no-test`. Resolve the command as above, run it with the same redirect-then-
capture pattern Step 0b uses — full output to `$TRACKING_DIR/$TICKET/step_2.output`,
`STATUS=$?` captured immediately after — and read the file back for classification:

- **Pass (`$STATUS` = 0):** print `"Tests passed. Continuing to commit."`, proceed to Step 2d.
- **Fail:** print the failures (read back from the file, in full) and offer `fix` /
  `commit anyway` / `abort`. `fix` or `abort` → stop. `commit anyway` → proceed to Step 2d,
  and add a `Note: <N> test(s) failing at commit time` line to the PR body.

Write a `step_2` entry to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) recording the result, with
`detail` set to the output filename.

**Step 2d runs on every path that reaches Step 3** — a passing suite, `commit anyway`, and
`--no-test` alike. It is a `git log` plus `git diff`, with no dependency on the suite, so
skipping the tests never skips it. (`fix` and `abort` stop the run outright, so nothing
downstream runs at all — that is a halt, not a bypass.) See the spine.
