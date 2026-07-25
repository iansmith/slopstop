# PR: Test Gates — Step 0 (pre-PR health) and Step 2 (pre-commit)

Both steps run the suite, and Step 0a said "same logic as Step 2a" — so the test-command
resolution lives here **once** and both steps use it.

## Identifying the test command

Both steps share rungs 1 and 2 — but **not** rung 3, and the difference is load-bearing:

1. a `**Test command:**` line in `task_plan.md`;
2. auto-detect from project files. The table is **not** restated here — it lives in
   one place, including the `pnpm-lock.yaml` vs `yarn.lock` discriminator:
   → Read `~/.claude/commands/slopstop-pr-refs/pr-test-detection.md`
3. **Step 2 only** — ask the user once, and cache the answer by writing the
   `**Test command:**` line into `task_plan.md`.

**Step 0 never asks.** If neither rung 1 nor rung 2 determines a command, Step 0 skips
itself with a warning and continues to Step 1: it is a health check, not a hard
requirement, and a prompt here would stall exactly the headless `--inline` and autonomous
runs that can't answer one. Do not "unify" the ladder — Step 0a's two rungs and Step 2a's
three are a deliberate asymmetry.

## Step 0b — run the full suite and evaluate

Execute the command; capture output and exit code.

- **Pass (exit 0):** print `"Pre-PR gate: all tests passing. Proceeding."`, continue to Step 1.
- **Fail:** classify every failing test as **Regression** (it passed at Phase 0 time) or
  **Expected failure** (a Phase 0 red test for THIS ticket, not yet green). The distinction
  decides the outcome:
  - **Any regressions** → hard stop in autonomous mode (the default), or ask interactively.
    With `benchmark-continue`: proceed, write an override record, and put a prominent
    warning in the PR body.
  - **Only expected failures** → warn, and let the user (or autonomous config) decide.

Structured summary format and the benchmark override record JSON:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-test-failure-gate.md`

## Step 0c — cyclomatic complexity gate

`CHANGED_CODE` = source files with lizard-supported extensions modified since the branch
point. **Empty → skip the gate.** `lizard` unavailable → skip.

Thresholds from `.project-conf.toml`: `cc_warn_threshold` (default **10**, 🟡) and
`cc_reject_threshold` (default **15**, 🔴).

- **🔴 violations** → hard stop interactively; autonomous benchmark-continue writes a
  `pipeline.json` record and a `⚠️ BENCHMARK OVERRIDE (CC)` note in the PR body.
- **Only 🟡 elevated** → proceed, and append a **Complexity notes** section to the PR body.

Full shell implementation (`BASE_SHA`, `CHANGED_CODE` detection, lizard auto-install
cascade, `CC_JSON` parsing and fields, `NEW_FUNC_NAMES`, report format, override JSON):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-cc-gate.md`

## Step 2 — run the tests before committing

Skipped by `--no-test`. Resolve the command as above, run it, then:

- **Pass (exit 0):** print `"Tests passed. Continuing to commit."`, proceed to Step 2d.
- **Fail:** print the failures and offer `fix` / `commit anyway` / `abort`. `fix` or
  `abort` → stop. `commit anyway` → proceed to Step 2d, and add a
  `Note: <N> test(s) failing at commit time` line to the PR body.

**Step 2d runs on every path that reaches Step 3** — a passing suite, `commit anyway`, and
`--no-test` alike. It is a `git log` plus `git diff`, with no dependency on the suite, so
skipping the tests never skips it. (`fix` and `abort` stop the run outright, so nothing
downstream runs at all — that is a halt, not a bypass.) See the spine.
