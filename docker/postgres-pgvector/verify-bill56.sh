#!/usr/bin/env bash
# verify-bill56.sh — BILL-56 acceptance: commit provenance (TOUCHES edges).
#
# Usage:
#   bash docker/postgres-pgvector/verify-bill56.sh [IMAGE_TAG]
#
# Default IMAGE_TAG is slopstop-rag:latest.
# All probes go via `docker exec` (no host port publishing).
#
# Test plan:
#  1. Fresh-volume boot, wait for Uvicorn.
#  2. Ingest the BILL-55 SCIP fixture (so Function vertices exist in AGE).
#  3. POST a file-level commit payload → verify 200 + Commit vertex in AGE.
#  4. POST a function-level commit payload → verify TOUCHES edge to the
#     Function vertex (not just the File vertex).
#  5. Re-ingest the same commit → verify idempotency (vertex count unchanged).
#  6. No fatal log markers.

set -u

IMAGE="${1:-slopstop-rag:latest}"
CONTAINER="ticket-rag-bill56-verify"
DATA_DIR=$(mktemp -d -t bill56-pgdata.XXXXXX)
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

# ── SCIP fixture (reused from verify-bill55.sh) ───────────────────────────────
# One file (main.go), one function (describe) with enclosing_range, one call edge.
SCIP_PAYLOAD='
{
  "repo": "iansmith/scip-spike",
  "index": {
    "metadata": {"tool_info": {"name": "scip-go", "version": "0.2.7"}},
    "documents": [{
      "language": "Go",
      "relative_path": "main.go",
      "symbols": [{
        "symbol": "scip-go gomod scipspike . scipspike/describe().",
        "kind": "Function",
        "relationships": []
      }],
      "occurrences": [
        {
          "symbol": "scip-go gomod scipspike . scipspike/describe().",
          "range": [10, 5, 13],
          "symbol_roles": 1,
          "enclosing_range": [10, 0, 13, 1]
        },
        {
          "symbol": "scip-go gomod `fmt` v0 fmt/Println().",
          "range": [11, 4, 8],
          "symbol_roles": 8
        }
      ]
    }],
    "external_symbols": []
  }
}'

# ── Commit payloads ───────────────────────────────────────────────────────────

# File-level: changed_lines=null → TOUCHES to File vertex only.
COMMIT_FILE_LEVEL='
{
  "repo": "iansmith/scip-spike",
  "sha": "aaaa1111bbbb2222cccc3333dddd4444eeee5555",
  "subject": "[BILL-55] Add describe function",
  "author": "Ian Smith",
  "authored_at": "2026-06-03T20:00:00Z",
  "ticket_ids": ["BILL-55"],
  "files": [
    {
      "path": "main.go",
      "change_type": "modified",
      "hunks": 1,
      "changed_lines": null
    }
  ]
}'

# Function-level: changed_lines overlapping describe()'s body [10,0..13,1].
COMMIT_FUNCTION_LEVEL='
{
  "repo": "iansmith/scip-spike",
  "sha": "bbbb2222cccc3333dddd4444eeee5555ffff6666",
  "subject": "[BILL-56] Touch describe body",
  "author": "Ian Smith",
  "authored_at": "2026-06-03T21:00:00Z",
  "ticket_ids": ["BILL-56"],
  "files": [
    {
      "path": "main.go",
      "change_type": "modified",
      "hunks": 1,
      "changed_lines": [[10, 12]]
    }
  ]
}'

# Helper: POST a payload to an endpoint and return the JSON response.
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

# ── Probe functions ───────────────────────────────────────────────────────────

scip_ingest_ok() {
    local resp
    resp=$(post_json "$SCIP_PAYLOAD" /code-graph/ingest 2>/dev/null) || return 1
    echo "$resp" | grep -q '"vertices_merged"'
}

commit_ingest_ok() {
    local payload="$1"
    local resp
    resp=$(post_json "$payload" /code-graph/ingest-commits 2>/dev/null) || return 1
    echo "$resp" | grep -q '"commits_merged"' || return 1
    echo "$resp" | grep -q '"touches_merged"'
}

