# PR Slop Detection Gate — Full Reference

## Step 2d — Red-test tamper diff (mechanical; runs first, and runs even on a clean tree)

The slop catalog below has always named *expectation inversion* and *test deletion* 🔴. The
gate still missed them, because it only ever looked at `git diff HEAD` and was skipped
outright when `$DIRTY` was empty. Tampering is **committed** work presenting a clean tree,
so the scan must span the commit range, not the working tree.

```bash
# Where this branch left the base (same formula the CC gate uses).
BASE_SHA=$(git merge-base HEAD "$ORIGIN_REMOTE/$DEFAULT_BRANCH" 2>/dev/null || git merge-base HEAD "$BASE")

# The EARLIEST Phase 0 red-test commit (`:plan` Step 0e) is the frozen baseline.
# git log is reverse-chronological, so the earliest match is the LAST line — never
# `grep -m1`, which takes the newest and would let a second "Phase 0" commit move the
# baseline past an earlier tamper.
RED=$(git log --format='%H %s' "$BASE_SHA"..HEAD | grep 'Phase 0: red tests' | tail -1 | cut -d' ' -f1)
```

**If `$RED` is empty → 🔴 immediately. Stop; do not run the diff below.** An empty `$RED`
would make `git diff $RED..HEAD` expand to `git diff ..HEAD` — which git reads as
`HEAD..HEAD`, an empty diff that falls through looking clean. Guard it explicitly:

```bash
if [ -z "$RED" ]; then
  echo "🔴 no Phase 0 red-test commit — tests were never shown failing"
  # hard-stop: fall into the 🔴 override flow below. Do NOT continue to the diff.
else
  # The RED commit IS the manifest of frozen files — Step 0e stages the red tests
  # explicitly by path, so ask git which files it froze rather than guessing at globs.
  FROZEN=$(git show --name-only --format= "$RED")

  # GUARD: an empty $FROZEN would make the pathspec vanish — `git diff A..B --` diffs the
  # ENTIRE repo, so every source change would read as a touched frozen file and the gate
  # would mass-false-positive into a hard-stop. An empty RED commit is itself wrong.
  if [ -z "$FROZEN" ]; then
    echo "🔴 Phase 0 commit $RED froze no files — the baseline is empty"
  else
    git diff -w -M "$RED"..HEAD -- $FROZEN
  fi
fi
```

`-w -M` (whitespace-blind, rename-detecting) so a `gofmt`/`black` run or a file rename
yields no hunks. Under a hard-stop policy a false positive costs a PR, so formatting churn
must not read as tampering — and Step 0e formats the baseline first, making a later format
run a true no-op.

Deriving the file set from the baseline is exact by construction and language-agnostic. Do
**not** substitute a glob like `'*_test.go' '*_test.py' 'tests/'`: it silently covers
nothing in a repo whose tests don't match (a vacuous pass is worse than no gate), it
over-scopes `testdata/` fixtures, and it completely misses Rust/Go **inline unit tests that
live inside the source file** (`#[cfg(test)] mod tests` in `src/foo.rs`) — a file the agent
edits legitimately, so a tamper hidden there would be invisible.

Classify every hunk in that diff:

- **Added test / added assertion** — fine. Added coverage is always welcome.
- **Removed, skipped, or commented-out test** — 🔴.
- **A changed assertion — an expected value edited in place** — 🔴. This is the one that
  looks innocent: a line that *already asserted something* now asserts something
  *different*. `assertEqual(x, 0x2C)` → `assertEqual(x, 0x1F)`; exact equality → a range,
  a not-nil, a no-error. The commit message will be confident and may cite a real
  standard. **That is not evidence.** A vetted expected value, changed by the model whose
  code had to satisfy it, is tampering by construction regardless of how it is narrated.

**A missing Phase 0 commit is itself 🔴** — not "nothing to check". Tests written in the
same commit as the code were never shown failing, so they are free to assert whatever the
code already does: an unfalsifiable green suite. Treating a missing baseline as a pass
makes *skipping the baseline* the cheapest way to evade this entire gate.

If the ticket's expected value is genuinely wrong, that is a **ticket defect**, not a
finding to fix in the test: halt via the `TICKET UNDERSPECIFIED` protocol (TD-4 in
`plan-ticket-driven.md` — exact comment shape and final line; the orchestrator parses
both). Do not edit the test yourself.

### Why this exists

SOP-111 (sophie, μ-law decoding) sailed through this gate while rewriting a red test's
expected value to match its own broken decoder. The policy was already right; it was
simply never enforced — the scan was scoped to uncommitted changes while the tamper lived
in a commit, and the step was skipped on the clean tree that a tampering agent presents.

Note this gate runs in the agent's **own** session. An agent that has already rationalized
rewriting an assertion will rationalize its own review of it — which is why Step 2d is a
mechanical diff rather than a judgment call, and why `:run` re-checks it from outside at
Gate 0 (`run-verification.md`). This is a cheap early self-check, not the authority.

**Autonomous path for this gate:** `[autonomous] on_redtest_tamper` — default `hard-stop`,
and there is deliberately **no `skip`** value. It is **not** `on_slop_findings`, which
governs Step 2e only. See `pr-autonomous.md`.

