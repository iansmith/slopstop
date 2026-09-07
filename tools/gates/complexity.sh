#!/usr/bin/env bash
# complexity.sh — the cyclomatic-complexity gate over a branch diff, with lizard.
#
# Usage (run from inside the branch's checkout):
#   complexity.sh --base <sha> --repo <path> [--tip <sha|HEAD>] \
#                 --warn <n> --reject <n> --exempt-pre-existing <true|false> \
#                 --file-nloc-warn <n> --exclude-paths '<json-array>'
#
# Verdicts:
#   CC CLEAN [— K exempt] [— T test-info]
#   CC VIOLATIONS: N 🔴, M 🟡[, K exempt][, T test-info]
#   CC INCONCLUSIVE: <files>
#   CC SKIPPED: <reason>
#   CC ERROR: exit <code> — <stderr>
#   CC BLOCKED: <what is missing>
#
# Exit: 0 for CLEAN/SKIPPED, 1 for VIOLATIONS (N > 0) or INCONCLUSIVE, 2 for ERROR/BLOCKED.
# 🟡-only (N = 0, M > 0) is reported as VIOLATIONS text but exits 0 — warn-level proceeds.
#
# One definition of every rule here: skills/complexity-check/SKILL.md. In particular:
#   - `--csv`, never `--json` (lizard has none; it exits 2 with empty stdout, which reads clean)
#   - quote-aware CSV parse, never `cut -d,` (signatures contain commas)
#   - both thresholds are inclusive lower bounds: CC >= reject is 🔴, warn <= CC < reject is 🟡
#   - test rows are informational, never in N (Step 4a)
#   - exemption = matched at BASE with CC_base >= CC_head, decided by a second lizard run
#     against a scratch worktree at BASE, pairing by (file,name,signature) -> (file,name) if
#     unique both sides -> byte-identical body -> unmatched (Step 5b)
#   - when BASE cannot be measured, nothing is exempt

set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_lib.sh
. "$HERE/_lib.sh"

BASE= REPO= TIP=HEAD WARN= REJECT= EXEMPT= NLOC_WARN= EXCLUDE=
while [ $# -gt 0 ]; do
  case "$1" in
    --base)                BASE=${2:-}; shift 2 ;;
    --repo)                REPO=${2:-}; shift 2 ;;
    --tip)                 TIP=${2:-}; shift 2 ;;
    --warn)                WARN=${2:-}; shift 2 ;;
    --reject)              REJECT=${2:-}; shift 2 ;;
    --exempt-pre-existing) EXEMPT=${2:-}; shift 2 ;;
    --file-nloc-warn)      NLOC_WARN=${2:-}; shift 2 ;;
    --exclude-paths)       EXCLUDE=${2:-}; shift 2 ;;
    *) blocked CC "unknown argument $1" ;;
  esac
done

[ -n "$REPO" ] || blocked CC "no --repo given"
cd "$REPO" 2>/dev/null || blocked CC "--repo $REPO is not a directory"
require_sha CC --base "$BASE"
TIP=$(git rev-parse --verify --quiet "${TIP}^{commit}") || blocked CC "--tip does not resolve"
require_int CC --warn "$WARN"
require_int CC --reject "$REJECT"
[ "$WARN" -lt "$REJECT" ] || blocked CC "--warn ($WARN) must be below --reject ($REJECT)"
require_bool CC --exempt-pre-existing "$EXEMPT"
require_int CC --file-nloc-warn "$NLOC_WARN"
require_json_array CC --exclude-paths "$EXCLUDE"

# ---------------------------------------------------------------- changed files
ALL_CHANGED=()
diff_out=$(git diff --name-only --diff-filter=d "$BASE" "$TIP") || blocked CC "git diff $BASE..$TIP failed"
while IFS= read -r f; do
  [ -n "$f" ] && ALL_CHANGED+=("$f")
done < <(printf '%s\n' "$diff_out" | grep -E '\.(py|js|ts|jsx|tsx|java|go|rs|c|cpp|cc|h|hpp|cs|kt|swift|scala|php|rb)$')
deleted=$(git diff --name-only --diff-filter=D "$BASE" "$TIP" | wc -l | tr -d ' ')

