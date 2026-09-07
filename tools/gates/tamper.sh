#!/usr/bin/env bash
# tamper.sh — stage 8a as a script: the frozen-set tamper diff and the file-map check.
#
# Usage (run from inside the branch's checkout):
#   tamper.sh --frozen <sha|none> --tip <sha|HEAD> --base <sha> \
#             [--stubs <path> [<path>...]] \
#             [--refactor | --backfill | --prose-only] \
#             [--fork <sha> --file-map '<json-array>']
#
# Verdicts (first line; a second FILEMAP line follows when --file-map is given):
#   TAMPER CLEAN
#   TAMPER FAIL: <file>:<line> — <old> -> <new>
#   TAMPER FAIL: <file> deleted|renamed
#   TAMPER FAIL: no Phase 0 baseline
#   TAMPER FAIL: <mode> ticket modified <test|production> file <path>
#   TAMPER BLOCKED: <guard failure>
#   FILEMAP CLEAN | FILEMAP FAIL: <paths>
#
# The one definition of what these mean is skills/run/references/handoff-verification.md
# ("8a — The mechanical tamper diff", "8a — The file-map violation check"). This script is
# that prose made executable; it adds no rule.
#
# The frozen set is the Phase 0 commit's file list MINUS the stub files red-tests named
# (`--stubs`). Stubs are not frozen (stages-phase0.md): the implementation must replace
# the sentinel, so a stub inside the set would fail every normal ticket. The prose in
# handoff-verification.md said "the commit, not a glob" without the subtraction; the
# inline orchestrator was excluding stubs silently. Found by the first synthetic run.
#
# `--frozen none` is accepted ONLY with --refactor or --prose-only — the two literal
# stage-4 outcomes that legitimately have no Phase 0 commit. Anything else with no
# frozen sha is `TAMPER FAIL: no Phase 0 baseline`, never CLEAN.

set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_lib.sh
. "$HERE/_lib.sh"

FROZEN= TIP= BASE= FORK= FILE_MAP= MODE=normal
STUBS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --stubs)      shift; collect_multi STUBS "$@"; shift "$COLLECTED" ;;
    --frozen)     FROZEN=${2:-}; shift 2 ;;
    --tip)        TIP=${2:-}; shift 2 ;;
    --base)       BASE=${2:-}; shift 2 ;;
    --fork)       FORK=${2:-}; shift 2 ;;
    --file-map)   FILE_MAP=${2:-}; shift 2 ;;
    --refactor)   MODE=refactor; shift ;;
    --backfill)   MODE=backfill; shift ;;
    --prose-only) MODE=prose-only; shift ;;
    *) blocked TAMPER "unknown argument $1" ;;
  esac
done

require_sha TAMPER --base "$BASE"
[ -n "$TIP" ] || blocked TAMPER "no --tip given"
TIP=$(git rev-parse --verify --quiet "${TIP}^{commit}") || blocked TAMPER "--tip does not resolve"
git merge-base --is-ancestor "$BASE" "$TIP" || blocked TAMPER "--base is not an ancestor of --tip"

rc=$EXIT_CLEAN
say() { printf '%s\n' "$*"; }

# ---------------------------------------------------------------- tamper diff
if [ -z "$FROZEN" ]; then
  blocked TAMPER "no --frozen given (pass the captured sha, or 'none' with --refactor/--prose-only)"
fi

if [ "$FROZEN" = none ]; then
  case "$MODE" in
    refactor|prose-only) ;;
    *) say "TAMPER FAIL: no Phase 0 baseline"; rc=$EXIT_FINDING ;;
  esac
