#!/usr/bin/env bash
# vacuity.sh — run each new test, by node-id, against a scratch worktree at the base commit.
#
# Usage (run from inside the branch's checkout):
#   vacuity.sh --base <sha> --frozen <sha> [--tip <sha|HEAD>] \
#              --node-ids <id> [<id>...]     (a Go id may be 'pkg -run TestX', quoted as one) \
#              --test-files <path> [<path>...] \
#              --command '<runner minus the node-id>' \
#              [--stubs <path> [<path>...]]
#
# Verdicts:
#   VACUITY CLEAN
#   VACUITY VACUOUS: N
#   VACUITY BLOCKED: <reason>
#
# Per node-id, on exit status alone (never on output text):
#   exit 0  -> vacuous            passes against pre-branch code; pins nothing
#   exit 1  -> meaningful         reached its assertion and failed there
#   other   -> could-not-determine collection/import/build error — never a pass, never red
#
# Stubs are reconstructed at --frozen, never at HEAD: at HEAD a stub holds the finished
# implementation and every test reads vacuous. That one line is the whole correctness of
# the mechanism — skills/vacuity-check/SKILL.md Step 3 is the one definition.
#
# The `regression`-tagged exemption is the CALLER's: omit those node-ids before calling.
# `SLOPSTOP PRAGMA coverage-backfill` comments are inert (BILL-468); counted, never honoured.

set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_lib.sh
. "$HERE/_lib.sh"

BASE= FROZEN= TIP=HEAD COMMAND=
NODE_IDS=() TEST_FILES=() STUBS=()
STUBS_GIVEN=false
while [ $# -gt 0 ]; do
  case "$1" in
    --base)       BASE=${2:-}; shift 2 ;;
    --frozen)     FROZEN=${2:-}; shift 2 ;;
    --tip)        TIP=${2:-}; shift 2 ;;
    --command)    COMMAND=${2:-}; shift 2 ;;
    --node-ids)   shift; collect_multi NODE_IDS "$@"; shift "$COLLECTED" ;;
    --test-files) shift; collect_multi TEST_FILES "$@"; shift "$COLLECTED" ;;
    --stubs)      STUBS_GIVEN=true; shift; collect_multi STUBS "$@"; shift "$COLLECTED" ;;
    *) blocked VACUITY "unknown argument $1" ;;
  esac
done

