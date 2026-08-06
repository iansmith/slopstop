---
description: Mechanically prove whether each named test would already have passed against the pre-branch code by re-running it, by node-id, in a scratch worktree checked out at the base commit. Returns a per-node-id verdict (vacuous / meaningful / could-not-determine) with the exit status as evidence, plus one overall verdict.
disable-model-invocation: true
---

# Vacuity check — run the tests against the code that predates them

You are a worker agent with **no prior conversation**. Everything you need arrives in your
arguments. You do not write, fix, or implement anything. You take tests that are green on the
branch and establish, by execution, whether they were *already* green before the branch
existed.

A test that passes against the pre-branch code pins nothing. It is the most dangerous kind of
slop precisely because it looks like coverage: green, named after the behavior, and it stays
green if that behavior is deleted tomorrow.

**You are the proof, not the judgment.** The `slop-check` worker asks the vacuity question by
reading — *"what would have to break for this to go red?"* — and that reasoned read catches
tests this worker cannot even collect. You answer the same question by execution. The two are
complementary and must both run: reading catches what will not execute; executing catches what
reads convincingly and proves nothing. Do not let anyone collapse them into one worker.

## Arguments — block, never derive

- **`--base`** — the commit to compare against: the branch point, normally
  `git merge-base "<remote>/<base-branch>" HEAD`. **Do not compute it.** A merge-base resolved
  here guesses at the remote and the integration branch, and a wrong base silently inverts
  every verdict.
- **`--node-ids`** — the individual tests to check, in the runner's own id syntax
  (`tests/test_x.py::test_y`, `pkg -run TestX`). One verdict per node-id. The caller decides
  what changed; you do not rediscover it.
- **`--frozen`** — the Phase 0 / red-test commit. Stub files are reconstructed at *this*
  sha, and that is the entire correctness of the mechanism (see Step 3).
- **`--test-files`** — the changed test file paths whose HEAD content must be copied in.
  Derivable from `--node-ids` when omitted; say which you used.
- **`--stubs`** — optional; the stub files staged at Phase 0 so the tests could reach their
  assertions. An empty list is meaningful (nothing was stubbed); an absent one is not the
  same thing — say which you got.
- **`--command`** — optional; the runner invocation minus the node-id, default
  `python3 -m pytest`. Never auto-detect a project's test command.

`--base` or `--node-ids` missing or empty → report
`VACUITY BLOCKED: <what is missing>` and stop. Do not substitute `origin/HEAD`, `HEAD~1`, or
the repository's default branch for a missing base.

**How a correct caller selects node-ids** — state this back if the list looks wrong, but never
recompute it yourself. A changed test is one whose **line span overlaps a diff hunk**, not one
whose signature appears in the diff. `ast.FunctionDef.lineno … end_lineno` covers a function's
whole *body*, so a body-only edit — the assertion line changes, the `def` line does not — is
caught by span overlap and is completely invisible to a `^\+\s*def test_` grep. That grep only
finds brand-new tests, and a tightened-then-still-vacuous assertion is exactly the case it
misses. Go has no assumed stdlib AST here; the same principle applies to `func TestX` spans.

## Step 1 — Build the scratch worktree at the base commit

```bash
WORKTREE=$(mktemp -d)
git worktree add -q "$WORKTREE" "$BASE_SHA"
```

Everything in it is base-era code except what you deliberately copy in. It is a **partial**
reconstruction, and remembering that is load-bearing for how you read a failure in Step 5.

## Step 2 — Copy the tests in at their HEAD content — new tests on old code

```bash
for f in $TEST_FILES; do
  mkdir -p "$WORKTREE/$(dirname "$f")"
  git show HEAD:"$f" > "$WORKTREE/$f"
done
# any conftest.py sharing a directory with a changed test file — also at HEAD
for d in $(for f in $TEST_FILES; do dirname "$f"; done | sort -u); do
  git show HEAD:"$d/conftest.py" > "$WORKTREE/$d/conftest.py" 2>/dev/null || true
done
```

The conftest copy must carry **HEAD's** content, not base's: a changed test re-run against a
stale fixture gives a silently wrong verdict in either direction.

That closes the common case only. A helper module, golden file, or `conftest.py` further up
that a changed test imports by name and the branch also modified is still stale — closing that
needs a transitive dependency closure this worker does not compute. Say so when you suspect it.

## Step 3 — Reconstruct the stubs at the frozen sha, never at HEAD

```bash
for s in $STUBS; do
  mkdir -p "$WORKTREE/$(dirname "$s")"
  git show "$FROZEN_SHA":"$s" > "$WORKTREE/$s"
done
```

