# PR CC Gate — Full Implementation

## BASE_SHA and CHANGED_CODE detection

```bash
BASE_SHA=$(git merge-base HEAD $ORIGIN_REMOTE/$(git remote show $ORIGIN_REMOTE | awk '/HEAD branch/{print $NF}') 2>/dev/null \
           || git merge-base HEAD $ORIGIN_REMOTE/master 2>/dev/null \
           || git merge-base HEAD $ORIGIN_REMOTE/main 2>/dev/null \
           || echo "HEAD~1")
# lizard-supported extensions (extend this list if your project uses others)
CHANGED_CODE=$(git diff --name-only "$BASE_SHA"..HEAD \
  | grep -E '\.(py|js|ts|jsx|tsx|java|go|rs|c|cpp|cc|h|hpp|cs|kt|swift|scala|php|rb)$')
```

If `CHANGED_CODE` is empty: skip this gate.

## Lizard availability — auto-install cascade

Check venv-local lizard binaries first (these work even when the venv is not
activated — common in Claude Desktop sessions where PATH does not include
`.venv/bin`). Then fall back to the system PATH and a pip auto-install.

```bash
# 1. Prefer a venv-local lizard relative to the repo root
_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
CC_CMD=""
for _candidate in \
    "${_REPO_ROOT}/.venv/bin/lizard" \
    "${_REPO_ROOT}/venv/bin/lizard"; do
  if [ -x "$_candidate" ]; then CC_CMD="$_candidate"; break; fi
done

# 2. Fall back to PATH / python3 -m lizard / auto-install
if [ -z "$CC_CMD" ]; then
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
fi
```

If `CC_CMD` is empty: skip with the warning above and continue to Step 1.

## Run CC analysis

```bash
CC_CSV=$($CC_CMD --csv $CHANGED_CODE)   # stderr passes through — do NOT redirect it
CC_STATUS=$?
```

**Use `--csv`. There is no `--json` flag** — lizard has never had one, at any version.
Passing it exits 2 with a usage error and empty stdout, which under the old "empty output
→ skip" rule read as a clean pass. **Do not suppress stderr here.** `2>/dev/null` on this
line is what made that failure look like a missing tool for the gate's entire lifetime;
letting it through puts lizard's own diagnostic in the transcript where the report can
quote it.

### Column contract

`--csv` output is **headerless**, one row per function, eleven fields in this order:

```
nloc,ccn,token_count,param_count,length,long_name,filename,name,signature,start_line,end_line
```

```
2,1,9,1,2,"simple@1-2@sample.py","sample.py","simple","simple( a )",1,2
12,7,44,3,12,"branchy@4-15@sample.py","sample.py","branchy","branchy( a , b , c )",4,15
```

**Parse it with a quote-aware CSV reader — never a delimiter split.** `long_name` and
`signature` are quoted and contain commas for any function with more than one parameter:
`"branchy( a , b , c )"` becomes four fields under `cut -d,` or `split(",")`, shifting
every later column so `start_line` reads as a fragment of a signature. Use Python's `csv`
module or an equivalent:

```bash
echo "$CC_CSV" | python3 -c '
import csv, sys
COLS = ["nloc","ccn","token_count","param_count","length",
        "long_name","filename","name","signature","start_line","end_line"]
rows = [dict(zip(COLS, r)) for r in csv.reader(sys.stdin) if len(r) == len(COLS)]
'
```

`COLS` is the one column list for this file — the File NLOC check below restates it rather
than inventing a second encoding, since `rows` itself does not survive past this step: it
lives inside a one-shot `python3 -c` process and is gone once that process exits. Each
consumer of `$CC_CSV` (CC classification here, the NLOC grouping below) re-parses it with
the same `COLS`, not a shared variable.

A row whose field count does not match is skipped by that guard — if any are, say so in
the report rather than passing over it, for the same reason the outcomes below exist.

The fields this gate uses: `ccn` (the cyclomatic complexity), `filename`, `name`,
`start_line`, `end_line`, and `nloc`.

