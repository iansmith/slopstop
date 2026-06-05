#!/usr/bin/env bash
# verify-bill58.sh — BILL-58 acceptance: query surface (callers, implementors,
#                    blast-radius, ticket-code) via the four new MCP endpoints.
#
# Usage:
#   bash docker/postgres-pgvector/verify-bill58.sh [IMAGE_TAG]
#
# Default IMAGE_TAG is slopstop-rag:latest.
# All probes go via `docker exec` (no host port publishing required).
#
# Test plan:
#  1. Fresh-volume boot, wait for Uvicorn.
#  2. POST /code-graph/ingest — synthetic SCIP fixture:
#       - linesOverlap()  — target function (enclosing_range lines 10–15)
#       - caller()        — calls linesOverlap  (CALLS edge)
#       - blastA()        — calls caller        (CALLS edge, depth-2 chain)
#       - ConcreteType.   — implements Overlapper# (IMPLEMENTS edge)
#       - Overlapper#.    — interface
#  3. POST /code-graph/ingest-commits — ticket BILL-58 commit touching linesOverlap.
#  4. GET  /code-graph/callers   {moniker: linesOverlap} → caller in results + location set.
#  5. GET  /code-graph/implementors {moniker: Overlapper#} → ConcreteType in results.
#  6. GET  /code-graph/blast-radius {moniker: linesOverlap, depth: 2} → blastA in results.
#  7. GET  /code-graph/ticket-code  {ticket_id: BILL-58} → linesOverlap in results.
#  8. Validation gates: limit=201 → 422; depth=6 → 422.
#  9. No fatal log markers.

set -u

IMAGE="${1:-slopstop-rag:latest}"
CONTAINER="ticket-rag-bill58-verify"
DATA_DIR=$(mktemp -d -t bill58-pgdata.XXXXXX)
PASS=0
FAIL=0

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    chmod -R u+w "$DATA_DIR" 2>/dev/null || true
    rm -rf "$DATA_DIR"
}
trap cleanup EXIT

note() { echo "  ----  $*"; }

check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS  $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $name"
        FAIL=$((FAIL + 1))
    fi
}

uvicorn_count() { docker logs "$CONTAINER" 2>&1 | grep -c 'Uvicorn running on'; }

wait_uvicorn_ge() {
    local want="$1" timeout="${2:-60}"
    for _ in $(seq 1 "$timeout"); do
        [ "$(uvicorn_count)" -ge "$want" ] && return 0
        sleep 1
    done
    return 1
}

# ── SCIP fixture ──────────────────────────────────────────────────────────────
#
# Graph topology after ingest:
#
#   blastA() --CALLS--> caller() --CALLS--> linesOverlap()
#   ConcreteType. --IMPLEMENTS--> Overlapper#.
#
# Occurrence ranges (single-line: [line, startChar, endChar]):
#   linesOverlap  definition @ line 10, enclosing_range [10,0,15,1]
#   caller        definition @ line 20, enclosing_range [20,0,25,1]
#     reference to linesOverlap @ line 21 (inside caller's body) → CALLS edge
#   blastA        definition @ line 30, enclosing_range [30,0,35,1]
#     reference to caller       @ line 31 (inside blastA's body)  → CALLS edge
#   ConcreteType  definition @ line 40 (no enclosing_range — it's a type, not a fn)
#   Overlapper#   definition @ line 50
#
SCIP_PAYLOAD='
{
  "repo": "iansmith/slopstop",
  "index": {
    "metadata": {"tool_info": {"name": "scip-go", "version": "0.2.7"}},
    "documents": [{
      "language": "Go",
      "relative_path": "commit_ingest.go",
      "symbols": [
        {
          "symbol": "scip-go gomod slopstop . slopstop/linesOverlap().",
          "kind": "Function",
          "relationships": []
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/caller().",
          "kind": "Function",
          "relationships": []
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/blastA().",
          "kind": "Function",
          "relationships": []
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/ConcreteType.",
          "kind": "Class",
          "relationships": [
            {
              "symbol": "scip-go gomod slopstop . slopstop/Overlapper#.",
              "is_implementation": true
            }
          ]
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/Overlapper#.",
          "kind": "Interface",
          "relationships": []
        }
      ],
      "occurrences": [
        {
          "symbol": "scip-go gomod slopstop . slopstop/linesOverlap().",
          "range": [10, 0, 20],
          "symbol_roles": 1,
          "enclosing_range": [10, 0, 15, 1]
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/caller().",
          "range": [20, 0, 20],
          "symbol_roles": 1,
          "enclosing_range": [20, 0, 25, 1]
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/linesOverlap().",
          "range": [21, 4, 20],
          "symbol_roles": 8
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/blastA().",
          "range": [30, 0, 20],
          "symbol_roles": 1,
          "enclosing_range": [30, 0, 35, 1]
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/caller().",
          "range": [31, 4, 20],
          "symbol_roles": 8
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/ConcreteType.",
          "range": [40, 0, 20],
          "symbol_roles": 1
        },
        {
          "symbol": "scip-go gomod slopstop . slopstop/Overlapper#.",
          "range": [50, 0, 20],
          "symbol_roles": 1
        }
      ]
    }],
    "external_symbols": []
  }
}'