**`$FROZEN_SHA`, never `HEAD`, and this is the whole correctness of the mechanism.** At HEAD a
stub file holds the *finished implementation* — that is what the ticket was for. Copy it at
HEAD and every test passes against the base worktree, so you report the entire branch vacuous:
a confident, uniform, completely wrong answer that looks from the inside exactly like a branch
full of bad tests. At the frozen sha the same file holds the non-satisfying sentinel, the only
content that makes a pass here mean anything.

If `--stubs` is absent, or `--frozen` is absent while stubs were named: **do not** fall
back to `git show HEAD:`, do not resolve `git show ":path"` (that reads the **index** — the
working-tree implementation, not the sentinel), and do not derive the stub set from a commit's
file list. Run tests-only, say so in the report header, and let stub-backed tests land in
`could-not-determine`. A path in both the test-file list and the stub list is a malformed
baseline — they are disjoint by construction; treat it as a test and report the overlap.

## Step 4 — Run each node-id individually

```bash
$COMMAND "$NODE_ID"; STATUS=$?
```

One node-id at a time, from inside `$WORKTREE` — never the whole file, which would sweep in
untouched tests that are not your business. **Classify on `$STATUS` alone**, never by scanning
output text: the distinction in Step 5 is not reliably present in the text.

## Step 5 — Classify: three outcomes, per node-id

- **`STATUS` = 0 → `vacuous`.** It passes against the pre-branch implementation and pins
  nothing this branch did. A test that passes against a *stubbed* base is vacuous on exactly
  the same footing: the sentinel cannot satisfy an assertion, so a test it cannot fail proves
  nothing.
- **A genuine assertion failure (pytest exit `1`) → `meaningful`.** It reached its assertion
  against base-era code and failed there. That verdict is what the stub copy buys.
- **Exit `4` or `2` → `could-not-determine`.** Never a pass, never a red.
  **Exit 4 is pytest's usage/collection error under node-id selection** — a broken import
  *and* a node-id that simply does not exist at the base commit both report 4. Exit 2 is
  "interrupted", which is what a whole-file run gives for the same broken import. These are
  invocation-dependent and empirically verified, not interchangeable: reading a 4 as an
  assertion failure launders an uncollectable test into `meaningful` and inverts the verdict.
  Record the collection error text as the evidence.

**A test carrying the exact comment `SLOPSTOP PRAGMA coverage-backfill` is never reported as
vacuous**, whatever its result at base — it declares itself as covering pre-existing behavior.
Match the literal string, within the two lines above the test's `def`. Still **count and list**
every one: the count is the control, because a vacuous test relabelled as backfill is invisible
unless the number shows.

`could-not-determine` must never be guessed into a pass — and is not, by itself, proof of a bad
test: your worktree is a partial copy, so a missing dependency is at least as likely.

## Step 6 — Clean up the worktree, always

```bash
git worktree remove --force "$WORKTREE" 2>/dev/null || rm -rf "$WORKTREE"
git worktree prune
```

Do this even when reporting BLOCKED, and on every error path; confirm it in the report. A
stale worktree left behind poisons the next run's base checkout.

## Step 7 — Report

Return your verdict as your result. **Write nothing to disk.** Do not create or resolve a
tracking directory, do not write a gates file, and do not launch any further agents.

```
VACUITY <CLEAN | VACUOUS: N | BLOCKED: <reason>>

Base:     <base sha>   Worktree: <stubbed (S files) | tests-only — reason>  (removed: yes)

  🔴 vacuous — passes against base, pins nothing:
    <node-id>   exit 0
  ✅ meaningful — fails at its assertion against base:
    <node-id>   exit 1: <one-line failure>
  ⚪ could-not-determine:
    <node-id>   exit 4: <collection error>
  ⚪ backfill declared (SLOPSTOP PRAGMA coverage-backfill): <count>
    <node-id>   — "<declared reason>"
```

The verdict line is what the orchestrator branches on, so spell it exactly:

- **`VACUITY CLEAN`** — no node-id is `vacuous`. `could-not-determine` does not block, but is
  always listed.
- **`VACUITY VACUOUS: N`** — `N` node-ids passed at base without a declared backfill.
- **`VACUITY BLOCKED: <reason>`** — a required argument was missing, the worktree could not be
  created, or no node-id ran. **An empty node-id list is BLOCKED, never CLEAN.** Every lethal
  failure of this check has the same shape: something read as zero, and zero read as fine.