require_sha VACUITY --base "$BASE"
require_sha VACUITY --frozen "$FROZEN"
TIP=$(git rev-parse --verify --quiet "${TIP}^{commit}") || blocked VACUITY "--tip does not resolve"
[ ${#NODE_IDS[@]} -gt 0 ] || blocked VACUITY "empty node-id list — an empty list is BLOCKED, never CLEAN"
[ ${#TEST_FILES[@]} -gt 0 ] || blocked VACUITY "no --test-files given"
[ -n "$COMMAND" ] || blocked VACUITY "no --command given — never auto-detect a project's test runner"

# A path in both lists is a malformed baseline — they are disjoint by construction.
for s in "${STUBS[@]:-}"; do
  [ -n "$s" ] || continue
  for t in "${TEST_FILES[@]}"; do
    [ "$s" = "$t" ] && blocked VACUITY "$s is listed as both a test file and a stub"
  done
done

scratch_worktree "$BASE" || blocked VACUITY "could not create a scratch worktree at $BASE"
WT=$SCRATCH_WT

# Tests, and any conftest.py beside them, at TIP content.
pragma_count=0
for f in "${TEST_FILES[@]}"; do
  git cat-file -e "$TIP:$f" 2>/dev/null || blocked VACUITY "test file $f does not exist at $TIP"
  mkdir -p "$WT/$(dirname "$f")"
  git show "$TIP:$f" > "$WT/$f"
  c=$(grep -c 'SLOPSTOP PRAGMA coverage-backfill' "$WT/$f" || true)
  pragma_count=$((pragma_count + c))
done
for d in $(for f in "${TEST_FILES[@]}"; do dirname "$f"; done | sort -u); do
  git cat-file -e "$TIP:$d/conftest.py" 2>/dev/null && git show "$TIP:$d/conftest.py" > "$WT/$d/conftest.py"
done

# Stubs at FROZEN — never HEAD, never the index.
stub_note="tests-only — no --stubs given"
if $STUBS_GIVEN; then
  stub_note="stubbed (${#STUBS[@]} files at $FROZEN)"
  for s in "${STUBS[@]:-}"; do
    [ -n "$s" ] || continue
    git cat-file -e "$FROZEN:$s" 2>/dev/null || blocked VACUITY "stub $s does not exist at --frozen $FROZEN"
    mkdir -p "$WT/$(dirname "$s")"
    git show "$FROZEN:$s" > "$WT/$s"
  done
fi

vacuous=() meaningful=() undetermined=() outputs=()
for id in "${NODE_IDS[@]}"; do
  # A node-id may be one token (`tests/test_x.py::test_y`) or red-tests' Go form
  # `pkg -run TestX` — several words. Word-split it so `go test` sees each as an
  # argument; a single-token id is unchanged. (SOP-589: the whole string as one
  # argument gave three false could-not-determine results.)
  # shellcheck disable=SC2086
  out=$(cd "$WT" && sh -c "$COMMAND \"\$@\"" _ $id 2>&1)
  status=$?
  last=$(printf '%s\n' "$out" | grep -vE '^\s*$|^(FAIL|ok)(\s|$)|^exit status [0-9]+$' | tail -1 | cut -c1-160)
  outputs+=("$out")
  # `go test` exits 1 for a build or setup failure exactly as for a failed assertion —
  # the one place status alone inverts the verdict. Those two literal markers are the
  # narrowest text check that keeps a Go compile error out of `meaningful`.
  if [ $status -eq 1 ] && printf '%s' "$out" | grep -qE '\[(build|setup) failed\]'; then
    status=97
  fi
  case $status in
    0) vacuous+=("$id   exit 0") ;;
    1) meaningful+=("$id   exit 1: $last") ;;
    97) undetermined+=("$id   exit 1 [build/setup failed]: $last") ;;
    *) undetermined+=("$id   exit $status: $last") ;;
  esac
done

ran=$(( ${#vacuous[@]} + ${#meaningful[@]} + ${#undetermined[@]} ))
[ $ran -gt 0 ] || blocked VACUITY "no node-id ran"

# Runner-failure guard. A wrapper that cannot start (missing env, no DB, bad flag) exits
# 1 for every node-id with byte-identical output, and exit 1 reads as `meaningful` — a
# clean verdict from a runner that never ran a test. Real failures differ per test (the
# test name is in the output). Two or more ids, all non-zero, all identical -> BLOCKED.
if [ $ran -ge 2 ] && [ ${#vacuous[@]} -eq 0 ]; then
  same=true
  for o in "${outputs[@]}"; do [ "$o" = "${outputs[0]}" ] || same=false; done
  if $same; then
    blocked VACUITY "every node-id failed with identical output — the runner did not run a test: $(printf '%s\n' "${outputs[0]}" | grep -v '^\s*$' | head -1 | cut -c1-200)"
  fi
fi

if [ ${#vacuous[@]} -gt 0 ]; then
  printf 'VACUITY VACUOUS: %d\n' "${#vacuous[@]}"; rc=$EXIT_FINDING
else
  printf 'VACUITY CLEAN\n'; rc=$EXIT_CLEAN
fi
printf 'Base: %s   Tip: %s   Worktree: %s  (removed: yes)\n' "$BASE" "$TIP" "$stub_note"
printf 'Inert backfill comments seen: %d   (honoured: never — the marker was deleted in BILL-468)\n\n' "$pragma_count"
[ ${#vacuous[@]} -gt 0 ]      && { printf '  🔴 vacuous — passes against base, pins nothing:\n';     printf '    %s\n' "${vacuous[@]}"; }
[ ${#meaningful[@]} -gt 0 ]   && { printf '  ✅ meaningful — fails at its assertion against base:\n'; printf '    %s\n' "${meaningful[@]}"; }
[ ${#undetermined[@]} -gt 0 ] && { printf '  ⚪ could-not-determine:\n';                             printf '    %s\n' "${undetermined[@]}"; }
exit $rc