### Three outcomes — a gate that could not measure never passes quietly

- **lizard exits non-zero** (`CC_STATUS`) → 🔴 **gate error**. lizard measured nothing. Report the
  exit code and lizard's stderr from the command output, verbatim. Interactive: hard stop,
  requires an explicit override with a reason. Autonomous: consult the same
  `benchmark-continue` path the CC violations use, and record the override with
  `"step": "pre_pr_cc_gate_measurement_failure"` so it is distinguishable from a clean run.
- **`CC_STATUS` is zero but no rows parsed, while `CHANGED_CODE` is non-empty** →
  ⚠️ **inconclusive**. Name every changed file that produced no rows. Do not hard-stop —
  a file of only constants, imports, or type declarations legitimately has no functions —
  but state it, and carry it into the Step 8 summary. **Emptiness alone cannot tell you
  the measurement worked:** lizard exits **0** with empty stdout both for a file that
  does not exist and for one it cannot parse, so this outcome must never resolve itself
  by staying quiet.
- **`CC_STATUS` is zero with rows** → classify against the thresholds below.

**A skipped gate is recorded too.** `CC_CMD` empty (lizard absent and un-installable) stays
a skip — that is a real environment condition with a stated fix, not a measurement failure —
but it posts a `"step": "pre_pr_cc_gate_tool_missing"` `## slopstop signals` PR comment (see
the benchmark override record format below) and appears in the Step 8 summary. Otherwise a
run where lizard never installed is, from the outside, identical to a clean gate; the pip
cascade above ends in `|| true` with its errors discarded, so a missing tool would be the
cheapest untraceable way to disable this gate.

Read both thresholds from `.project-conf.toml`:

- `cc_warn_threshold` from `[autonomous] cc_warn_threshold` (default: **5**)
- `cc_reject_threshold` from `[autonomous] cc_reject_threshold` (default: **10**)

**Both thresholds are inclusive lower bounds.** For each parsed row (`ccn` is the
complexity):
- `cyclomatic_complexity >= cc_reject_threshold` → **🔴 violation** (hard-gate)
- `cc_warn_threshold <= cyclomatic_complexity < cc_reject_threshold` → **🟡 elevated** (warning)

At the defaults that is: **CC 5–9 warns, CC 10 or above rejects.** The inclusive form is
deliberate — a threshold named `reject = 10` that let CC 10 through would not mean what
it says, and boundary values are exactly where a reader checks the rule.

**Counting mode: default, not `-m`/`--modified`.** lizard's `-m` flag counts a `switch`
with N cases as CC 1 instead of N. Not used here. CC's defensible meaning is the number
of linearly independent paths through a function — the minimum number of tests needed
for branch coverage — and a five-case switch genuinely needs five tests. `-m` would make
the metric understate that. Measured on lizard 1.23.0:

```
                              default    -m
5-case switch                   CC 5     CC 2
equivalent if/elif chain        CC 5     CC 5
```

The readability argument for `-m` is real — SonarSource's Cognitive Complexity collapses
a switch to one increment on exactly that basis, because a switch is easier to scan than
the equivalent if-chain — but that is a different metric measuring a different thing.
This gate measures testability, so it keeps default counting. Recorded here so `-m` is
not re-proposed as an obvious win: adopting it would change every number this gate
reports, which is a decision for the thresholds above, not a free improvement.

**Not a valid remedy: converting an if-chain to `switch`/`case`.** Under default counting
the two score identically (measured above: both CC 5), so the advice produces no
reduction, and an agent that follows it correctly concludes the guidance is wrong. A
dispatch or lookup *table* is the transformation that survives — it removes the branches
rather than restyling them.

## Scope: touched-by-this-branch vs. pre-existing

Tag each function by whether the branch's diff overlaps its line range —
`start_line`..`end_line` from the CSV parse above, against the diff's changed-line
ranges. Replaces an earlier signature-line grep entirely: that mechanism matched only
lines where a `def`/`func`/etc. token was *added*, so a function edited into a
violation without its signature line changing — the common case — tagged
`[pre-existing]`. It also matched by bare function name, so a violation in one file
could be "exempted" by an unrelated same-named function added elsewhere. It also relied
on a GNU/PCRE2-only grep extension BSD grep (macOS default) rejects with exit 2 and
empty stdout.