# ── Commit fixture ────────────────────────────────────────────────────────────
# changed_lines [[10, 12]] overlaps linesOverlap's enclosing_range [10..15]
# → TOUCHES edge from this Commit to the linesOverlap Function vertex.
COMMIT_PAYLOAD='
{
  "repo": "iansmith/slopstop",
  "sha": "cccc5858dddd5858eeee5858ffff58580000cccc",
  "subject": "[BILL-58] Add query surface (callers, blast-radius, ticket-code)",
  "author": "Ian Smith",
  "authored_at": "2026-06-04T16:00:00Z",
  "ticket_ids": ["BILL-58"],
  "files": [
    {
      "path": "commit_ingest.go",
      "change_type": "modified",
      "hunks": 1,
      "changed_lines": [[10, 12]]
    }
  ]
}'

# ── HTTP helpers ──────────────────────────────────────────────────────────────

post_json() {
    local payload="$1" endpoint="$2"
    printf '%s' "$payload" | docker exec -i "$CONTAINER" python3 -c "
import sys, json, urllib.request
payload = sys.stdin.buffer.read()
req = urllib.request.Request(
    'http://127.0.0.1:7777${endpoint}',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req) as r:
    print(r.read().decode())
"
}

post_json_status() {
    local payload="$1" endpoint="$2"
    printf '%s' "$payload" | docker exec -i "$CONTAINER" python3 -c "
import sys, urllib.request, urllib.error
payload = sys.stdin.buffer.read()
req = urllib.request.Request(
    'http://127.0.0.1:7777${endpoint}',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST',
)
try:
    with urllib.request.urlopen(req) as r:
        print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
"
}

# ── Probe functions ───────────────────────────────────────────────────────────

scip_ingest_ok() {
    local resp
    resp=$(post_json "$SCIP_PAYLOAD" /code-graph/ingest 2>/dev/null) || return 1
    echo "$resp" | grep -q '"vertices_merged"'
}

commit_ingest_ok() {
    local resp
    resp=$(post_json "$COMMIT_PAYLOAD" /code-graph/ingest-commits 2>/dev/null) || return 1
    echo "$resp" | grep -q '"commits_merged"' || return 1
    echo "$resp" | grep -q '"touches_merged"'
}

# callers of linesOverlap → should include caller() with a non-null location
callers_returns_result() {
    local resp
    resp=$(post_json \
        '{"moniker":"scip-go gomod slopstop . slopstop/linesOverlap().", "repo":"iansmith/slopstop"}' \
        /code-graph/callers 2>/dev/null) || return 1
    echo "$resp" | grep -q '"results"' || return 1
    echo "$resp" | grep -q 'slopstop/caller'
}

callers_result_has_location() {
    local resp
    resp=$(post_json \
        '{"moniker":"scip-go gomod slopstop . slopstop/linesOverlap().", "repo":"iansmith/slopstop"}' \
        /code-graph/callers 2>/dev/null) || return 1
    # location field should be "file_path:line" — non-null string
    echo "$resp" | grep -qE '"location"\s*:\s*"[^"]+'
}

# implementors of Overlapper# → should include ConcreteType
implementors_returns_concretetype() {
    local resp
    resp=$(post_json \
        '{"moniker":"scip-go gomod slopstop . slopstop/Overlapper#.", "repo":"iansmith/slopstop"}' \
        /code-graph/implementors 2>/dev/null) || return 1
    echo "$resp" | grep -q '"results"' || return 1
    echo "$resp" | grep -q 'ConcreteType'
}

# blast-radius of linesOverlap depth=2 → should include blastA (depth-2 caller)
blast_radius_depth2_includes_blasta() {
    local resp
    resp=$(post_json \
        '{"moniker":"scip-go gomod slopstop . slopstop/linesOverlap().", "depth":2, "repo":"iansmith/slopstop"}' \
        /code-graph/blast-radius 2>/dev/null) || return 1
    echo "$resp" | grep -q '"results"' || return 1
    echo "$resp" | grep -q 'blastA'
}