else
  FROZEN=$(git rev-parse --verify --quiet "${FROZEN}^{commit}") \
    || blocked TAMPER "--frozen does not resolve to a commit"
  git merge-base --is-ancestor "$FROZEN" "$TIP" || blocked TAMPER "--frozen is not an ancestor of --tip"
  git merge-base --is-ancestor "$BASE" "$FROZEN" || blocked TAMPER "--base is not an ancestor of --frozen"

  FROZEN_FILES=()
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    is_stub=false
    for s in "${STUBS[@]:-}"; do [ "$s" = "$f" ] && is_stub=true; done
    $is_stub || FROZEN_FILES+=("$f")
  done < <(git show --name-only --format= "$FROZEN")
  [ ${#FROZEN_FILES[@]} -gt 0 ] || blocked TAMPER "frozen set is empty — $FROZEN touches no non-stub files"

  # deleted or renamed frozen file
  while IFS=$'\t' read -r status path rest; do
    [ -n "$status" ] || continue
    case "$status" in
      D*) say "TAMPER FAIL: $path deleted"; rc=$EXIT_FINDING ;;
      R*) say "TAMPER FAIL: $path renamed to ${rest:-?}"; rc=$EXIT_FINDING ;;
    esac
  done < <(git diff --name-status -M "$FROZEN" "$TIP" -- "${FROZEN_FILES[@]}")

  # any removed line in a frozen file
  removed=$(git diff -w --ignore-blank-lines "$FROZEN" "$TIP" -- "${FROZEN_FILES[@]}" \
    | python3 -c '
import re, sys
cur = None; old_line = 0; out = []
for raw in sys.stdin.read().split("\n"):
    if raw.startswith("--- "):
        continue
    if raw.startswith("+++ "):
        cur = raw[4:].removeprefix("b/"); continue
    m = re.match(r"^@@ -(\d+)", raw)
    if m:
        old_line = int(m.group(1)); continue
    if raw.startswith("-"):
        out.append(f"{cur}:{old_line} — {raw[1:].strip()}"); old_line += 1
    elif raw.startswith("+"):
        pass
    elif raw.startswith(" ") or raw == "":
        old_line += 1
print("\n".join(out))
')
  if [ -n "$removed" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && say "TAMPER FAIL: $line"
    done <<< "$removed"
    rc=$EXIT_FINDING
  fi
fi

# ---------------------------------------------------------------- invariant-mode fences
# refactor: no test file may change; backfill: no production file may change.
# Compared against the branch's own changes (the $OWN rule): --fork when given, else --base.
if [ "$MODE" = refactor ] || [ "$MODE" = backfill ]; then
  from=${FORK:-$BASE}
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    if [ "$MODE" = refactor ] && is_test_path "$p"; then
      say "TAMPER FAIL: refactor ticket modified test file $p"; rc=$EXIT_FINDING
    elif [ "$MODE" = backfill ] && ! is_test_path "$p"; then
      say "TAMPER FAIL: backfill ticket modified production file $p"; rc=$EXIT_FINDING
    fi
  done < <(git diff --name-only "$from" "$TIP")
fi

[ $rc -eq $EXIT_CLEAN ] && say "TAMPER CLEAN"

# ---------------------------------------------------------------- file map
if [ -n "$FILE_MAP" ]; then
  require_json_array TAMPER --file-map "$FILE_MAP"
  [ -n "$FORK" ] || blocked TAMPER "--file-map given without --fork"
  FORK=$(git rev-parse --verify --quiet "${FORK}^{commit}") || blocked TAMPER "--fork does not resolve"
  # Two commands, unioned: committed + tracked-uncommitted, and untracked new files.
  outside=$( { git diff --name-only "$FORK"; git ls-files --others --exclude-standard; } \
    | sort -u | python3 -c '
import json, sys
fmap = json.loads(sys.argv[1])
def covered(p):
    for e in fmap:
        e = e.rstrip("/")
        if p == e or p.startswith(e + "/"):
            return True
    return False
bad = [p for p in sys.stdin.read().split("\n") if p and not covered(p)]
print("\n".join(bad))
' "$FILE_MAP")
  if [ -n "$outside" ]; then
    say "FILEMAP FAIL: $(printf '%s' "$outside" | tr '\n' ' ')"
    rc=$EXIT_FINDING
  else
    say "FILEMAP CLEAN"
  fi
fi

exit $rc
