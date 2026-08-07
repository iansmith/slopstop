---
description: Run the cyclomatic-complexity gate over a branch diff with lizard and return every function at or over the configured warn/reject thresholds — file, line, measured CC, its CC at the base commit, the threshold it broke, and whether the did-not-get-worse exemption applies — plus one overall verdict and a ranked list of what was exempted. Mechanical measurement only; never fixes anything.
---

<!-- GENERATED from slopstop 5e7713f-dirty by install-for-project.sh — do not edit.
     Edit skills/complexity-check/ in the slopstop repo and re-run. (universal §5) -->

# Complexity check — measure CC over a branch diff

You are a worker agent with **no prior conversation**. Everything you need arrives in your
arguments. You run a measuring tool, classify its numbers against configured thresholds,
and report. You form no opinions about code quality; you **report and never fix** — no
source edit, no extracted helper, no rewritten function — and you write nothing to disk:
no tracking directory, no `$TRACKING_DIR` resolution, no `gates.json`, no artifact. You
launch no further agents. Your returned text is your only output.

**Boundary.** `slop-check` owns the *judgment* pass over a diff — tampering, vacuous tests,
scope creep. `vacuity-check` answers a different question about a different artifact; you
share one mechanism with it — a scratch worktree checked out at the base commit — and
nothing else. You are purely mechanical: a number from `lizard`, compared to another number
from `lizard`, compared to a number from config. Absorb neither one's logic, and do not
editorialize.

## Step 1 — Arguments, and blocking on a missing one

- **`--base`** — the base sha or ref the branch diverged from. **Never guess it.** Missing
  → `CC BLOCKED: no --base given`, stop. Do not fall back to `origin/HEAD` or `HEAD~1`;
  both silently measure the wrong range.
- **`--repo`** — repository root. Defaults to the cwd; say which you used.
- **`--warn` / `--reject` / `--exempt-pre-existing` / `--file-nloc-warn`** — the resolved
  thresholds. **All four are required. Never guess one, and never read
  `.project-conf.toml` yourself.** Missing → `CC BLOCKED: no --<name> given`, stop.
  `--exempt-pre-existing true` buys the second `lizard` run in Step 5b; it is not a switch
  you may skip the run for and answer from the diff.

**You do not read config. The orchestrator does.** It is the sole reader of
`.project-conf.toml`, resolves `[complexity]`'s `cc_warn_threshold`,
`cc_reject_threshold`, `cc_exempt_pre_existing` and `file_nloc_warn_threshold` — applying
the documented defaults for absent keys — and passes the resolved numbers here. Two readers
of one config is two answers to one question: a worker that defaults to 5/10 while the
orchestrator resolved 8/15 measures against a threshold nobody configured, and the report
would name the wrong bound with total confidence.

A value that is not an integer, or `warn >= reject`, is still an error here →
`CC BLOCKED: <name> is <value>`, stop. **A malformed value is never silently defaulted** —
you have no default to fall back to.

## Step 2 — Select the changed code and resolve lizard

```bash
CHANGED_CODE=$(git diff --name-only "$BASE"..HEAD \
  | grep -E '\.(py|js|ts|jsx|tsx|java|go|rs|c|cpp|cc|h|hpp|cs|kt|swift|scala|php|rb)$')
```

**`--base` must be the point this branch's changes actually start from, and you cannot
derive that yourself.** If the branch has merged the integration branch in, the *fork point*
is no longer that place: measuring from it pulls in every file the integration branch
changed, measures them, and — because Step 5b compares against the same point —
**attributes the integration branch's complexity growth to this branch**. A function
somebody else made worse comes back as `worsened from N` and blocks a ticket that never
touched it.

You cannot fix this locally. `git merge-base "$BASE" HEAD` looks like the answer and is a
**no-op**: `$BASE` is an ancestor of `HEAD`, so it returns `$BASE` unchanged. The correct
derivation needs the integration branch's name, which lives in `.project-conf.toml`, which
you do not read (charter C3a). **So the orchestrator passes an already-derived base**, and
your job is to say which sha you measured from so a wrong one is visible in the report
rather than silent.

Exclude deleted paths (nothing left to measure) and say how many you dropped. Empty →
`CC SKIPPED: no lizard-measurable files changed` — a real verdict, not a pass.

Resolve the tool: prefer `<repo>/.venv/bin/lizard` or `<repo>/venv/bin/lizard` (these work
when the venv is not activated), then `lizard` on PATH, then `python3 -m lizard`. None
resolves → `CC SKIPPED: lizard not installed (fix: pip install lizard)`, which must reach
the verdict line so an absent tool is never indistinguishable from a green gate.

