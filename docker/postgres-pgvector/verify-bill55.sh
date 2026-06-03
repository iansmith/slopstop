#!/usr/bin/env bash
# verify-bill55.sh — BILL-55 acceptance: SCIP ingestion pipeline (indexers → Cypher MERGE).
#
# Usage:
#   bash docker/postgres-pgvector/verify-bill55.sh [IMAGE_TAG]
#
# Default IMAGE_TAG is slopstop-rag:latest.
# All probes go via `docker exec` (no host port publishing).

set -u

IMAGE="${1:-slopstop-rag:latest}"
CONTAINER="ticket-rag-bill55-verify"
DATA_DIR=$(mktemp -d -t bill55-pgdata.XXXXXX)
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

# Minimal SCIP fixture: one file, one function (describe), one call edge (fmt.Println).
# Mirrors the Layer 1/2 test fixtures in test_code_graph_ingest*.py.
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
          "symbol_roles": 8,
          "enclosing_range": [10, 0, 13, 1]
        }
      ]
    }],
    "external_symbols": []
  }
}'

# POST /code-graph/ingest and capture the JSON response.
# Pipes the payload from the host via python3 -c to avoid curl dependency.
ingest_response() {
    printf '%s' "$SCIP_PAYLOAD" | docker exec -i "$CONTAINER" python3 -c "
import sys, json, urllib.request
payload = sys.stdin.buffer.read()
req = urllib.request.Request(
    'http://127.0.0.1:7777/code-graph/ingest',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req) as r:
    print(r.read().decode())
"
}

ingest_ok() {
    local resp
    resp=$(ingest_response 2>/dev/null) || return 1
    echo "$resp" | grep -q '"vertices_merged"' || return 1
    echo "$resp" | grep -q '"edges_merged"'
}

# Response must report at least 2 vertices (File + Function; External stub optional)
# and exactly 1 edge (CALLS from describe → Println).
ingest_counts_ok() {
    local resp v e
    resp=$(ingest_response 2>/dev/null) || return 1
    v=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['vertices_merged'])" 2>/dev/null) || return 1
    e=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['edges_merged'])" 2>/dev/null) || return 1
    [ "$v" -ge 2 ] && [ "$e" -eq 1 ]
}

# After ingest, the Function vertex must exist in the AGE graph.
vertex_in_graph() {
    docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<'EOSQL' \
        | grep -q '"moniker"'
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT * FROM cypher('code_graph', $$
  MATCH (v {moniker: 'scip-go gomod scipspike . scipspike/describe().'})
  RETURN v
$$) AS (v agtype);
EOSQL
}

# Count vertices in the code_graph via Cypher (AGE has no ag_vertex catalog table).
cypher_vertex_count() {
    docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<'EOSQL' \
        | tail -n1 | tr -d '[:space:]'
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT * FROM cypher('code_graph', $$ MATCH (v) RETURN count(v) $$) AS (n agtype);
EOSQL
}

# Second identical ingest must not increase vertex count (idempotent MERGE).
ingest_idempotent() {
    local v1 v2
    v1=$(cypher_vertex_count) || return 1
    [ -n "$v1" ] || return 1
    ingest_response >/dev/null 2>&1 || return 1
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

echo "BILL-55 verification — image: $IMAGE"
echo "host data dir: $DATA_DIR"
echo "---"

note "Fresh-volume boot"
docker run -d \
    --name "$CONTAINER" \
    -v "$DATA_DIR:/var/lib/postgresql" \
    "$IMAGE" >/dev/null 2>&1

check "fresh-volume boot: app ready (uvicorn up, schema applied) within 60s" \
    wait_uvicorn_ge 1 60

check "POST /code-graph/ingest returns 200 with vertices_merged + edges_merged" \
    ingest_ok

check "ingest counts: ≥2 vertices (File+Function), 1 CALLS edge" \
    ingest_counts_ok

check "Function vertex present in AGE graph after ingest" \
    vertex_in_graph

check "second identical ingest is idempotent (vertex count unchanged)" \
    ingest_idempotent

check "logs contain no non-benign FATAL / panic / Traceback markers" \
    no_fatal_markers

if [ "$FAIL" -gt 0 ]; then
    echo "--- container logs (tail 50) for debugging ---"
    docker logs --tail 50 "$CONTAINER" 2>&1 || true
fi

echo "---"
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
