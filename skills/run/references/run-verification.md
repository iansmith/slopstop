# Run: Handoff Verification (Step 6 detail)

A clean `:pr` review is necessary, never sufficient (`design/slopstop-process.md`
§7d): the agent's own pipeline hunts bugs and quality; the handoff hunts
**conformance** and **acceptability**, from the outside, at the medium tier.

## Tamper check — frozen red tests (mechanical, before the subagents)

The orchestrator runs this **itself**, before spawning anything. A FAIL ends verification
there — no subagent is bought. A green suite is not evidence when the agent had write
access to the tests.

The agent's Phase 0 commit (`[$TICKET] Phase 0: red tests …`, `:plan` Step 0e) pins the
vetted tests in RED state. Everything after it is the agent's own work. Resolve the
baseline against the **fork SHA already recorded in `fleet-state.md`** at launch:

```bash
# The EARLIEST Phase 0 red-test commit is the frozen baseline. git log is
# reverse-chronological, so the earliest match is the LAST line. Never `grep -m1`: that
# takes the NEWEST match, letting an agent slide the baseline past its own tamper by
# titling a later commit "Phase 0: red tests".
RED=$(git log --format='%H %s' <fork-sha>..<branch-tip> | grep 'Phase 0: red tests' | tail -1 | cut -d' ' -f1)

if [ -z "$RED" ]; then
  : # FAIL — see below. Do NOT fall through to the diff.
else
  # The RED commit IS the manifest of frozen files (Step 0e stages them explicitly by
  # path), so ask git what it froze instead of guessing at globs — exact by construction,
  # language-agnostic, and it catches Rust/Go inline `#[cfg(test)]` tests living in source
  # files, which a '*_test.*' glob would miss entirely.
  FROZEN=$(git show --name-only --format= "$RED")

  if [ -z "$FROZEN" ]; then
    # GUARD: empty $FROZEN makes the pathspec vanish, and `git diff A..B --` diffs the
    # ENTIRE repo — every source change would look like a touched frozen file. An empty
    # Phase 0 commit is itself a FAIL, not a clean gate. Do NOT fall through to the diff.
    echo "FAIL: Phase 0 commit $RED froze no files — the baseline is empty"
  else
    # -w -M: whitespace-blind + rename-aware, so a gofmt or a rename is not read as tampering.
    git diff -w -M --numstat "$RED"..<branch-tip> -- $FROZEN   # any deletions → classify hunks
  fi
fi
```

**The empty-`$RED` guard is load-bearing.** `git diff $RED..<tip>` with `$RED` unset expands
to `git diff ..<tip>`, which git resolves as `HEAD..<tip>` — an empty diff that falls
through looking *clean*. An unguarded check would silently pass the exact case below.

**Context economy (spec §9):** the orchestrator never ingests raw diffs. `--numstat` is the
trigger — any nonzero **deletion** count on a frozen file means something was changed or
removed, not merely added. Only then hand the specific files to a subagent for hunk
classification, and take back findings, not code.

**No Phase 0 red-test commit found → FAIL immediately.** Do not treat a missing baseline
as "nothing to check" — it is the *strongest* failure, not the absence of one. An agent
that never wrote a failing test never proved its tests can fail, so its green suite is
unfalsifiable: tests written after (or alongside) the implementation are free to assert
whatever the code already does. This is the cheaper evasion of the whole rule, and a
tamper diff that only runs when a baseline exists rewards skipping the baseline.
Observed live on SOP-110 (sophie), which went from fork straight to
`[SOP-110] Implement …` with tests in the same commit — no red state ever existed, and
every downstream gate was green.

Finding: `<branch> — no Phase 0 red-test commit; tests were never shown failing. Re-run
with red tests committed in RED state before implementation.`

With a baseline present, read the diff and classify every hunk:

- **Added test / added assertion** — fine. Agents are encouraged to add coverage.
- **Removed, skipped, or commented-out test** — FAIL.
- **A changed assertion — an expected value edited in place** — FAIL.

That last one is the tell, and it is worth being precise about, because it is the case
that looks most innocent in a diff: a line that *already asserted something* now asserts
something *different*. `assertEqual(x, 0x2C)` → `assertEqual(x, 0x1F)`. `assertEqual` →
`assertAlmostEqual`. An exact value → a range, a not-nil, a no-error. The agent will
have a reason. The commit message will be confident and often cites a real standard.
**The reason is irrelevant.** A vetted expected value changed by the model whose code
had to satisfy it is tampering by construction, regardless of how it is narrated.

FAIL with the finding as `<test file>:<line> — red-test assertion changed after RED
commit: <old> → <new> — restore the vetted assertion and fix the code under test`.

If the agent genuinely proves the ticket's expected value wrong (a cited spec, a real
table), that is a **ticket defect**, not a passing implementation: it goes back for a
rewrite with the corrected expectation, and the red test is re-vetted before the code is
allowed to satisfy it.

## Redness confirmation — was the baseline ever red? (mechanical, before the subagents)

Run only if the tamper check passed. The tamper check answers *"did the frozen tests
change since RED?"* — this answers a question it structurally cannot: *"were they ever
red in the first place?"* `:plan` Step 0e's rule ("only tests observed FAILING at 0d
may enter this commit") is prose the agent itself enforces; nothing external re-checks
it. SOP-110 (sophie) shipped tests in the same commit as the implementation — never
shown failing — and every downstream gate read the result as a clean baseline, because
every downstream gate only asks whether something *changed*.

**One script, cache-gated.** A full checkout plus a test run has real cost; a relaunch on
the same ticket must not re-pay it for a baseline already confirmed. The steps below —
the cache check, the worktree checkout, the test-command resolution, and the run — are
one continuous script, not independent fragments; the checkout and run must sit **inside**
the cache-miss branch, or caching becomes decorative:

```bash
CACHE="scratch/runs/$RUN_ID/redness-checks/$TICKET-${RED:0:12}.txt"
if [ -f "$CACHE" ]; then
  STATUS_CACHED=$(cat "$CACHE")   # already classified for this $RED — skip everything below
