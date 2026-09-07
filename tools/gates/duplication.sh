#!/usr/bin/env bash
# duplication.sh — the clone-detection gate over a branch diff (ast-grep via duplication-check.py).
#
# Usage (run from inside the branch's checkout):
#   duplication.sh --base <sha> --repo <path> [--tip <sha|HEAD>] \
#                  --min-lines <n> --exempt-pre-existing <true|false> \
#                  --exclude-paths '<json-array>' [--detector <path>]
#
# Verdicts:
#   DUP CLEAN [— K exempt]
#   DUP VIOLATIONS: N blocking[, K exempt]
#   DUP SKIPPED: <reason>
#   DUP BLOCKED: <what is missing>
#
# The detector is tools/duplication-check.py, found beside this script's parent directory
# (`../duplication-check.py`) unless --detector overrides it. It stays as-is; this script
# replaces only the LLM wrapper that called it (skills/duplication-check/SKILL.md, the one
# definition of the rules below).

set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_lib.sh
. "$HERE/_lib.sh"

BASE= REPO= TIP=HEAD MIN_LINES= EXEMPT= EXCLUDE= DETECTOR="$HERE/../duplication-check.py"
while [ $# -gt 0 ]; do
  case "$1" in
    --base)                BASE=${2:-}; shift 2 ;;
    --repo)                REPO=${2:-}; shift 2 ;;
    --tip)                 TIP=${2:-}; shift 2 ;;
    --min-lines)           MIN_LINES=${2:-}; shift 2 ;;
    --exempt-pre-existing) EXEMPT=${2:-}; shift 2 ;;
    --exclude-paths)       EXCLUDE=${2:-}; shift 2 ;;
    --detector)            DETECTOR=${2:-}; shift 2 ;;
    *) blocked DUP "unknown argument $1" ;;
  esac
done

[ -n "$REPO" ] || blocked DUP "no --repo given"
cd "$REPO" 2>/dev/null || blocked DUP "--repo $REPO is not a directory"
require_sha DUP --base "$BASE"
TIP=$(git rev-parse --verify --quiet "${TIP}^{commit}") || blocked DUP "--tip does not resolve"
require_int DUP --min-lines "$MIN_LINES"
require_bool DUP --exempt-pre-existing "$EXEMPT"
require_json_array DUP --exclude-paths "$EXCLUDE"
[ -f "$DETECTOR" ] || blocked DUP "detector not found at $DETECTOR"

ALL_CHANGED=()
diff_out=$(git diff --name-only --diff-filter=d "$BASE" "$TIP") || blocked DUP "git diff $BASE..$TIP failed"
while IFS= read -r f; do
  [ -n "$f" ] && ALL_CHANGED+=("$f")