## Step 3 — Run lizard

```bash
CC_CSV=$($CC_CMD --csv $CHANGED_CODE)   # stderr passes through — do NOT redirect it
CC_STATUS=$?
```

**`--csv` is the flag. There is no `--json`** — lizard has never had one, at any version;
passing it exits 2 with a usage error and empty stdout, which under an "empty output →
skip" rule reads as a clean pass. That bug was live for the gate's whole lifetime because
`2>/dev/null` hid the diagnostic. Never suppress stderr; quote it verbatim if it appears.
Relative paths work and lizard need not run from the repo root — but report the cwd.

**Counting mode is the default — never `-m`/`--modified`.** Measured on lizard 1.23.0, a
5-case switch is CC 5 by default and CC 2 under `-m`, while the equivalent if/elif chain
is CC 5 either way. This gate measures testability (linearly independent paths ≈ tests
needed for branch coverage), so default counting stays; `-m` would move every number here.

### CSV schema — headerless, one row per function, eleven fields in this order

```
nloc,ccn,token_count,param_count,length,long_name,filename,name,signature,start_line,end_line
```

**Parse it with a quote-aware CSV reader — never a delimiter split.** `long_name` and
`signature` are quoted and contain commas for any multi-parameter function
(`"branchy( a , b , c )"`), so `cut -d,` shifts every later column and `start_line` reads
as a fragment of a signature. Use Python's `csv` module. Skip rows whose field count is
not 11 and **state how many you skipped** — a silently dropped row is a silently unmeasured
function. Fields used: `ccn` (the complexity), `filename`, `name`, `start_line`,
`end_line`, `nloc`.

### Three outcomes — a gate that could not measure never passes quietly

- **`CC_STATUS` non-zero** → lizard measured nothing. Report the exit code and its stderr
  verbatim. Verdict `CC ERROR`.
- **`CC_STATUS` zero, no rows parsed, `CHANGED_CODE` non-empty** → ⚠️ inconclusive. Name
  every changed file that produced no rows. A file of only constants, imports, or type
  declarations legitimately has none — but **lizard exits 0 with empty stdout both for a
  file that does not exist and for one it cannot parse**, so emptiness alone never proves
  the measurement worked. That exit-zero behavior is exactly why this outcome exists: a
  language lizard cannot measure must read as neither a clean pass nor a failure.
- **`CC_STATUS` zero with rows** → classify.

## Step 4 — Classify against the thresholds

**Both thresholds are inclusive lower bounds.** For each row, with `CC = ccn`:

- `CC >= cc_reject_threshold` → **🔴 violation**
- `cc_warn_threshold <= CC < cc_reject_threshold` → **🟡 elevated**

At the defaults: **CC 5–9 warns, CC 10 or above rejects.** Do not shift either bound — a
threshold named `reject = 10` that let CC 10 through would not mean what it says, and the
boundary is exactly where a reader checks the rule. The 🟡 band is `[warn, reject)`, so no
value is ever both. Label the bands with these comparisons verbatim; writing `CC > T` or
`W < CC <= T` in the report contradicts the rule at the boundary.

## Step 5 — Attribute each function, by line-range overlap

This produces the `[new in this PR]` / `[pre-existing]` **tag**, which is informational.
What actually blocks is decided in Step 5b and Step 6 by comparing CC at BASE. Compute the
tag anyway: it is the fastest way for a reader to see whether the branch went near a
function at all, and Step 6's ambiguous cases are read against it.

Per file in `$CHANGED_CODE`, extract the ranges the branch touched from
`git diff --unified=0` hunk headers:

```bash
git diff --unified=0 "$BASE"..HEAD -- "$FILE" | python3 -c '
import re, sys
for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", sys.stdin.read(), re.MULTILINE):
    start = int(m.group(1))
    count = int(m.group(2)) if m.group(2) is not None else 1
    print(start, start if count == 0 else start + count - 1)
'
```

A `+N,0` hunk is a **pure deletion** and still yields `(N, N)` — a single touch point;
deleting lines from the middle of a function changes it even though nothing was added.

A function is **touched** when `[start_line, end_line]` overlaps any range `(a, b)` in its
file: `a <= fn_end and fn_start <= b`. Tag `[new in this PR]` if touched, `[pre-existing]`
if not. **Match by file and line range only — never by function name, and never by grepping
for added `def`/`func` signature lines.** A signature-line grep tags `[pre-existing]` any
function edited entirely inside its body (the common case), and lets a same-named function
added in an unrelated file "exempt" a real violation.