commit_vertex_in_graph() {
    local sha="$1"
    docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<EOSQL \
        | grep -q '"sha"'
LOAD 'age';
SET search_path = ag_catalog, "\$user", public;
SELECT * FROM cypher('code_graph', \$\$
  MATCH (c:Commit {sha: '${sha}'})
  RETURN c
\$\$) AS (c agtype);
EOSQL
}

touches_edge_in_graph() {
    local sha="$1"
    docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<EOSQL \
        | grep -q .
LOAD 'age';
SET search_path = ag_catalog, "\$user", public;
SELECT * FROM cypher('code_graph', \$\$
  MATCH (c:Commit {sha: '${sha}'})-[e:TOUCHES]->()
  RETURN e
\$\$) AS (e agtype);
EOSQL
}

touches_function_not_just_file() {
    local sha="$1"
    docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<EOSQL \
        | grep -q '"label":"Function"'
LOAD 'age';
SET search_path = ag_catalog, "\$user", public;
SELECT * FROM cypher('code_graph', \$\$
  MATCH (c:Commit {sha: '${sha}'})-[:TOUCHES]->(tgt)
  RETURN tgt
\$\$) AS (tgt agtype);
EOSQL
}

cypher_vertex_count() {
    docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<'EOSQL' \
        | tail -n1 | tr -d '[:space:]'
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT * FROM cypher('code_graph', $$ MATCH (v) RETURN count(v) $$) AS (n agtype);
EOSQL
}

commit_ingest_idempotent() {
    local payload="$1"
    local v1 v2
    v1=$(cypher_vertex_count) || return 1
    [ -n "$v1" ] || return 1
    post_json "$payload" /code-graph/ingest-commits >/dev/null 2>&1 || return 1
    v2=$(cypher_vertex_count) || return 1
    [ "$v1" = "$v2" ]
}

no_fatal_markers() {
    ! docker logs "$CONTAINER" 2>&1 \
        | grep -E -i '(FATAL|panic|^Traceback)' \
        | grep -v -i -e 'the database system is starting up' \
                     -e 'not yet accepting connections' \
        | grep -q .
}

# ── Test run ──────────────────────────────────────────────────────────────────

echo "BILL-56 verification — image: $IMAGE"
echo "host data dir: $DATA_DIR"
echo "---"

note "Fresh-volume boot"
docker run -d \
    --name "$CONTAINER" \
    -v "$DATA_DIR:/var/lib/postgresql" \
    "$IMAGE" >/dev/null 2>&1

check "fresh-volume boot: app ready within 60s" \
    wait_uvicorn_ge 1 60

note "Seed code graph with SCIP fixture (Function vertex + enclosing_range)"
check "POST /code-graph/ingest: seed SCIP index" \
    scip_ingest_ok

note "File-level commit ingest (changed_lines=null)"
check "POST /code-graph/ingest-commits: file-level returns 200 + counts" \
    commit_ingest_ok "$COMMIT_FILE_LEVEL"

check "Commit vertex (file-level SHA) present in AGE" \
    commit_vertex_in_graph "aaaa1111bbbb2222cccc3333dddd4444eeee5555"

check "TOUCHES edge from file-level commit present in AGE" \
    touches_edge_in_graph "aaaa1111bbbb2222cccc3333dddd4444eeee5555"

note "Function-level commit ingest (changed_lines overlapping describe body)"
check "POST /code-graph/ingest-commits: function-level returns 200 + counts" \
    commit_ingest_ok "$COMMIT_FUNCTION_LEVEL"

check "Commit vertex (function-level SHA) present in AGE" \
    commit_vertex_in_graph "bbbb2222cccc3333dddd4444eeee5555ffff6666"

check "TOUCHES edge from function-level commit targets Function vertex (not just File)" \
    touches_function_not_just_file "bbbb2222cccc3333dddd4444eeee5555ffff6666"

note "Idempotency"
check "re-ingest same commit is idempotent (vertex count unchanged)" \
    commit_ingest_idempotent "$COMMIT_FUNCTION_LEVEL"

check "logs contain no non-benign FATAL / panic / Traceback markers" \
    no_fatal_markers

if [ "$FAIL" -gt 0 ]; then
    echo "--- container logs (tail 50) for debugging ---"
    docker logs --tail 50 "$CONTAINER" 2>&1 || true
fi

echo "---"
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
