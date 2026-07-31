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
    # Diff body -> tracking dir IN FULL, read back below to classify every hunk (C5, C1).
    # Stderr on a SEPARATE stream: a naive `> file 2>&1` would let a failing `git diff`
    # write its error text into the file this gate parses, reading as zero hunks — a
    # THIRD path to this gate's known "empty diff reads as clean" lethal mode, alongside
    # the -z "$RED" / -z "$FROZEN" guards above.
    git diff -w -M "$RED"..HEAD -- $FROZEN \
      > "$TRACKING_DIR/$TICKET/step_2d.diff" 2> "$TRACKING_DIR/$TICKET/step_2d.diff.stderr"
    STATUS=$?
    if [ "$STATUS" -ne 0 ]; then
      echo "🔴 git diff exited $STATUS — hard stop, never a clean pass"
      # hard-stop: fall into the 🔴 override flow below, do not read step_2d.diff.
    fi
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

- **Added test / added assertion** — fine, with **one exception**: an added test that
  **shadows a frozen one** — same qualified name (`def test_x` / `func TestX`) in the same
  file, or a later definition that rebinds an earlier one — is 🔴. In pytest and Go a
  later same-name definition silently replaces the earlier, so "adding" a passing
  `test_decode_zero` next to the frozen failing one makes the red assertion never run. A
  pure addition is welcome; an addition that *neutralizes* a frozen test is tampering
  wearing an addition's clothes. (This is why the diff alone is not sufficient — see
  *Known evasions* below.)
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
the tamper check (`run-verification.md`). This is a cheap early self-check, not the authority.

**Known evasions this diff cannot catch — the judgment layer must.** The mechanical gate
trusts three things the agent controls: *which files entered the frozen commit*, *that an
addition is benign*, and *that a `Phase 0` label implies the tests were red. It is defeated
by, and the handoff requirements adversary (`run-verification.md`) must specifically hunt:

- a **shadow test** — a same-name added test that neutralizes a frozen one (partly caught
  above, but AST-level renames evade the textual check);
- the **expected value living in a non-frozen file** — the frozen test reads it from a
  helper, `conftest.py`, a fixture, or a golden file that was *not* staged in the Phase 0
  commit, so editing that file changes the assertion's result with no hunk in the frozen
  set;