else
  WORKTREE=$(mktemp -d)
  git worktree add -q "$WORKTREE" "$RED"

  # Resolve the test command the same way :plan Step 0a does — task_plan.md's
  # **Test command:** line if present, else the same auto-detect table — rather
  # than a second, divergent resolution that could silently disagree with what
  # Phase 0 itself used. task_plan.md lives in the ticket's tracking directory,
  # not the repo, so it is read from there regardless of which SHA is checked out.
  TEST_CMD=$(grep -m1 '^\*\*Test command:\*\*' task_plan.md 2>/dev/null | sed 's/^\*\*Test command:\*\* //')
  # else auto-detect per plan-phase0-mechanics.md 0a's table

  # Scoped to $FROZEN — the same file set the tamper check above already computed,
  # not the whole suite. Output is captured because it, not the exit code alone,
  # distinguishes the two failure shapes classified below.
  ( cd "$WORKTREE" && eval "$TEST_CMD $FROZEN" ) > "$CACHE.output" 2>&1
  STATUS=$?
  git worktree remove --force "$WORKTREE"
fi
```

**On a cache hit, `$STATUS_CACHED` already holds one of the three dispositions below —
skip straight to acting on it.** On a cache miss, classify `$STATUS` — exit code alone is
not enough, so this is three outcomes, not two:

- **Exit 0** → **never-red** → **FAIL**. A test that passes cleanly against the code at
  `$RED` asserts what the code already did; it proves nothing was implemented to satisfy
  it.
- **Non-zero, but the failure never reached an assertion** (a collection, import, or
  setup error — the frozen test imports a module the implementation adds later, or fails
  to parse) → **unverifiable** → **FAIL**, distinct from the outcome above. A bare "assert
  non-zero exit" would let this launder through as red: the run genuinely failed, but
  nothing was ever asserted, so it proves exactly as little as a clean pass does. Same
  distinction BILL-340 drew for the CC gate — a check that could not run must not read as
  a check that passed. For this repo's own suite the concrete signal is pytest's own exit
  codes: **1** is a real assertion failure, **2** is a collection error (verified
  empirically, pytest 9.0.3) — for other frameworks, classify by the same principle stated
  here (did a specific assertion actually fire, or did the run error out before reaching
  one), since this file is read and interpreted, not executed verbatim.
- **Non-zero, with a genuine assertion failure** → **genuinely-red** → **PASS**.

Whichever disposition was reached (fresh or cached), write it to `$CACHE` before
continuing — a fresh classification caches itself for the next relaunch; a cache hit
rewrites the same value, which is harmless.

A FAIL here ends verification the same way a tamper-check FAIL does — no subagent is
spawned, and the relaunch handoff below carries the finding.

## The two subagents

Run only if the tamper check **and** the redness confirmation both passed.

Both are **fresh** (no orchestrator conversation history), run on the handoff-verifier
tier — `[stage_tiers].handoff_verifier` (default `medium`) → `[tiers].<that tier>` —
and read the **actual artifacts** — the ticket body, the worktree, the diff between
the recorded fork SHA and the branch tip — **never the agent's claims** (its ticket
comments and PR description are the *subject* of scrutiny, not evidence).

Run both in parallel — they are independent, and because they only **read** (no
worktree of their own, no router env) they are spawned directly as orchestrator
subagents, not via the fleet's headless-CLI launch (Step 4's mechanism is for the
implementation agent, which writes).

(These orchestrator-subagent `Agent(...)` spawns cannot carry a reasoning-effort
value — see `design/agent-effort-capability.md`, BILL-333.)

### 1. Requirements adversary

Charter: *fail this work if you can.* Score the diff against the ticket's
**Definition of done** item by item, and each **Observable behavior**. The verdict
vocabulary (`met` / `not-met` / `unverifiable`) and the evidence sources are shared
with `:merge` and `:document` so the three cannot disagree:
→ Read `~/.claude/commands/slopstop-run-refs/dod-scoring.md`

Everything below is the fleet-only charter, which stays here:

- criteria met only on paper (asserted in comments, absent in code),
- **vacuous or code-shaped tests** — a red test that passes without pinning the *ticket's*
  stated expectation: a weakened assertion, a test of the implementation rather than the
  expectation, or an expected value transcribed wrong from the start. Check every
  now-green red test against the **ticket**, not against what the code returns — the tamper check
  only sees values edited *after* the RED commit, so a value that was wrong on arrival is
  invisible to it and yours alone to catch.
- **the three evasions the tamper check's diff cannot see** — the tamper check is mechanical and trusts the
  frozen file set; you are the backstop for what it structurally misses. For each red test,
  confirm: (a) **no shadow** — no second definition of the same test name (in any commit)
  neutralizes it, including via rename; (b) **the expected value is in the frozen test
  itself**, not read from a helper / `conftest.py` / fixture / golden file that the Phase 0
  commit did not freeze — trace the assertion's inputs and confirm none were edited after
  RED; (c) **the test was actually red** — the behavior it pins genuinely fails without the
  agent's implementation (mentally, or by reverting the source hunk), not merely green with
  a `Phase 0` label. These are the diff-blind evasions catalogued in `pr-slop-detection.md`.
- **scope violations** — work outside the file map or the Out of scope fences
  (mechanically pre-checked by monitoring; judged here for substance),
- regressions in behavior the ticket said must stay green.

### 2. Code reviewer

Is the implementation acceptable — correctness of the changed code, no removed
invariants, honest error handling, house-style conformance. (The agent already ran
`:pr`'s inline review at the small tier; this is the medium-tier second opinion.)

## Verdict schema — the only thing that returns

Each subagent's final message is exactly:

```
VERDICT: PASS | FAIL
FINDINGS:                    (omit when PASS)
1. <file>:<line> — <specific defect> — <what would fix it>
...
```

**The orchestrator never ingests diffs** — findings and verdicts enter this context;
code does not (context economy, spec §9). If a finding needs more detail than a
file:line line can carry, the subagent writes it to
`scratch/runs/$RUN_ID/verdicts/<TICKET>-attempt<N>.md` and the finding cites that
file.

## On failure — the relaunch handoff

The tamper check FAILs, the redness confirmation FAILs, or either subagent FAILs → the
attempt is spent:

1. Record the verdicts in `fleet-state.md` and post a verdict marker on the ticket. On a
   tamper-check or redness-confirmation FAIL there are no subagent verdicts to record —
   the check's finding stands alone, and the relaunch brief carries it verbatim.
2. Relaunch the agent (Step 4's mechanism) **in the same preserved worktree** — never
   a fresh clone; the code under correction is the starting point.
3. The new brief's findings slot carries the **specific findings verbatim**
   (file:line, quoted DoD items). A retry without new information is a wasted
   attempt — if there are no specific findings, something is wrong with the verdict,
   not the agent.
4. Budget accounting and the 2-failure diagnosis fork (rewrite vs escalation) are
   Step 7's — verification only verifies, records, and hands off.

Tamper check clean and both subagents PASS → the ticket is **blessed** and queues for Step 8
integration. Blessing binds
to a specific commit: record the branch **tip SHA at verdict time** in `fleet-state.md`
(the `verdicts` cell, e.g. `PASS@<sha>`) alongside the two verdicts. Step 8 re-checks the
tip before integrating — if it has advanced past the recorded blessed SHA (a relaunch,
rewrite, or salvage commit landed on the branch), the blessing is void and this handoff
verification re-runs on the new tip. Nothing else moves a preserved branch's tip (agents
never merge or rebase, §7a), so a sibling's serial integration never voids a blessing.