# blast-radius depth=1 → should include caller but NOT blastA
blast_radius_depth1_excludes_blasta() {
    local resp
    resp=$(post_json \
        '{"moniker":"scip-go gomod slopstop . slopstop/linesOverlap().", "depth":1, "repo":"iansmith/slopstop"}' \
        /code-graph/blast-radius 2>/dev/null) || return 1
    echo "$resp" | grep -q 'slopstop/caller' || return 1
    ! echo "$resp" | grep -q 'blastA'
}

# ticket-code for BILL-58 → should include linesOverlap
ticket_code_returns_lines_overlap() {
    local resp
    resp=$(post_json \
        '{"ticket_id":"BILL-58", "repo":"iansmith/slopstop"}' \
        /code-graph/ticket-code 2>/dev/null) || return 1
    echo "$resp" | grep -q '"results"' || return 1
    echo "$resp" | grep -q 'linesOverlap'
}

# ticket-code for unknown ticket → empty results, not an error
ticket_code_unknown_is_empty_not_error() {
    local resp
    resp=$(post_json \
        '{"ticket_id":"BILL-XXXXXX", "repo":"iansmith/slopstop"}' \
        /code-graph/ticket-code 2>/dev/null) || return 1
    echo "$resp" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('results') == [], f'expected empty results, got {d}'
" 2>/dev/null
}

# Validation: limit > 200 → 422
callers_limit_over_max_is_422() {
    local status
    status=$(post_json_status \
        '{"moniker":"scip-go gomod slopstop . slopstop/linesOverlap().", "limit":201}' \
        /code-graph/callers 2>/dev/null)
    [ "$status" = "422" ]
}

# Validation: depth > 5 → 422
blast_radius_depth_over_max_is_422() {
    local status
    status=$(post_json_status \
        '{"moniker":"scip-go gomod slopstop . slopstop/linesOverlap().", "depth":6}' \
        /code-graph/blast-radius 2>/dev/null)
    [ "$status" = "422" ]
}

no_fatal_markers() {
    ! docker logs "$CONTAINER" 2>&1 \
        | grep -E -i '(FATAL|panic|^Traceback)' \
        | grep -v -i -e 'the database system is starting up' \
                     -e 'not yet accepting connections' \
        | grep -q .
}

# ── Test run ──────────────────────────────────────────────────────────────────

echo "BILL-58 verification — image: $IMAGE"
echo "host data dir: $DATA_DIR"
echo "---"

note "Fresh-volume boot"
docker run -d \
    --name "$CONTAINER" \
    -v "$DATA_DIR:/var/lib/postgresql" \
    "$IMAGE" >/dev/null 2>&1

check "fresh-volume boot: app ready within 60s" \
    wait_uvicorn_ge 1 60

note "Seed code graph via SCIP ingest"
check "POST /code-graph/ingest: returns vertices_merged" \
    scip_ingest_ok

note "Seed commit provenance (BILL-58 commit touching linesOverlap)"
check "POST /code-graph/ingest-commits: returns commits_merged + touches_merged" \
    commit_ingest_ok

note "POST /code-graph/callers"
check "callers of linesOverlap returns ≥1 result including caller()" \
    callers_returns_result
check "callers result has non-null location field (file_path:line)" \
    callers_result_has_location

note "POST /code-graph/implementors"
check "implementors of Overlapper# returns ConcreteType" \
    implementors_returns_concretetype

note "POST /code-graph/blast-radius"
check "blast-radius depth=2 includes blastA (depth-2 transitive caller)" \
    blast_radius_depth2_includes_blasta
check "blast-radius depth=1 includes caller but NOT blastA" \
    blast_radius_depth1_excludes_blasta

note "POST /code-graph/ticket-code"
check "ticket-code BILL-58 returns linesOverlap (TOUCHES edge present)" \
    ticket_code_returns_lines_overlap
check "ticket-code unknown ticket_id returns empty results (not an error)" \
    ticket_code_unknown_is_empty_not_error

note "Input validation gates"
check "callers with limit=201 returns 422 Unprocessable Entity" \
    callers_limit_over_max_is_422
check "blast-radius with depth=6 returns 422 Unprocessable Entity" \
    blast_radius_depth_over_max_is_422

check "logs contain no non-benign FATAL / panic / Traceback markers" \
    no_fatal_markers

if [ "$FAIL" -gt 0 ]; then
    echo "--- container logs (tail 50) for debugging ---"
    docker logs --tail 50 "$CONTAINER" 2>&1 || true
fi

echo "---"
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