- a **green test frozen as red** — nothing here re-runs the tests at the RED commit to
  confirm they failed; the gate asks "did this change?", never "was it ever red?". The
  fleet path closed this at handoff verification (BILL-287,
  `run-verification.md`'s "Redness confirmation" section) — checked out `$RED` in a
  scratch worktree, re-ran `$FROZEN`, classified never-red / unverifiable / genuinely-red.
  **This solo path (`:pr` Step 2d) does not have the equivalent self-check** — the tamper
  check above and this section still only ask whether something changed, never whether it
  was ever red. Filed as BILL-346, mirroring the tamper check's own self-check +
  external-check pairing (`pr-slop-detection.md` here, `run-verification.md` from
  outside).

Closing the remaining two mechanically needs checks a `git diff` cannot do (name-collision
detection, the test's transitive dependency closure). Until those exist, they are the
judgment adversary's job, and they are tracked as follow-ups.

**Autonomous path for this gate:** `[autonomous] on_redtest_tamper` — default `hard-stop`,
and there is deliberately **no `skip`** value. It is **not** `on_slop_findings`, which
governs Step 2e only. See `pr-autonomous.md`.

Write a `step_2d` entry to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) recording the result, with
`detail` set to the diff-body filename (`step_2d.diff`). **This step never reads
`gates.json` for a skip decision** — no flag skips this gate (above), and no `gates.json`
hit ever will either; that read path is permanently excluded by the schema (C4). Writing
this gate's diff body to disk is a context-volume change only: **no `gates.json` entry may
skip this gate**, before or after this ticket.

## Inline slop detection (when `--inline` was passed)

Skip the Agent spawn. Use `$INLINE_DIFF` captured during inline simplify (Step 1) if available; if Step 1 was skipped (`--no-simplify`), run `git diff "$(git merge-base "$ORIGIN_REMOTE/$BASE" HEAD)"` now — the same branch scope Step 1 uses, one ref so it spans committed and uncommitted work alike. **Never scope this to the working tree alone.** On the clean tree every fleet agent presents, such a diff is empty, so the scan would report a clean pass having examined nothing — worse than an honest skip, because it manufactures a green gate. Also run:

```bash
git ls-files --others --exclude-standard -- 'tests/**' '**/test_*.py' '*_test.py' | head -20
```

Read each untracked test file in full. Apply the slop pattern catalog below to everything surfaced. Report findings and apply the same 🔴/🟡 gate behavior (interactive override flow, override record, autonomous path) exactly as the agent path would.

## Slop-detection agent prompt

Spawn an agent with these instructions:

> "Gather every test file in scope using two commands:
> 1. `git diff "$(git merge-base "$ORIGIN_REMOTE/$BASE" HEAD)"` — every change this branch makes, committed or not. One ref, not a range: a two-commit range would miss uncommitted work, and a working-tree diff would miss committed work — which is exactly where tampering lives
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

## Tier gating applies to Step 2e only

**Step 2e is tier-gated:** on the `trivial` tier, this step is skipped when a matching
sha-valid `gates.json` `step_2e` entry already exists (schema:
`~/.claude/commands/slopstop-pr-refs/pr-size-classifier.md`); otherwise it runs. On
`standard` and `large`, it always runs. The mechanical gates before and after this
section are never tier-gated — no tier, and no flag, skips either of them.

## Autonomous path — Step 2e (the slop-pattern review) ONLY

**This section does not apply to Step 2d.** `on_slop_findings` governs the judgment-based
slop review and nothing else. The mechanical red-test tamper gate has its own knob —
`[autonomous] on_redtest_tamper` (default `hard-stop`, and deliberately **no `skip`**) — for
the reason given in § Step 2d: `on_slop_findings` defaults to `skip` (a judgment gate, not a
mechanical one), so a shared knob would silently disable the tamper gate for exactly the
agents it polices. See `pr-autonomous.md`.

For **Step 2e**, when running in autonomous mode (`[autonomous] enabled = true`), consult
`[autonomous] on_slop_findings`:

| Value | Action |
|---|---|
| `skip` (**default**) | skip **the Step 2e slop review** entirely; log `"[autonomous] on_slop_findings=skip — slop detection bypassed"`. Step 2d still runs. |
| `ask` | ask interactively (same as non-autonomous) — stalls a headless run; set explicitly only when a human is monitoring |
| `hard-stop` | if any 🔴 findings present: hard-stop, no override allowed; log `"[autonomous] on_slop_findings=hard-stop — stopping on 🔴 slop findings, no override allowed"` |

Write a `step_2e` entry to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) recording the result (`"pass"`
when no 🔴 findings block, `"fail"` on a hard-stop).

## Step 2f — Vacuity gate (mechanical; runs even on a clean tree, unskippable)

**No flag skips this gate.** Not `--no-test`, not `--no-adversary`, not
`[autonomous] on_slop_findings` — the identical claim Step 2d makes above, for the identical
reason: `on_slop_findings` governs Step 2e's judgment review and defaults to `skip` in any
fleet-capable config, so sharing it here would silently disable this gate for exactly the
agents it exists to police.

### Why this exists, and how it differs from Step 2d

Step 2d asks *"did the frozen Phase 0 tests change since `$RED`?"* — a test written or edited
**after** Phase 0 is invisible to it, because it was never frozen. `:plan` Step 0f's adversary
attacks Phase 0 tests for the same vacuity this gate checks, but only at Phase 0 time — a
review-round or simplify-round edit, or anything an implementation agent adds outside the
Phase 0 commit, passes through neither. Observed live, twice, in the same ticket (BILL-340):
one vacuous assertion was written and fixed at Phase 0 (caught — a test that passes at Phase 0
is by definition not red); a second was introduced during the simplify round, after both
Phase-0 gates had already fired, and was caught only by hand — mutating the doc and noticing
the test stayed green. That manual step is what this gate mechanises.