Compute the ranges the branch actually touched, per file, from `git diff --unified=0`
hunk headers, in Python rather than a shell regex extension. Run this once **for each
file in `$CHANGED_CODE`**, with `$FILE` bound to that file's path:

```bash
git diff --unified=0 "$BASE_SHA"..HEAD -- "$FILE" | python3 -c '
import re, sys
for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", sys.stdin.read(), re.MULTILINE):
    start = int(m.group(1))
    count = int(m.group(2)) if m.group(2) is not None else 1
    end = start if count == 0 else start + count - 1
    print(start, end)
'
```

A `+N,0` hunk (pure deletion, no replacement lines) still reports `(N, N)` — a single
touch point — rather than being skipped for adding zero lines. Deleting lines from the
middle of a function changes it even when nothing is added back.

A function is **touched** if `[start_line, end_line]` overlaps any changed range in its
file: `a <= fn_end and fn_start <= b`. Tag `[new in this PR]` if touched, `[pre-existing]`
if not — same tag vocabulary as before, now derived correctly.

**Known limitations, stated rather than silently absorbed:**

- **Renamed files.** `git diff --unified=0 "$BASE_SHA"..HEAD -- "$FILE"`, scoped to a
  single pathspec, cannot pair a rename with its content change even with `-M` — git
  needs both sides of the rename in the same invocation to detect it. A renamed file
  shows as a single whole-file addition, so every function in it reports touched. This
  fails in the *safe* direction — over-blocking, not under-exempting — but it means
  `cc_exempt_pre_existing` is silently inert for any file this branch renamed, with no
  functions in it benefiting from the exemption until a later branch edits it again.
- **Decorator- or annotation-only edits.** `start_line` is the `def`/`func` line itself;
  a decorator above it (`@lru_cache(...)`, `@retry(...)`) is not part of the reported
  range. A hunk that only changes a decorator's arguments falls outside `[start_line,
  end_line]` and the function reads as untouched — the wrong direction, since the
  decorator can change real behavior (caching, retries, permissions) without lizard's CC
  number moving at all.

## Pre-existing-code exemption (opt-in)

Read `cc_exempt_pre_existing` from `.project-conf.toml` `[autonomous]` section
(default: **false**). Off by default — every project behaves exactly as described
above until it opts in.

**When `false`:** every 🔴 violation blocks, touched or not. `[new in this PR]` /
`[pre-existing]` are informational tags only.

**When `true`:** only `[new in this PR]` (touched) 🔴 violations block. A
`[pre-existing]` 🔴 violation is **exempted** from the hard-gate — but it is still
printed, under its own heading, with its CC and a note that this branch did not touch
it. The exemption changes what blocks, not what is visible: making complexity invisible
would defeat the gate's purpose, and a function exempted today stops being exempt the
moment a later branch edits it.

## CC report format

```
CC gate: N 🔴 violation(s), M 🟡 elevated (threshold = T)

  🔴 At or over threshold (CC >= T):
    backup_scheduler.py:42  run_backup          CC=34  grade=E  [new in this PR]
    ...

  🟡 Elevated (W <= CC < T, where W = cc_warn_threshold):
    backup_scheduler.py:88  _schedule_next      CC=18  grade=C  [pre-existing]
    ...
```

**With `cc_exempt_pre_existing = true` and at least one violation exempted**, the
headline gains a `K exempt` clause and the report gains its own section — both absent
otherwise, so a project that never opts in sees no trace of this feature in its report:

```
CC gate: N 🔴 violation(s), M 🟡 elevated, K exempt (threshold = T)

  ...

  ⚪ Exempt — pre-existing, not touched by this branch (cc_exempt_pre_existing = true):
    backup_scheduler.py:150  _parse_legacy_config  CC=14  grade=D
    ...
