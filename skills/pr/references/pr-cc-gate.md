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
# Parses the rows once. Both the CC classification and the File NLOC check below
# read from `rows` — there is one column list in this file, and this is it.
echo "$CC_CSV" | python3 -c '
import csv, sys
COLS = ["nloc","ccn","token_count","param_count","length",
        "long_name","filename","name","signature","start_line","end_line"]
rows = [dict(zip(COLS, r)) for r in csv.reader(sys.stdin) if len(r) == len(COLS)]
'
```

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
but it records `"step": "pre_pr_cc_gate_tool_missing"` in `pipeline.json` and appears in the
Step 8 summary. Otherwise a run where lizard never installed is, from the outside, identical
to a clean gate; the pip cascade above ends in `|| true` with its errors discarded, so a
missing tool would be the cheapest untraceable way to disable this gate.

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

  🔴 At or over threshold (CC >= T):
    backup_scheduler.py:42  run_backup          CC=34  grade=E  [new in this PR]
    ...

  🟡 Elevated (W <= CC < T, where W = cc_warn_threshold):
    backup_scheduler.py:88  _schedule_next      CC=18  grade=C  [pre-existing]
    ...
```

## File NLOC check

Read `file_nloc_warn_threshold` from `.project-conf.toml` `[autonomous]` section (default: **400**). If the value is `0`, skip this check entirely with no output.

Using the rows parsed above, group by `filename` and sum `nloc` for each group. This gives the total non-comment lines per file across all functions lizard found in that file.

For example (illustrative — implement as a model-side computation against the parsed rows):

```python
# Continues from `rows` above — no second parse, and no positional indices.
totals, counts = collections.Counter(), collections.Counter()
for row in rows:
    totals[row["filename"]] += int(row["nloc"])
    counts[row["filename"]] += 1
for path, total in totals.items():
    if total > FILE_NLOC_THRESHOLD:
        print(f"{path}  NLOC={total}  (lizard sum, {counts[path]} functions)")
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

**Why 🟡 only:** a brand-new function won't have callers yet by definition — it was just written. This is a smell signal, not a hard gate. Dismiss if the function is intentionally internal or not yet wired up. A reviewer can cross-check using `/slopstop:know <name>`.

**Limitation:** functions added in this PR are not yet indexed in the code graph, so they will never appear in `get_dead_candidates` results until after the next indexing run. This sub-check is useful only when `NEW_PY_DEF_NAMES` includes functions that already existed in the repo (e.g., a refactored `def` whose signature line appears in the diff as a `+` line). For PRs that only introduce brand-new functions, this sub-check will always produce no hits.