CHANGED=() EXCL_REPORT=()
if [ ${#ALL_CHANGED[@]} -gt 0 ]; then
  in_excl=false
  while IFS= read -r line; do
    if [ "$line" = "--EXCLUDED--" ]; then in_excl=true; continue; fi
    if $in_excl; then EXCL_REPORT+=("$line"); else CHANGED+=("$line"); fi
  done < <(filter_excluded "$EXCLUDE" "${ALL_CHANGED[@]}")
fi

if [ ${#CHANGED[@]} -eq 0 ]; then
  printf 'CC SKIPPED: no lizard-measurable files changed\n'
  exit $EXIT_CLEAN
fi

# ---------------------------------------------------------------- resolve lizard
CC_CMD=
for cand in "$REPO/.venv/bin/lizard" "$REPO/venv/bin/lizard"; do
  [ -x "$cand" ] && { CC_CMD=$cand; break; }
done
[ -z "$CC_CMD" ] && command -v lizard >/dev/null 2>&1 && CC_CMD=lizard
[ -z "$CC_CMD" ] && python3 -c 'import lizard' 2>/dev/null && CC_CMD="python3 -m lizard"
if [ -z "$CC_CMD" ]; then
  printf 'CC SKIPPED: lizard not installed (fix: pip install lizard)\n'
  exit $EXIT_CLEAN
fi

# ---------------------------------------------------------------- measure at TIP
HEAD_WT=$REPO
if [ "$TIP" != "$(git rev-parse HEAD)" ]; then
  scratch_worktree "$TIP" || blocked CC "could not create a scratch worktree at $TIP"
  HEAD_WT=$SCRATCH_WT
fi
HEAD_CSV=$(mktemp -t cc-head); HEAD_ERR=$(mktemp -t cc-head-err)
( cd "$HEAD_WT" && $CC_CMD --csv "${CHANGED[@]}" ) > "$HEAD_CSV" 2> "$HEAD_ERR"
HEAD_STATUS=$?
if [ $HEAD_STATUS -ne 0 ]; then
  printf 'CC ERROR: exit %d — %s\n' "$HEAD_STATUS" "$(tr '\n' ' ' < "$HEAD_ERR" | cut -c1-400)"
  exit $EXIT_BLOCKED
fi

# ---------------------------------------------------------------- measure at BASE
BASE_CSV=$(mktemp -t cc-base); BASE_NOTE="not run (exempt off)"; RENAMES=$(mktemp -t cc-renames)
: > "$BASE_CSV"; : > "$RENAMES"
if [ "$EXEMPT" = true ]; then
  git diff --find-renames --name-status --diff-filter=R "$BASE" "$TIP" \
    | awk -F'\t' '{print $3 "\t" $2}' > "$RENAMES"
  BASE_FILES=()
  for f in "${CHANGED[@]}"; do
    b=$(awk -F'\t' -v h="$f" '$1==h {print $2; exit}' "$RENAMES")
    b=${b:-$f}
    git cat-file -e "$BASE:$b" 2>/dev/null && BASE_FILES+=("$b")
  done
  if [ ${#BASE_FILES[@]} -eq 0 ]; then
    BASE_NOTE="0 files existed at BASE — every changed file is new"
  else
    scratch_worktree "$BASE"; BASE_WT=$SCRATCH_WT
    if [ -z "$BASE_WT" ]; then
      BASE_NOTE="inert: could not create a worktree at $BASE — nothing exempt"
    else
      BASE_ERR=$(mktemp -t cc-base-err)
      ( cd "$BASE_WT" && $CC_CMD --csv "${BASE_FILES[@]}" ) > "$BASE_CSV" 2> "$BASE_ERR"
      bs=$?
      if [ $bs -ne 0 ]; then
        BASE_NOTE="inert: lizard exit $bs at BASE — nothing exempt"; : > "$BASE_CSV"
      elif [ ! -s "$BASE_CSV" ]; then
        BASE_NOTE="inert: lizard produced no rows at BASE for ${#BASE_FILES[@]} files — nothing exempt"
      else
        BASE_NOTE="${#BASE_FILES[@]} files measured at BASE — worktree removed"
      fi
    fi
  fi
fi

# ---------------------------------------------------------------- touched ranges (for the tag)
RANGES=$(mktemp -t cc-ranges)
for f in "${CHANGED[@]}"; do
  git diff --unified=0 "$BASE" "$TIP" -- "$f" | python3 -c '
import re, sys
f = sys.argv[1]
for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", sys.stdin.read(), re.M):
    s = int(m.group(1)); c = int(m.group(2)) if m.group(2) is not None else 1
    print(f"{f}\t{s}\t{s if c == 0 else s + c - 1}")
' "$f"
done > "$RANGES"

# ---------------------------------------------------------------- classify + report
python3 - "$HEAD_CSV" "$BASE_CSV" "$RENAMES" "$RANGES" "$WARN" "$REJECT" "$EXEMPT" \
           "$NLOC_WARN" "$BASE" "$TIP" "$BASE_NOTE" "$deleted" "$HEAD_WT" \
           "$(printf '%s\n' "${EXCL_REPORT[@]:-}")" "$(printf '%s\n' "${CHANGED[@]}")" <<'PY'
import csv, re, subprocess, sys
(head_csv, base_csv, renames_f, ranges_f, warn, reject, exempt_flag, nloc_warn,
 base_sha, tip_sha, base_note, deleted, head_wt, excl_report, changed) = sys.argv[1:16]
warn, reject, nloc_warn = int(warn), int(reject), int(nloc_warn)
exempt_on = exempt_flag == "true"
changed = [c for c in changed.split("\n") if c]
TEST_RE = re.compile(r"(^|/)(tests?|spec|testdata|__tests__)/|_test\.|\.test\.|_spec\.|conftest\.py$")

def load(path):
    rows, skipped = [], 0
    with open(path, newline="") as fh:
        for r in csv.reader(fh):
            if len(r) != 11:
                skipped += 1; continue
            nloc, ccn, tok, params, length, long_name, fname, name, sig, start, end = r
            rows.append(dict(nloc=int(nloc), cc=int(ccn), tok=int(tok), params=int(params),
                             file=fname, name=name, sig=sig, start=int(start), end=int(end)))
    return rows, skipped

head, head_skipped = load(head_csv)
base, base_skipped = load(base_csv)
renames = {}
for line in open(renames_f):
    if "\t" in line:
        h, b = line.rstrip("\n").split("\t", 1); renames[h] = b
ranges = {}
for line in open(ranges_f):
    f, a, b = line.rstrip("\n").split("\t"); ranges.setdefault(f, []).append((int(a), int(b)))

if not head:
    print(f"CC INCONCLUSIVE: {' '.join(changed)}")
    print(f"Base: {base_sha}  Tip: {tip_sha}  lizard exited 0 with no rows for {len(changed)} changed files")
    sys.exit(1)

def body(sha, path, start, end):
    try:
        src = subprocess.run(["git", "show", f"{sha}:{path}"], capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    return "\n".join(src.split("\n")[start - 1:end])

# pair HEAD rows with BASE rows
by_sig = {}; by_name = {}; by_file = {}
for r in base:
    by_sig.setdefault((r["file"], r["name"], r["sig"]), []).append(r)
    by_name.setdefault((r["file"], r["name"]), []).append(r)
    by_file.setdefault(r["file"], []).append(r)
head_name_counts = {}
for r in head:
    bf = renames.get(r["file"], r["file"])
    head_name_counts[(bf, r["name"])] = head_name_counts.get((bf, r["name"]), 0) + 1

for r in head:
    bf = renames.get(r["file"], r["file"])
    r["base"] = None; r["tier"] = None
    if not exempt_on or not base:
        continue
    c = by_sig.get((bf, r["name"], r["sig"]))
    if c and len(c) == 1:
        r["base"], r["tier"] = c[0], "signature"; continue
    c = by_name.get((bf, r["name"]))
    if c and len(c) == 1 and head_name_counts.get((bf, r["name"])) == 1:
        r["base"], r["tier"] = c[0], "name"; continue
    cands = [b for b in by_file.get(bf, [])
             if (b["nloc"], b["tok"], b["params"], b["cc"]) == (r["nloc"], r["tok"], r["params"], r["cc"])]
    if len(cands) == 1:
        hb = body(tip_sha, r["file"], r["start"], r["end"]); bb = body(base_sha, bf, cands[0]["start"], cands[0]["end"])
        if hb is not None and hb == bb:
            r["base"], r["tier"] = cands[0], "body"

def touched(r):
    return any(a <= r["end"] and r["start"] <= b for a, b in ranges.get(r["file"], []))

red, yellow, exempt, test_info = [], [], [], []
for r in head:
    r["is_test"] = bool(TEST_RE.search(r["file"]))
    r["tag"] = "new in this PR" if touched(r) else "pre-existing"
    if r["cc"] >= reject:
        band = "red"
    elif r["cc"] >= warn:
        band = "yellow"
    else:
        continue
    if r["is_test"]:
        test_info.append(r); continue
    if band == "yellow":
        yellow.append(r); continue
    if r["base"] is not None and r["base"]["cc"] >= r["cc"]:
        exempt.append(r)
    else:
        red.append(r)

def reason(r):
    if not exempt_on or base_note.startswith("inert"):
        return "exemption not evaluated: " + ("exempt_pre_existing = false" if not exempt_on else base_note)
    if r["base"] is None:
        return "created" if r["tag"] == "new in this PR" else "base unmatched: renamed? new file? ambiguous name?"
    return f"worsened from {r['base']['cc']}"

def line(r):
    b = "new" if r["base"] is None else str(r["base"]["cc"])
    return f"  {r['file']}:{r['start']}  {r['name']}  CC={r['cc']}  base={b}  [{r['tag']}]"

N, M, K, T = len(red), len(yellow), len(exempt), len(test_info)
if N == 0 and M == 0:
    v = "CC CLEAN"
    if K: v += f" — {K} exempt"
    if T: v += f" — {T} test-info"
    rc = 0
else:
    v = f"CC VIOLATIONS: {N} 🔴, {M} 🟡"
    if K: v += f", {K} exempt"
    if T: v += f", {T} test-info"
    rc = 1 if N else 0
print(v)
print(f"Base: {base_sha}  Tip: {tip_sha}  Files measured: {len(changed)}  Functions: {len(head)}  "
      f"Rows skipped: {head_skipped}  Deleted paths dropped: {deleted}  cwd: {head_wt}")
print(f"Thresholds: warn={warn} reject={reject} exempt_pre_existing={exempt_flag}  (as given by the caller)")
ex = [l for l in excl_report.split("\n") if l]
print("Excluded: " + (", ".join(f"{p} ({n} paths)" for p, n in (l.split("\t") for l in ex)) if ex else "none"))
print(f"Base measurement: {base_note}")
if red:
    print(f"\n🔴 At or over reject (CC >= {reject}) — blocking:")
    for r in sorted(red, key=lambda r: -r["cc"]):
        print(line(r)); print(f"     {reason(r)}")
if yellow:
    print(f"\n🟡 Elevated ({warn} <= CC < {reject}):")
    for r in sorted(yellow, key=lambda r: -r["cc"]): print(line(r))
if exempt:
    ex_sorted = sorted(exempt, key=lambda r: -r["cc"]); show = ex_sorted[:max(5, min(25, len(ex_sorted)))]
    print(f"\n⚪ Exempt — did not get worse (cc_exempt_pre_existing = true).  Showing {len(show)} of {len(ex_sorted)}:")
    for r in show: print(line(r) + f"  (tier: {r['tier']})")
if test_info:
    print(f"\n⚪ Test functions at or over a threshold — informational, never blocking ({T}):")
    for r in sorted(test_info, key=lambda r: -r["cc"]): print(line(r))
if nloc_warn > 0:
    per_file = {}
    for r in head:
        per_file.setdefault(r["file"], [0, 0]); per_file[r["file"]][0] += r["nloc"]; per_file[r["file"]][1] += 1
    over = []
    for f, (n, cnt) in per_file.items():
        if n > nloc_warn:
            try:
                if "SLOPSTOP PRAGMA no-line-count-limit" in open(f"{head_wt}/{f}", errors="replace").read():
                    continue
            except OSError:
                pass
            over.append((f, n, cnt))
    if over:
        print(f"\n🟡 File NLOC over {nloc_warn}:")
        for f, n, cnt in over: print(f"  {f}  NLOC={n}  ({cnt} functions)")
measured = {r["file"] for r in head}
unmeasured = [c for c in changed if c not in measured]
print("Unmeasured: " + (", ".join(unmeasured) if unmeasured else "none"))
sys.exit(rc)
PY