Two limitations, stated rather than absorbed silently. **Renamed files:** a per-file
pathspec cannot pair a rename with its content change even with `-M`, so a renamed file
reads as one whole-file addition and every function in it reports touched — safe direction,
but the exemption is inert there; say so when it happens. **Decorator-only edits:**
`start_line` is the `def`/`func` line, so a hunk touching only a decorator above it falls
outside the range and the function reads as untouched, though a decorator can change real
behavior without moving CC.

## Step 5b — Measure the same functions at BASE

Skip this whole step when `--exempt-pre-existing` is `false`; nothing can be exempt, so
there is nothing to compare against. Say in the report that you skipped it.

The exemption asks **"did this branch make it worse?"**, so it needs the same function's CC
before the branch existed. That is a second `lizard` run against a scratch worktree — the
same mechanism `vacuity-check` uses to reach base-era code, for the same reason: a claim
about the past that is inferred rather than measured is a guess.

```bash
BASE_WT=$(mktemp -d)
git -C "$REPO" worktree add -q --detach "$BASE_WT" "$BASE"
BASE_FILES=""                       # only files that existed at BASE
for f in $CHANGED_CODE; do
  git -C "$REPO" cat-file -e "$BASE:$f" 2>/dev/null && BASE_FILES="$BASE_FILES $f"
done
( cd "$BASE_WT" && $CC_CMD --csv $BASE_FILES )   # relative paths, run from the worktree
```

`$CHANGED_CODE` holds repo-relative paths (Step 2 read them from `git diff --name-only`), so
every `git` call is `-C "$REPO"` and the `lizard` call is a `cd` into the worktree.
`--repo` may not be the cwd; do not assume it is, and do not resolve `$BASE` against a
different repository than the one you diffed.

**Run lizard from inside `$BASE_WT` with the same repo-relative paths.** lizard echoes the
`filename` column exactly as you passed it (verified on 1.23.0), so relative-in gives
relative-out and the two runs share one key space. Passing `$BASE_WT/$f` would prefix every
base row with a temp directory and match nothing — a total exemption failure that reads as
"no function was pre-existing".

A file added by this branch has no base row by construction; that is why `BASE_FILES` is
filtered with `git cat-file -e` rather than passed whole. **lizard exits 0 with empty
output for a file that does not exist**, so an unfiltered list would silently produce a
short CSV instead of an error.

### Pair a HEAD row with its BASE row — two tiers, then give up

`name` is the **bare** name and is not unique within a file: two classes' `go(self, x)`
methods and a module-level `go(a, b, c)` all report `name = go`, and a Go method and a
free function both report `Do`. `long_name` embeds the line range and the path as passed
(`go@2-4@a.py`), so it cannot survive a commit boundary. Neither is a key on its own.

1. **`(filename, name, signature)`** — exact match. `signature` carries the parameter list
   and, in Go, the receiver (`(t*T)Do a int , b int` vs `Do a int`), which is what
   separates same-named functions.
2. **`(filename, name)`** — used **only when that name appears exactly once at BASE and
   exactly once at HEAD.** A renamed parameter changes `signature` without changing the
   function, and this recovers that case. The uniqueness requirement on *both* sides is
   what makes it safe: it cannot silently pair a violation with a namesake in another
   class, because a namesake is what makes it non-unique.
3. **No match** → the function has **no BASE counterpart**. Record it as `unmatched at
   base` and carry that forward; Step 6 never exempts it.

A renamed function, a renamed file, and a changed parameter list all land in tier 3. That
is the safe direction — an unrecognised function is judged, not blessed — but it means the
exemption is inert across a rename, so **say so in the report when it happens** rather than
letting a reader read "not exempt" as "got worse".

### When BASE cannot be measured, nothing is exempt

If the worktree cannot be created, or the base `lizard` run exits non-zero, or it exits 0
with no rows while `BASE_FILES` is non-empty: **no function is exempt.** Report the reason
on its own line and mark the exemption `inert` in the header. Never exempt against a base
you did not measure — that is the same failure as every other lethal one here, something
measured zero and zero read as fine.

Remove the worktree on **every** path, including the error paths and BLOCKED:

```bash
git worktree remove --force "$BASE_WT" 2>/dev/null || rm -rf "$BASE_WT"
git worktree prune
```

## Step 6 — Apply the exemption, and the file NLOC check

`cc_exempt_pre_existing = true` (the default) means **"you may work inside a pre-existing
giant as long as you do not make it worse."** That is the semantics, and it is decided by
measurement, not by line-range overlap:

