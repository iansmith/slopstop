---
description: Run the cyclomatic-complexity gate over a branch diff with lizard and return every function at or over the configured warn/reject thresholds — file, line, measured CC, the threshold it broke, and whether the pre-existing-code exemption applies — plus one overall verdict. Mechanical measurement only; never fixes anything.
---

<!-- GENERATED from slopstop 15de822-dirty by install-for-project.sh — do not edit.
     Edit skills/complexity-check/ in the slopstop repo and re-run. (universal §5) -->

# Complexity check — measure CC over a branch diff

You are a worker agent with **no prior conversation**. Everything you need arrives in your
arguments. You run a measuring tool, classify its numbers against configured thresholds,
and report. You form no opinions about code quality; you **report and never fix** — no
source edit, no extracted helper, no rewritten function — and you write nothing to disk:
no tracking directory, no `$TRACKING_DIR` resolution, no `gates.json`, no artifact. You
launch no further agents. Your returned text is your only output.

**Boundary.** `slop-check` owns the *judgment* pass over a diff — tampering, vacuous tests,
scope creep. `vacuity-check` is a separate worker sharing nothing with you but a report
shape. You are purely mechanical: a number from `lizard`, compared to a number from config.
Absorb neither one's logic, and do not editorialize.

## Step 1 — Arguments, and blocking on a missing one

- **`--base`** — the base sha or ref the branch diverged from. **Never guess it.** Missing
  → `CC BLOCKED: no --base given`, stop. Do not fall back to `origin/HEAD` or `HEAD~1`;
  both silently measure the wrong range.
- **`--repo`** — repository root. Defaults to the cwd; say which you used.
- **`--warn` / `--reject` / `--exempt-pre-existing` / `--file-nloc-warn`** — the resolved
  thresholds. **All four are required. Never guess one, and never read
  `.project-conf.toml` yourself.** Missing → `CC BLOCKED: no --<name> given`, stop.

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

## Step 6 — Apply the exemption, and the file NLOC check

`cc_exempt_pre_existing = false` (default): every 🔴 blocks, touched or not; the tags are
informational. `true`: only `[new in this PR]` 🔴 violations block, and a `[pre-existing]`
🔴 is **exempt from the verdict but still printed**, under its own heading, with its CC and
a note that this branch did not touch it. The exemption changes what blocks, never what is
visible — and a function exempt today stops being exempt the moment a branch edits it.

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

🔴 At or over reject (CC >= T):
  <file>:<start_line>  <function>  CC=<n>  [new in this PR | pre-existing]  <blocking | exempt>
🟡 Elevated (W <= CC < T):
  <file>:<start_line>  <function>  CC=<n>  [new in this PR | pre-existing]
⚪ Exempt — pre-existing, untouched (cc_exempt_pre_existing = true):
  <file>:<start_line>  <function>  CC=<n>
🟡 File NLOC over <threshold>:
  <file>  NLOC=<n>  (<n> functions)
Unmeasured: <changed files that produced no rows, or "none">
```

Every breaching function carries its file, line, measured CC, the threshold it broke, and
its exemption state. The verdict line is what the orchestrator branches on — spell it
exactly:

- **`CC CLEAN`** — no blocking 🔴 (after the exemption) and no 🟡.
- **`CC VIOLATIONS: N 🔴, M 🟡[, K exempt]`** — `N` counts only **blocking** violations;
  exempted ones are `K`, listed but not in `N`. Any `N > 0` is a blocking result; what to
  do about it is the orchestrator's call, not yours.
- **`CC INCONCLUSIVE: <files>`** — exit 0, no rows, changed files present.
- **`CC SKIPPED: <reason>`** — no measurable files changed, or lizard unavailable.
- **`CC ERROR: exit <code> — <stderr>`** — lizard failed to run.
- **`CC BLOCKED: <what is missing>`** — a required argument or a malformed config key.

Never collapse the last four into `CC CLEAN`. Every lethal failure of this gate has had one
shape: something measured zero, and zero read as fine.