```

### Reducing a 🔴 violation

CC-specific, distinct from the review's dead-code/duplication/over-defensive-coding
criteria — these remedies are about the *shape* of a function's control flow, not general
code quality, so they live here rather than being folded into that pass. State them in
the report for every in-scope violation — the goal is a more linear path through the
function, not a smaller number for its own sake, so a function split arbitrarily to
dodge the threshold has not actually satisfied it:

- **Extract** repeated or independently-nameable fragments into their own functions.
- **Invert** nested conditionals into early-return guard clauses.
- **Lift** loop bodies into named helper functions.
- **Replace** a multi-branch dispatch with a lookup or dispatch table — not a
  `switch`/`case` restyling of the same branches (see the counting-mode note above:
  under this gate's counting, that produces no reduction).
- **Collapse** boolean-flag parameters that fork the function's body into separate
  functions, one per behavior.

## File NLOC check

Read `file_nloc_warn_threshold` from `.project-conf.toml` `[autonomous]` section (default: **400**). If the value is `0`, skip this check entirely with no output.

Parse `$CC_CSV` again with the same `COLS`, group by `filename`, and sum `nloc` for each
group. This gives the total non-comment lines per file across all functions lizard found
in that file.

For example (illustrative — implement as a model-side computation against the parsed rows):

```bash
echo "$CC_CSV" | python3 -c '
import collections, csv, sys
COLS = ["nloc","ccn","token_count","param_count","length",
        "long_name","filename","name","signature","start_line","end_line"]
threshold = int(sys.argv[1])
totals, counts = collections.Counter(), collections.Counter()
for r in csv.reader(sys.stdin):
    if len(r) != len(COLS):
        continue
    row = dict(zip(COLS, r))
    totals[row["filename"]] += int(row["nloc"])
    counts[row["filename"]] += 1
for path, total in totals.items():
    if total > threshold:
        print(f"{path}  NLOC={total}  (lizard sum, {counts[path]} functions)")
' "$FILE_NLOC_THRESHOLD"
```

Emit output only when at least one file exceeds the threshold:

```
File NLOC: 2 file(s) over threshold (warn = 400)

  🟡 skills/pr/references/pr-cc-gate.md    NLOC=423  (lizard sum, 4 functions)
  🟡 skills/plan/references/plan-red-tests.md  NLOC=412  (lizard sum, 3 functions)
```

Rules:
- **Completely silent** when no files exceed the threshold or when `file_nloc_warn_threshold = 0`.
- **🟡 only** — never a 🔴 hard stop, never blocks the PR.
- If any NLOC warnings exist, also add a line to the PR body's "Complexity notes" section listing the over-threshold files and their NLOC totals.
- **Opt-out pragma:** any file whose content contains the string `SLOPSTOP PRAGMA no-line-count-limit` (in any comment syntax) is excluded from this check entirely — do not emit a 🟡 for it regardless of its NLOC total.

## CC-gate bypass — benchmark override record

When `on_test_failure = "benchmark-continue"` causes the CC gate to be bypassed, post a comment on the **PR** with the header `## slopstop signals` followed by a fenced `json` block:

````
## slopstop signals

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
````

`tools/metrics/signals.py` parses every `## slopstop signals` comment on the ticket and
its PR and merges them newest-wins per key, so each bypass (from this gate or the
test-failure gate in the same run) posts its own comment rather than appending to a
shared file.

**Why 🟡 only:** a brand-new function won't have callers yet by definition — it was just written. This is a smell signal, not a hard gate. Dismiss if the function is intentionally internal or not yet wired up. A reviewer can cross-check using `/slopstop:know <name>`.

**Limitation:** functions added in this PR are not yet indexed in the code graph, so they will never appear in `get_dead_candidates` results until after the next indexing run. This sub-check is useful only when `NEW_PY_DEF_NAMES` includes functions that already existed in the repo (e.g., a refactored `def` whose signature line appears in the diff as a `+` line). For PRs that only introduce brand-new functions, this sub-check will always produce no hits.