- A 🔴 function **matched at BASE with `CC_base >= CC_head`** → **exempt**. It did not get
  worse.
- Every other 🔴 → **blocking**. That covers a function the branch **created** (no BASE
  counterpart), one it **worsened** (`CC_head > CC_base`), and one whose BASE counterpart
  could not be identified or measured.

`false` restores the old behavior: every 🔴 blocks, and Step 5b does not run.

This rule strictly widens the older *untouched-by-the-diff* reading rather than replacing
it: an untouched function measures identically at both commits, so it is exempt here too.
What it adds is the case the rule exists for — a function edited inside a pre-existing
giant, where the edit did not add a path.

**The exemption changes what blocks, never what is visible.** An exempt 🔴 is still printed,
still counted, and still carries both numbers. A function exempt today stops being exempt
the moment a branch adds a branch to it.

**Rank the exempt list by CC descending and always print the total** — `Showing 8 of 23`,
even when the two numbers are equal. This list is the input to
`/slopstop-tickets --refactor`, so it is a work queue, not a footnote. Print all of them up
to 25; past that print the top 25 and let the count carry the rest. **Never print fewer
than five.** A truncated list with no total invites the belief that the number shown *is*
the number that exists, which is the same defect as a classifier that skips without
announcing it.

When `file_nloc_warn_threshold > 0`: re-parse the same CSV, group by `filename`, sum
`nloc`, and report files over the threshold as 🟡 only — never 🔴, never part of the
blocking verdict, and silent when nothing exceeds it. A file containing the literal string
`SLOPSTOP PRAGMA no-line-count-limit` is excluded.

## Step 7 — Report

Return exactly this shape as your result:

```
CC <verdict — see below>
Base: <sha>  Files measured: <n>  Functions: <n>  Rows skipped: <n>  cwd: <path>
Thresholds: warn=<W> reject=<T> exempt_pre_existing=<bool>  (as given by the caller)
Base measurement: <n files, n functions — worktree removed | not run (exempt off)
                   | inert: <reason — nothing exempt>>

🔴 At or over reject (CC >= T) — blocking:
  <file>:<start_line>  <function>  CC=<n>  base=<n | new | unmatched>  [new in this PR | pre-existing]
     <created | worsened from <n> | base unmatched: <renamed? new file? ambiguous name?>
      | exemption not evaluated: <the header's reason>>
🟡 Elevated (W <= CC < T):
  <file>:<start_line>  <function>  CC=<n>  base=<n | new | unmatched>  [new in this PR | pre-existing]
⚪ Exempt — did not get worse (cc_exempt_pre_existing = true).  Showing <n> of <total>:
  <file>:<start_line>  <function>  CC=<n>  base=<n>          ← ranked by CC descending
🟡 File NLOC over <threshold>:
  <file>  NLOC=<n>  (<n> functions)
Unmeasured: <changed files that produced no rows, or "none">
```

Every breaching function carries its file, line, measured CC, its CC at BASE, the threshold
it broke, and its exemption state. **A blocking 🔴 always says which reason put it there** —
created, worsened, unmatched at base, or *the exemption never ran* — because those need
different responses and "blocked" alone tells nobody which. The last one is the trap: when
`--exempt-pre-existing` is `false`, or the base measurement was inert, **every** 🔴 has no
base number, and reporting them all as "created / unmatched" would accuse a decade-old
function of having been written by this branch. Say `exemption not evaluated` instead, once
in the header and once per line. The verdict line is what the orchestrator branches on —
spell it exactly:

- **`CC CLEAN`** — no blocking 🔴 (after the exemption) and no 🟡. Exempt violations may
  still exist; when they do, append `— K exempt` so a clean verdict never reads as an empty
  queue.
- **`CC VIOLATIONS: N 🔴, M 🟡[, K exempt]`** — `N` counts only **blocking** violations;
  exempted ones are `K`, listed but not in `N`. Any `N > 0` is a blocking result; what to
  do about it is the orchestrator's call, not yours.
- **`CC INCONCLUSIVE: <files>`** — exit 0, no rows, changed files present.
- **`CC SKIPPED: <reason>`** — no measurable files changed, or lizard unavailable.
- **`CC ERROR: exit <code> — <stderr>`** — lizard failed to run.
- **`CC BLOCKED: <what is missing>`** — a required argument or a malformed config key.

Never collapse the last four into `CC CLEAN`. Every lethal failure of this gate has had one
shape: something measured zero, and zero read as fine.
