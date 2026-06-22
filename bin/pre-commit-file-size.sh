#!/usr/bin/env bash
# pre-commit-file-size.sh — Git pre-commit hook: warn or refuse files that
# exceed line-count thresholds.
#
# Usage (install as or call from .git/hooks/pre-commit):
#   bin/pre-commit-file-size.sh
#
# Thresholds (total lines from wc -l, including comments and blanks):
#   > 1500 lines  →  REFUSED: exit 1 (blocks commit)
#   > 1000 lines  →  WARNING: exit 0 (advisory only)
#   ≤ 1000 lines  →  silent:  exit 0

set -uo pipefail

EXIT=0

while IFS= read -r f; do
    # Skip deletions and files that don't exist on disk.
    test -f "$f" || continue

    COUNT=$(wc -l < "$f")

    # Under both thresholds — nothing to report.
    (( COUNT > 1000 )) || continue

    # Skip files that have opted out via the slopstop no-count pragma.
    grep -q 'SLOPSTOP PRAGMA no-line-count-limit' "$f" 2>/dev/null && continue

    if (( COUNT > 1500 )); then
        echo "REFUSED: $f has $COUNT lines (limit: 1500) — split it before committing"
        EXIT=1
    else
        echo "WARNING: $f has $COUNT lines (soft limit: 1000) — consider splitting"
    fi
done < <(git diff --cached --name-only)

exit "$EXIT"