**Complementary to `run-verification.md`'s Redness confirmation (BILL-287), not a duplicate:**

| | Step 2d / BILL-287 | this gate |
|---|---|---|
| question | was the Phase 0 baseline ever red? | does each changed test pin anything? |
| tests in scope | the frozen set from the Phase 0 commit | every test changed since the merge-base |
| reverts to | `$RED` | `git merge-base "$ORIGIN_REMOTE/$BASE" HEAD` |
| covers post-Phase-0 edits | no — not frozen | yes, that is the point |

### Scope: which tests changed

```bash
BASE=$(git merge-base "$ORIGIN_REMOTE/$BASE_BRANCH" HEAD)
CHANGED_TEST_FILES=$(git diff --name-only "$BASE"..HEAD | grep -E 'test_.*\.py$|_test\.go$')
```

For each changed test file, identify which **test functions** changed — by line-range
overlap with the diff, the same technique `pr-cc-gate.md`'s pre-existing-code exemption uses
and for the identical reason: a signature grep (`^\+\s*def test_`) only catches a **brand-new**
test. A body-only edit to an existing test — the assertion line changes, the `def` line does
not — is invisible to a signature grep. That is exactly BILL-340's second vacuous assertion:
the check tightened, `test_gate_requires_a_quote_aware_parser`'s `def` line never moved.

For Python, parse the file with `ast` and compare each `FunctionDef` (name starting with
`test`) against the diff's changed-line ranges:

```python
import ast, re, subprocess

def changed_ranges(base_sha, path):
    diff = subprocess.run(["git", "diff", "--unified=0", f"{base_sha}..HEAD", "--", path],
                           capture_output=True, text=True).stdout
    ranges = []
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        ranges.append((start, start if count == 0 else start + count - 1))
    return ranges

def changed_test_functions(source, ranges):
    tree = ast.parse(source)
    return [n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
            and any(a <= n.end_lineno and n.lineno <= b for a, b in ranges)]
```

For Go, no equivalent stdlib AST is assumed available in this context — identify changed
`func TestX` names from the diff hunks by the same principle (a function is in scope if the
diff touches any line inside it, not merely its signature line), not a bare `^\+func Test`
grep for the same reason given above.

### Run each changed test against BASE, not the branch tip

Create a scratch worktree at `$BASE` (same mechanism `run-verification.md`'s Redness
confirmation uses, at a different SHA) and copy in the **current content** of the changed test
files — new tests on old code:

```bash
WORKTREE=$(mktemp -d)
git worktree add -q "$WORKTREE" "$BASE"
for f in $CHANGED_TEST_FILES; do
  mkdir -p "$WORKTREE/$(dirname "$f")"
  git show HEAD:"$f" > "$WORKTREE/$f"
done
# Also copy any conftest.py sharing a directory with a changed test file — see
# the known limitation immediately below before trusting a clean result blindly.
for d in $(dirname $CHANGED_TEST_FILES | sort -u); do
  git show HEAD:"$d/conftest.py" > "$WORKTREE/$d/conftest.py" 2>/dev/null || true
done
```

**Known limitation.** This closes the common case — a fixture in the *same directory* as the
changed test — but not a shared fixture, helper module, or golden file the branch also
modified that a changed test imports **by name** from elsewhere (`from helpers import X`,
a `conftest.py` several directories up, a golden file). That test's dependency changed too,
silently, and its verdict here can be wrong in either direction. This is the identical
"expected value in a non-frozen file" evasion Step 2d's own catalogue names for a sibling
gate (§ above) — closing it in general needs the test's transitive dependency closure, which
this gate does not compute. BILL-286 tracks that closure for Step 2d; the same mechanism,
once built, applies here too. Not solved by this gate.

Run each changed test function **individually, by node-id** (`pytest <file>::<test_name>`),
not the whole file — a file can hold both a changed test and unrelated untouched ones, and
only the changed one is this gate's business.

