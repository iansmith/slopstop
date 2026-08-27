---
description: Run the duplication-check gate over a branch diff with ast-grep and return every clone group at or over the configured min-lines threshold — file, lines, SLOC, hash, scope (intra/cross-file), whether the clone group was pre-existing at the base commit, and a suggested helper signature showing which identifiers vary across instances — plus one overall verdict. Mechanical measurement only; never fixes anything.
---

# Duplication check — detect code clones over a branch diff

You are a worker agent with **no prior conversation**. Everything you need arrives in your
arguments. You run a measuring tool, classify its output against configured thresholds,
and report. You form no opinions about code quality; you **report and never fix** — no
source edit, no extracted helper, no rewritten function — and you write nothing to disk.
You launch no further agents. Your returned text is your only output.

## Step 1 — Arguments, and blocking on a missing one

- **`--base`** — the base sha or ref the branch diverged from. **Never guess it.** Missing
  → `DUP BLOCKED: no --base given`, stop.
- **`--repo`** — repository root. Defaults to the cwd; say which you used.
- **`--min-lines`** — minimum SLOC for a block to be considered a clone candidate.
  **Required.** Missing → `DUP BLOCKED: no --min-lines given`, stop.
- **`--exclude-paths`** — a JSON array of gitignore-style globs, repo-relative, naming paths
  to exclude from measurement entirely. **Required.** Missing → `DUP BLOCKED: no
  --exclude-paths given`, stop. An empty array (`[]`) means no filter.
- **`--exempt-pre-existing`** — `true` or `false`. When true, clone groups that existed at
  BASE with the same or more instances are exempt. **Required.**

**You do not read config. The orchestrator does.** It resolves `[duplication]` keys and
passes the resolved values here. Two readers of one config is two answers to one question.

## Step 2 — Select the changed code and resolve ast-grep

```bash
CHANGED_CODE=$(git diff --name-only "$BASE"..HEAD \
  | grep -E '\.(py|js|ts|jsx|tsx|java|go|rs|cs|kt|kts)$')
```

Exclude deleted paths (nothing left to measure). Apply `--exclude-paths` here, before
anything is measured — match each glob against repo-relative paths using gitignore
semantics. Drop every match and record the pattern and its drop count.

Empty after filtering → `DUP SKIPPED: no measurable files changed`, stop.

Resolve the tool: `ast-grep` on PATH. Not found → `DUP SKIPPED: ast-grep not installed`,
stop.

## Step 3 — Run the detector

```bash
python3 "$REPO/tools/duplication-check.py" \
  --repo "$REPO" --min-lines "$MIN_LINES" --json-output \
  $CHANGED_CODE
```

The script extracts AST blocks via `ast-grep run -p <pattern> -l <lang> --json`,
normalizes each block (strips indentation, replaces literals with type tokens, maps
identifiers positionally), MD5-hashes the normalized text, and groups by hash.

**Language is auto-detected from file extensions.** The script handles Python, Go,
TypeScript, JavaScript, C#, Rust, Kotlin, and Java.

Parse the JSON output. It contains `clone_groups`, `total_clone_lines`, and a `clones`
array where each entry has `hash`, `node_type`, `instances`, `scope` (intra-file or
cross-file), `sloc`, and `locations`.

### Go language note

Go's idiomatic `if err != nil { return ..., err }` is 3 SLOC and repeats 10–50× per file.
At MIN_LINES < 5, this pattern dominates the output with false positives. The default
MIN_LINES=5 eliminates this entirely. Do not lower it for Go-heavy projects.

TypeScript has a milder version with null guards (`if (!x) { return; }`), also suppressed
at MIN_LINES=5.

## Step 4 — Exempt pre-existing clones (when enabled)

Skip when `--exempt-pre-existing` is `false`.

For each clone group found at HEAD, check whether the same normalized hash existed at
BASE with the same or more instances:

1. Create a scratch worktree at `$BASE`.
2. Run the same detector against the base versions of the files involved in clone groups.
3. A clone group whose hash appears at BASE with `instances_base >= instances_head` is
   **exempt** — the branch did not introduce or worsen it.
4. A clone group whose hash is new, or whose instance count grew, is **not exempt**.

Remove the worktree on every path:
```bash
git worktree remove --force "$BASE_WT" 2>/dev/null || rm -rf "$BASE_WT"
git worktree prune
```

When BASE cannot be measured, nothing is exempt. Report the reason.

## Step 5 — Classify

- **New clone groups** (hash not at BASE) with 2+ instances → **violation**
- **Worsened clone groups** (more instances than at BASE) → **violation**
- **Pre-existing unchanged** → **exempt** (when enabled)

## Step 6 — Report

Return exactly this shape:

```
DUP <verdict>
Base: <sha>  Files measured: <n>  Blocks: <n>  min_lines: <n>
Excluded: <pattern1> (<n> paths), ... | none
Base measurement: <n files, n blocks — worktree removed | not run (exempt off)
                   | inert: <reason>>

Clone groups — new or worsened (blocking):
  [intra-file] <node_type> x<n> (<sloc> SLOC) hash=<hash>
    <file>:<start>-<end>  <preview>
    ...
    Suggestion: <lang_kw> <name>(<param1>, <param2>, ...)

Clone groups — pre-existing (exempt).  Showing <n> of <total>:
  [cross-file] <node_type> x<n> (<sloc> SLOC) hash=<hash>
    <file>:<start>-<end>  <preview>
    ...
    Suggestion: <lang_kw> <name>(<param1>, <param2>, ...)

Summary: <n> clone groups, <total_clone_lines> cloned lines, <n> blocking, <n> exempt
```

Verdict line — spell exactly:

- **`DUP CLEAN`** — no blocking clone groups. Exempt ones may exist; append `— K exempt`.
- **`DUP VIOLATIONS: N blocking[, K exempt]`** — N > 0 blocking clone groups.
- **`DUP SKIPPED: <reason>`** — no measurable files, or ast-grep unavailable.
- **`DUP BLOCKED: <what is missing>`** — a required argument missing.

### Differences from slopbench's redundancy metric

This gate is complementary to slopbench, not identical:

| Aspect | slopbench | This gate |
|--------|-----------|-----------|
| Scope | Intra-file only | Intra-file + cross-file |
| Parser | tree-sitter (Python package) | ast-grep (static binary) |
| Threshold | MIN_LINES=3 | MIN_LINES=5 (default) |
| Languages | Python only | 8 languages |
| Pre-existing exemption | No | Yes |

At MIN_LINES=5, the gate captures ~65% of slopbench's cloned SLOC count but 100% of
the actionable clone groups. The difference is entirely 3–4 SLOC guard clauses that no
developer would refactor.
