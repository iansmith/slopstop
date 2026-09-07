#!/usr/bin/env bash
# Shared helpers for the slopstop gate scripts. Sourced, never run.
#
# Contract every gate script honours (skills/run/references/stages-lean.md):
#   - verdict text on stdout, first line is the verdict the orchestrator branches on
#   - exit 0 = CLEAN / SKIPPED, 1 = a blocking finding, 2 = BLOCKED or ERROR
#   - no config reading: every threshold, path and sha arrives as an argument
#   - "something measured zero and zero read as fine" is the failure mode; every
#     empty input is asserted, never defaulted

set -u

EXIT_CLEAN=0
EXIT_FINDING=1
EXIT_BLOCKED=2

# blocked <PREFIX> <reason>  -> prints "<PREFIX> BLOCKED: <reason>" and exits 2
blocked() { printf '%s BLOCKED: %s\n' "$1" "$2"; exit $EXIT_BLOCKED; }

# require_sha <PREFIX> <name> <value> -> asserts the value resolves to a commit
require_sha() {
  local prefix=$1 name=$2 val=${3:-}
  [ -n "$val" ] || blocked "$prefix" "no $name given"
  git rev-parse --verify --quiet "${val}^{commit}" >/dev/null 2>&1 \
    || blocked "$prefix" "$name '$val' does not resolve to a commit"
}

# require_int <PREFIX> <name> <value>
require_int() {
  local prefix=$1 name=$2 val=${3:-}
  [ -n "$val" ] || blocked "$prefix" "no $name given"
  [[ "$val" =~ ^[0-9]+$ ]] || blocked "$prefix" "$name is '$val', not an integer"
}

# require_bool <PREFIX> <name> <value>
require_bool() {
  local prefix=$1 name=$2 val=${3:-}
  [ -n "$val" ] || blocked "$prefix" "no $name given"
  [ "$val" = true ] || [ "$val" = false ] || blocked "$prefix" "$name is '$val', not true|false"
}

# require_json_array <PREFIX> <name> <value>
require_json_array() {
  local prefix=$1 name=$2 val=${3:-}
  [ -n "$val" ] || blocked "$prefix" "no $name given"
  python3 -c 'import json,sys; v=json.loads(sys.argv[1]); sys.exit(0 if isinstance(v,list) else 1)' "$val" 2>/dev/null \
    || blocked "$prefix" "$name is not a JSON array: $val"
}

# collect_multi <arrayname> <remaining args...>
#   Consumes values up to the next `--flag` into the named array and sets COLLECTED to
#   the count consumed so the caller can `shift "$COLLECTED"`. Sets a variable rather
#   than echoing the count: inside `$(...)` the array append lands in a subshell.
collect_multi() {
  local __name=$1; shift
  COLLECTED=0
  while [ $# -gt 0 ] && [[ "$1" != --* ]]; do
    eval "$__name+=(\"\$1\")"
    shift; COLLECTED=$((COLLECTED+1))
  done
}

# filter_excluded <json-array-of-globs> <paths...>
#   Prints the paths that match NO glob, then a final line "EXCLUDED <pattern> <count>"
#   per pattern on stderr-free stdout tail (caller splits). gitignore semantics: fnmatch
#   with pathname, trailing /** matches the subtree.
filter_excluded() {
  local globs=$1; shift
  printf '%s\n' "$@" | python3 -c '
import fnmatch, json, sys
globs = json.loads(sys.argv[1])
paths = [p for p in sys.stdin.read().split("\n") if p]
counts = {g: 0 for g in globs}
kept = []
def match(p, g):
    if g.endswith("/**"):
        d = g[:-3]
        return p == d or p.startswith(d + "/")
    return fnmatch.fnmatchcase(p, g)
for p in paths:
    hit = [g for g in globs if match(p, g)]
    if hit:
        counts[hit[0]] += 1
    else:
        kept.append(p)
for p in kept: print(p)
print("--EXCLUDED--")
for g in globs: print(f"{g}\t{counts[g]}")
' "$globs"
}

# is_test_path <path> -> 0 when the path is test material.
# One expression, the same one :run's invariant-mode section uses (SKILL.md, "$OWN").
is_test_path() {
  printf '%s\n' "$1" | grep -qE '(^|/)(tests?|spec|testdata|__tests__)/|_test\.|\.test\.|_spec\.|conftest\.py$'
}

# scratch_worktree <sha> -> sets SCRATCH_WT to the path; registers cleanup on EXIT.
#   Sets a variable rather than printing: called inside `$(...)` the registration would
#   happen in a subshell and the EXIT trap would see an empty list (found on the first
#   real run — four worktrees leaked into sophie).
_GATE_REGISTRY=$(mktemp -t slopstop-gate-registry)
scratch_worktree() {
  local sha=$1 wt
  SCRATCH_WT=
  wt=$(mktemp -d -t slopstop-gate) || return 1
  rmdir "$wt"
  git worktree add -q --detach "$wt" "$sha" >/dev/null 2>&1 || return 1
  printf '%s\n' "$wt" >> "$_GATE_REGISTRY"
  SCRATCH_WT=$wt
}
_gate_cleanup() {
  local wt
  while IFS= read -r wt; do
    [ -n "$wt" ] || continue
    git worktree remove --force "$wt" >/dev/null 2>&1 || rm -rf "$wt"
  done < "$_GATE_REGISTRY"
  [ -s "$_GATE_REGISTRY" ] && git worktree prune >/dev/null 2>&1
  rm -f "$_GATE_REGISTRY"
  return 0
}
trap _gate_cleanup EXIT