**Output destination — for the record, not for classification.** Each node-id's
stdout/stderr is redirected to a file in the tracking dir (one file per node-id, or one
appended log keyed by node-id), `STATUS=$?` captured on the line immediately following:

```bash
pytest "$NODE_ID" > "$TRACKING_DIR/$TICKET/step_2f/$NODE_ID_SLUG.output" 2>&1
STATUS=$?
```

A context-volume change only, kept for the record — the exit status, never the file, is
the classification input; unlike Step 2d, this gate never reads its output file back to
decide anything.

### Classify — three outcomes, per test

Classify by `STATUS`, never by scanning the file — the distinction below is load-bearing
and empirically verified, and none of it is present in redirected text:

- **`STATUS` = 0** → the test passes cleanly against the base implementation → **🔴**, unless
  the test carries a `SLOPSTOP PRAGMA coverage-backfill` comment (see below).
- **`STATUS` is a genuine assertion failure** → confirmed: the test pins something this
  branch actually did. No finding.
- **Cannot even be collected** → **inconclusive**, reported explicitly, never silently a pass.
  Selecting a *specific node-id* — this gate's invocation, unlike Step 2d's whole-suite scope —
  reports both a collection/import error **and** a node-id that does not exist at `$BASE` at
  all (e.g. a test whose supporting fixtures were also added by this branch) as pytest's
  usage-error exit code, **4**, not the exit **2** a whole-file run would give the same broken
  import (verified empirically — this is a real, invocation-dependent difference, not an
  assumption carried over from `run-verification.md`'s whole-file exit-2 premise). Neither
  case is a genuine assertion failure, so neither counts as red.

**Inconclusive does not block, unlike BILL-287's redness confirmation treating the same
shape as a hard FAIL.** Deliberate, not an inconsistency: BILL-287 reverts to `$RED` with a
*full checkout* of the whole tree, so a collection error there means the frozen test itself
is broken — a real problem with a trustworthy signal. This gate's BASE worktree is a
*partial* copy (changed test files, plus same-directory `conftest.py` as of the fix above),
so a collection error here is at least as likely to be an artifact of that narrower copy — a
dependency the copy missed — as it is to be a genuine problem with the test. Blocking on a
signal this gate's own construction makes noisy would make the gate self-defeating. Still
reported, always, so a real problem hiding behind "just the copy" isn't lost.

### Backfill: declared, not silently exempted

A test added for behavior that already existed correctly at `BASE` legitimately passes there.
Declare it with the exact pragma the CC gate's NLOC check already established the convention
for:

```python
# SLOPSTOP PRAGMA coverage-backfill: <one-line reason>
def test_existing_behavior_x():
    ...
```

A declared backfill is never a 🔴, regardless of its result at `BASE`. It is still **counted**
and **listed** in the Step 8 summary — the count is the control: an agent cannot quietly
relabel a vacuous test as backfill without the number showing. No config key silences this
declaration or the gate itself; behavior 6 of the ticket that added it is explicit that no
flag disables it.

### Report format

```
Vacuity gate: N 🔴 vacuous, M inconclusive, K backfill declared

  🔴 Passes cleanly against BASE — pins nothing this branch did:
    test_thing.py::test_new_behavior
    ...

  ⚪ Inconclusive — could not be collected at BASE:
    test_thing.py::test_uses_new_helper  (ModuleNotFoundError: no module named 'new_helper')
    ...

  ⚪ Backfill declared (SLOPSTOP PRAGMA coverage-backfill):
    test_thing.py::test_existing_behavior_x  — "covering pre-existing behavior, not part of this branch"
    ...
```

Silent — no output at all — only when `N == 0` and there is nothing to report; `M` and `K`
still appear whenever nonzero, matching the CC gate's own "never silently drop a nonzero
count" convention.

Write a `step_2f` entry to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) recording the result (`"fail"`
when `N > 0`, `"pass"` otherwise), with `detail` set to the per-node-id output directory.
**This step never reads `gates.json` for a skip decision** — the same C4 exemption Step 2d
carries above. Writing this gate's per-node-id output to disk is a context-volume change
only: **no `gates.json` entry may skip this gate**, before or after this ticket.