## Inline slop detection (when `--inline` was passed)

Skip the Agent spawn. Use `$INLINE_DIFF` captured during inline simplify (Step 1) if available; if Step 1 was skipped (`--no-simplify`), run `git diff HEAD` now. Also run:

```bash
git ls-files --others --exclude-standard -- 'tests/**' '**/test_*.py' '*_test.py' | head -20
```

Read each untracked test file in full. Apply the slop pattern catalog below to everything surfaced. Report findings and apply the same 🔴/🟡 gate behavior (interactive override flow, override record, autonomous path) exactly as the agent path would.

## Slop-detection agent prompt

Spawn an agent with these instructions:

> "Gather every test file in scope using two commands:
> 1. `git diff HEAD` — staged and unstaged changes to tracked files
> 2. `git ls-files --others --exclude-standard -- 'tests/**' '**/test_*.py' '*_test.py' | head -20` — untracked new test files (capped at 20; run `git add -A` first if more need scanning); read each one in full
>
> For each test file surfaced, check whether any of the slop patterns below are present. For each finding, report: pattern type (🔴 or 🟡), file:line, what the code does, and why it's a slop pattern."

## Slop pattern catalog

### 🔴 Hard-stop patterns (require explicit override to proceed)

| Pattern | Description |
|---|---|
| **Test rewriting to pass** | Modifying an existing test's assertions or setup to make it pass rather than fixing the underlying code |
| **Expectation inversion** | Changing `assert X == expected` to `assert X == actual`, or relaxing an assertion threshold so the current output becomes the accepted value |
| **Test deletion or skip** | Removing a test or marking it `@skip` / `@pytest.mark.skip` that was previously failing |

### 🟡 Warning patterns (surface and warn; user can proceed without override)

| Pattern | Description |
|---|---|
| **Implementation testing instead of behavior testing** | New tests assert on internal state (private fields, intermediate variables, call counts) rather than observable outputs |
| **Tautological tests** | `assert fn(x) == fn(x)` or expected value derived from the same code under test |
| **Scope creep tests** | New tests added that test behavior unrelated to the ticket's stated scope |
| **Fake error handling** | `except Exception: pass`, broad catch-and-swallow, or error paths that return silently |
| **Hardcoded fixture cheating** | Test setup hardcodes the exact value the production code produces, making the test trivially pass |

## Interactive override flow (when 🔴 findings present)

```
STOP — slop-detection found 🔴 findings:

  🔴 test_foo.py:42  [TEST REWRITING]
     assert expected_result == 99  → was: assert expected_result == compute(x)
     Reason: assertion was relaxed to match implementation output rather than expected behavior.

Proceed requires an explicit override reason. This will be recorded in pipeline.json.
Enter override reason (or 'abort' to stop): _
```

Record to `<metrics_emit_path>/<TICKET>/pipeline.json` using the `benchmark_overrides`
append-to-array pattern (create file if absent).

**The two gates must write distinguishable records.** Step 2e (this section) uses
`"step": "pre_pr_slop_gate"`. The Step 2d tamper gate uses
`"step": "pre_pr_redtest_tamper_gate"` and `"tamper_findings"` in place of
`"slop_findings"`. The record of *who unfroze the tests* is the entire point of the
audit trail — a harness that cannot tell a tamper override from a slop override has
no audit trail.

```json
{
  "benchmark_overrides": [
    {
      "step": "pre_pr_slop_gate",
      "slop_findings": [
        {"severity": "🔴", "pattern": "test_rewriting", "file": "test_foo.py", "line": 42, "detail": "..."}
      ],
      "action": "override — <user's reason>"
    }
  ]
}
```

If `benchmark_overrides` already exists in the file, **append** to the array rather than replacing it.

## 🟡 Warnings presentation (non-blocking)

```
⚠️  Slop-detection found 🟡 warnings (not blocking):

  🟡 test_bar.py:18  [SCOPE CREEP]
     New test added for feature Y, unrelated to BILL-88's stated scope.

Proceeding to commit. Address these in a follow-up if needed.
```

## Clean pass

```
Slop detection: clean ✅ — no slop patterns found.
```

## Autonomous path — Step 2e (the slop-pattern review) ONLY

**This section does not apply to Step 2d.** `on_slop_findings` governs the judgment-based
slop review and nothing else. The mechanical red-test tamper gate has its own knob —
`[autonomous] on_redtest_tamper` (default `hard-stop`, and deliberately **no `skip`**) — for
the reason given in § Step 2d: a fleet-capable config is effectively pinned to
`on_slop_findings = "skip"`, so a shared knob would silently disable the tamper gate for
exactly the agents it polices. See `pr-autonomous.md`.

For **Step 2e**, when running in autonomous mode (`[autonomous] enabled = true`), consult
`[autonomous] on_slop_findings`:

| Value | Action |
|---|---|
| `ask` (default) | ask interactively (same as non-autonomous) |
| `skip` | skip **the Step 2e slop review** entirely; log `"[autonomous] on_slop_findings=skip — slop detection bypassed"`. Step 2d still runs. |
| `hard-stop` | if any 🔴 findings present: hard-stop, no override allowed; log `"[autonomous] on_slop_findings=hard-stop — stopping on 🔴 slop findings, no override allowed"` |