done < <(printf '%s\n' "$diff_out" | grep -E '\.(py|js|ts|jsx|tsx|java|go|rs|cs|kt|kts)$')
CHANGED=() EXCL_REPORT=()
if [ ${#ALL_CHANGED[@]} -gt 0 ]; then
  in_excl=false
  while IFS= read -r line; do
    if [ "$line" = "--EXCLUDED--" ]; then in_excl=true; continue; fi
    if $in_excl; then EXCL_REPORT+=("$line"); else CHANGED+=("$line"); fi
  done < <(filter_excluded "$EXCLUDE" "${ALL_CHANGED[@]}")
fi
if [ ${#CHANGED[@]} -eq 0 ]; then
  printf 'DUP SKIPPED: no measurable files changed\n'; exit $EXIT_CLEAN
fi
if ! command -v ast-grep >/dev/null 2>&1; then
  printf 'DUP SKIPPED: ast-grep not installed\n'; exit $EXIT_CLEAN
fi

HEAD_WT=$REPO
if [ "$TIP" != "$(git rev-parse HEAD)" ]; then
  scratch_worktree "$TIP" || blocked DUP "could not create a scratch worktree at $TIP"
  HEAD_WT=$SCRATCH_WT
fi
HEAD_JSON=$(mktemp -t dup-head)
( cd "$HEAD_WT" && python3 "$DETECTOR" --repo . --min-lines "$MIN_LINES" --json-output "${CHANGED[@]}" ) > "$HEAD_JSON" 2>/dev/null \
  || blocked DUP "detector failed at $TIP"

BASE_JSON=$(mktemp -t dup-base); : > "$BASE_JSON"; BASE_NOTE="not run (exempt off)"
if [ "$EXEMPT" = true ]; then
  BASE_FILES=()
  for f in "${CHANGED[@]}"; do git cat-file -e "$BASE:$f" 2>/dev/null && BASE_FILES+=("$f"); done
  if [ ${#BASE_FILES[@]} -eq 0 ]; then
    BASE_NOTE="0 files existed at BASE — every changed file is new"
  else
    scratch_worktree "$BASE"; BASE_WT=$SCRATCH_WT
    if [ -z "$BASE_WT" ]; then
      BASE_NOTE="inert: could not create a worktree at $BASE — nothing exempt"
    elif ( cd "$BASE_WT" && python3 "$DETECTOR" --repo . --min-lines "$MIN_LINES" --json-output "${BASE_FILES[@]}" ) > "$BASE_JSON" 2>/dev/null; then
      BASE_NOTE="${#BASE_FILES[@]} files measured at BASE — worktree removed"
    else
      BASE_NOTE="inert: detector failed at BASE — nothing exempt"; : > "$BASE_JSON"
    fi
  fi
fi

python3 - "$HEAD_JSON" "$BASE_JSON" "$BASE" "$TIP" "$MIN_LINES" "$BASE_NOTE" \
           "$(printf '%s\n' "${EXCL_REPORT[@]:-}")" <<'PY'
import json, sys
head_f, base_f, base_sha, tip_sha, min_lines, base_note, excl = sys.argv[1:8]
head = json.load(open(head_f))
base = {}
try:
    for c in json.load(open(base_f)).get("clones", []):
        base[c["hash"]] = c["instances"]
except (json.JSONDecodeError, OSError):
    pass
blocking, exempt = [], []
for c in head.get("clones", []):
    if c["instances"] < 2:
        continue
    if base_note.startswith("inert") or base_note.startswith("not run"):
        blocking.append(c)
    elif c["hash"] in base and base[c["hash"]] >= c["instances"]:
        exempt.append(c)
    else:
        blocking.append(c)
N, K = len(blocking), len(exempt)
v = "DUP CLEAN" if N == 0 else f"DUP VIOLATIONS: {N} blocking"
if K: v += (" — " if N == 0 else ", ") + f"{K} exempt"
print(v)
print(f"Base: {base_sha}  Tip: {tip_sha}  Files measured: {head.get('files_scanned')}  "
      f"Blocks: {head.get('blocks_extracted')}  min_lines: {min_lines}")
ex = [l for l in excl.split("\n") if l]
print("Excluded: " + (", ".join(f"{p} ({n} paths)" for p, n in (l.split("\t") for l in ex)) if ex else "none"))
print(f"Base measurement: {base_note}")
def show(c):
    print(f"  [{c['scope']}] {c['node_type']} x{c['instances']} ({c['sloc']} SLOC) hash={c['hash']}")
    for loc in c["locations"]:
        print(f"    {loc[0]}:{loc[1]}-{loc[2]}  {loc[3]}")
    if c.get("suggestion"): print(f"    Suggestion: {c['suggestion']}")
if blocking:
    print("\nClone groups — new or worsened (blocking):")
    for c in blocking: show(c)
if exempt:
    print(f"\nClone groups — pre-existing (exempt).  Showing {len(exempt)} of {len(exempt)}:")
    for c in exempt: show(c)
print(f"\nSummary: {head.get('clone_groups')} clone groups, {head.get('total_clone_lines')} cloned lines, {N} blocking, {K} exempt")
sys.exit(1 if N else 0)
PY
