#!/usr/bin/env bash
# smoke-http.sh — Host-side HTTP smoke test for the four BILL-58 code-graph
#                 endpoints plus /healthz.
#
# Tests the host-facing port (default: http://localhost:7777) via curl — the
# same network path the MCP server uses.  Complements verify-bill58.sh, which
# tests via docker exec on the container-internal address.
#
# Usage (from repo root):
#   bash docker/postgres-pgvector/host-tests/smoke-http.sh
#   RAG_URL=http://other-host:7777 bash docker/postgres-pgvector/host-tests/smoke-http.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

assert_repo_root
require_container

echo "smoke-http — host-side HTTP tests against $RAG_URL"
echo "---"

# ---------------------------------------------------------------------------
# Probe helpers
# All functions exit 0 = PASS, non-zero = FAIL.
# ---------------------------------------------------------------------------

_healthz_ok() {
    local resp
    resp=$(curl -sf "$RAG_URL/healthz") || return 1
    echo "$resp" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('postgres') == 'ok' and d.get('schema') == 'ok', f'unexpected: {d}'
"
}

# POST body → assert HTTP 200 + response has \"results\" key.
_post_has_results() {
    local endpoint="$1" body="$2"
    local resp
    resp=$(curl_json "$RAG_URL$endpoint" POST "$body") || return 1
    echo "$resp" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'results' in d, f'no results key: {d}'
assert isinstance(d['results'], list), f'results is not a list'
"
}

# POST body → assert HTTP 200 + results == [].
_post_empty_results() {
    local endpoint="$1" body="$2"
    local resp
    resp=$(curl_json "$RAG_URL$endpoint" POST "$body") || return 1
    echo "$resp" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('results') == [], f'expected empty results, got: {d}'
"
}

# POST body → assert HTTP status equals $want.
_post_status() {
    local want="$1" endpoint="$2" body="$3"
    local got
    got=$(curl_status "$RAG_URL$endpoint" POST "$body")
    [ "$got" = "$want" ]
}

# If the graph has results for $endpoint, assert each result carries the
# required set of keys.  Vacuously passes when results is empty (no data yet).
_result_schema_ok() {
    local endpoint="$1" body="$2"
    local resp
    resp=$(curl_json "$RAG_URL$endpoint" POST "$body") || return 1
    echo "$resp" | python3 -c "
import sys, json
REQUIRED = {'moniker', 'file_path', 'line', 'location', 'lang', 'repo', 'external'}
d = json.load(sys.stdin)
rows = d.get('results', [])
for row in rows:
    missing = REQUIRED - set(row.keys())
    assert not missing, f'result missing keys: {missing}, got: {row}'
"
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

note "GET /healthz"
check "healthz returns 200 with postgres=ok and schema=ok" \
    _healthz_ok

note "POST /code-graph/callers"
check "callers returns 200 + {results:[...]} shape" \
    _post_has_results /code-graph/callers \
        '{"moniker":"scip-go gomod slopstop . slopstop/nonexistent().","repo":"iansmith/slopstop"}'
check "callers: each result carries required keys (vacuous if graph empty)" \
    _result_schema_ok /code-graph/callers \
        '{"moniker":"","repo":"iansmith/slopstop","limit":5}'
check "callers: limit=201 returns 422" \
    _post_status 422 /code-graph/callers \
        '{"moniker":"x","limit":201}'

note "POST /code-graph/implementors"
check "implementors returns 200 + {results:[...]} shape" \
    _post_has_results /code-graph/implementors \
        '{"moniker":"scip-go gomod slopstop . slopstop/NoSuchInterface#.","repo":"iansmith/slopstop"}'
check "implementors: each result carries required keys" \
    _result_schema_ok /code-graph/implementors \
        '{"moniker":"","repo":"iansmith/slopstop","limit":5}'
check "implementors: limit=201 returns 422" \
    _post_status 422 /code-graph/implementors \
        '{"moniker":"x","limit":201}'

note "POST /code-graph/blast-radius"
check "blast-radius returns 200 + {results:[...]} shape" \
    _post_has_results /code-graph/blast-radius \
        '{"moniker":"scip-go gomod slopstop . slopstop/nonexistent().","depth":2,"repo":"iansmith/slopstop"}'
check "blast-radius: each result carries required keys" \
    _result_schema_ok /code-graph/blast-radius \
        '{"moniker":"","depth":2,"repo":"iansmith/slopstop","limit":5}'
check "blast-radius: depth=6 returns 422" \
    _post_status 422 /code-graph/blast-radius \
        '{"moniker":"x","depth":6}'
check "blast-radius: limit=201 returns 422" \
    _post_status 422 /code-graph/blast-radius \
        '{"moniker":"x","limit":201}'

note "POST /code-graph/ticket-code"
check "ticket-code with unknown ID returns 200 + empty results" \
    _post_empty_results /code-graph/ticket-code \
        '{"ticket_id":"BILL-XXXXXX","repo":"iansmith/slopstop"}'
check "ticket-code: each result carries required keys" \
    _result_schema_ok /code-graph/ticket-code \
        '{"ticket_id":"BILL-56","repo":"iansmith/slopstop","limit":5}'
check "ticket-code: limit=201 returns 422" \
    _post_status 422 /code-graph/ticket-code \
        '{"ticket_id":"x","limit":201}'

print_summary
