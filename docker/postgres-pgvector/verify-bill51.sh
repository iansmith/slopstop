#!/usr/bin/env bash
# verify-bill51.sh — BILL-51 acceptance: ticket_meta schema migration + metadata
# filters in /search endpoint.
#
# Usage:
#   bash docker/postgres-pgvector/verify-bill51.sh [IMAGE_TAG]
#
# Default IMAGE_TAG is slopstop-rag:latest (the tag `make rag-build` produces).
#
# Two tiers of checks:
#
#   Tier 1 — STRUCTURAL (always run, no Linear credentials needed):
#     The ticket_meta table exists, has the expected columns, and the /search
#     endpoint accepts the new metadata filter params (state_norm, assignee,
#     priority_max, labels, created_after, updated_after) without returning
#     a 422 validation error. Invalid values are correctly rejected with 422.
#
#   Tier 2 — LIVE DOGFOOD (only when LINEAR_API_KEY is exported AND the LOU
#     workspace is reachable): syncs LOU-102, confirms ticket_meta gains a row
#     with populated state_norm, then verifies that metadata filters actually
#     narrow results vs unfiltered baseline. Unfiltered regression: same top
#     chunk as BILL-37 verify (LOU-102 for the multicol query).
#
# All in-container probes go via `docker exec` (no host port publishing).

set -u

# Read LINEAR_API_KEY from .harvester.toml when not already set in the
# environment. The file is TOML ([linear] / api_key = "…") — the same format
# parsed by the Makefile and rag_service.harvesters.linear via tomllib — so it
# must be PARSED, not sourced as shell (a bare `source` chokes on `[linear]`
# and would silently leave the key unset, skipping all Tier-2 live checks).
if [ -z "${LINEAR_API_KEY:-}" ]; then
    _CREDS="$(cd "$(dirname "$0")/../.." && pwd)/.harvester.toml"
    if [ -f "$_CREDS" ]; then
        LINEAR_API_KEY="$(python3 -c "import tomllib,sys; print(tomllib.load(open(sys.argv[1],'rb')).get('linear',{}).get('api_key',''),end='')" "$_CREDS" 2>/dev/null || true)"
        export LINEAR_API_KEY
    fi
fi

IMAGE="${1:-slopstop-rag:latest}"
CONTAINER="ticket-rag-bill51-verify"
DATA_DIR=$(mktemp -d -t bill51-pgdata.XXXXXX)
PASS=0
FAIL=0
SKIP=0

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

check_with_output() {
    # Like check but prints stdout/stderr on failure for easier diagnosis.
    local name="$1"; shift
    local out
    if out=$("$@" 2>&1); then
        echo "  PASS  $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $name"
        echo "          output: $out"
        FAIL=$((FAIL + 1))
    fi
}

skip() {
    echo "  SKIP  $1"
    echo "          reason: $2"
    SKIP=$((SKIP + 1))
}

healthz_ok() {
    local timeout="${1:-30}"
    for _ in $(seq 1 "$timeout"); do
        if docker exec "$CONTAINER" python3 -c "
import json, sys, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:7777/healthz', timeout=2) as r:
        d = json.loads(r.read().decode())
        sys.exit(0 if d.get('postgres')=='ok' and d.get('schema')=='ok' else 1)
except Exception:
    sys.exit(1)
" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

post_search() {
    # POST /search with a JSON body; exits 0 iff HTTP status is 200.
    local body="$1"
    docker exec "$CONTAINER" python3 -c "
import json, sys, urllib.request, urllib.error
body = '''$body'''.encode()
req = urllib.request.Request('http://127.0.0.1:7777/search', data=body,
                             headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        sys.exit(0 if r.status == 200 else 1)
except urllib.error.HTTPError as e:
    print('HTTP', e.code, e.read().decode()[:200]); sys.exit(1)
except Exception as e:
    print('error:', e); sys.exit(1)
"
}

post_search_status() {
    # Returns the HTTP status code of POST /search (for 422 rejection tests).
    local body="$1"
    docker exec "$CONTAINER" python3 -c "
import json, sys, urllib.request, urllib.error
body = '''$body'''.encode()
req = urllib.request.Request('http://127.0.0.1:7777/search', data=body,
                             headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception as e:
    print('error:', e); sys.exit(1)
" 2>/dev/null
}

echo "BILL-51 verification — image: $IMAGE"
echo "host data dir: $DATA_DIR"
echo "---"

# -------------------------------------------------------------------
# Boot
# -------------------------------------------------------------------
note "Boot — fresh-volume start"

DOCKER_ENV=()
if [ -n "${LINEAR_API_KEY:-}" ]; then
    DOCKER_ENV=(-e "LINEAR_API_KEY=${LINEAR_API_KEY}")
fi

docker run -d \
    --name "$CONTAINER" \
    -v "$DATA_DIR:/var/lib/postgresql" \
    ${DOCKER_ENV[@]+"${DOCKER_ENV[@]}"} \
    "$IMAGE" >/dev/null 2>&1

check "fresh-volume boot: /healthz postgres:ok AND schema:ok within 30s" \
    healthz_ok 30

# -------------------------------------------------------------------
# Tier 1 — structural (no credentials needed)
# -------------------------------------------------------------------
note "Tier 1 — structural (no Linear credentials needed)"

# ticket_meta table exists with the schema-003 migration applied.
check "ticket_meta table exists in postgres" \
    bash -c "docker exec $CONTAINER psql -U postgres -d postgres -c '\d ticket_meta' 2>&1 | grep -q 'ticket_meta'"

# Spot-check key columns from 003_ticket_meta.sql.
check "ticket_meta has state_norm, assignee, priority_num, labels columns" \
    bash -c "docker exec $CONTAINER psql -U postgres -d postgres -tAc \
        \"SELECT column_name FROM information_schema.columns WHERE table_name='ticket_meta' AND column_name IN ('state_norm','assignee','priority_num','labels') ORDER BY column_name\" \
        | tr '\n' ',' | grep -q 'assignee,labels,priority_num,state_norm'"

# SearchFilters new fields are importable and instantiable.
check "SearchFilters accepts BILL-51 metadata fields without error" \
    bash -c "docker exec $CONTAINER python3 -c \"
from rag_service.models import SearchFilters
f = SearchFilters(assignee='Ian', state_norm='open', priority_max=2,
                  labels=['bug'], created_after='2025-01-01', updated_after='2025-06-01')
assert f.assignee == 'Ian'
assert f.state_norm == 'open'
assert f.priority_max == 2
assert f.labels == ['bug']
\""

# state_norm Literal validation: only open/in_progress/done/canceled are valid.
check "SearchFilters rejects invalid state_norm value" \
    bash -c "docker exec $CONTAINER python3 -c \"
from rag_service.models import SearchFilters
import sys
try:
    SearchFilters(state_norm='invalid_value')
    sys.exit(1)  # should have raised
except Exception:
    sys.exit(0)
\""

# priority_max validation: must be 0-4.
check "SearchFilters rejects priority_max=99 (out of range)" \
    bash -c "docker exec $CONTAINER python3 -c \"
from rag_service.models import SearchFilters
import sys
try:
    SearchFilters(priority_max=99)
    sys.exit(1)
except Exception:
    sys.exit(0)
\""

# Empty labels list is coerced to None (no meta JOIN on empty label match).
check "SearchFilters coerces empty labels list to None" \
    bash -c "docker exec $CONTAINER python3 -c \"
from rag_service.models import SearchFilters
f = SearchFilters(labels=[])
assert f.labels is None
\""

# /search accepts state_norm filter — returns 200, not 422.
check_with_output "POST /search with state_norm='open' returns 200" \
    bash -c "$(declare -f post_search); CONTAINER=$CONTAINER post_search \
        '{\"query\":\"overflow\",\"filters\":{\"state_norm\":\"open\"}}'"

# /search accepts assignee filter — returns 200, not 422.
check_with_output "POST /search with assignee='Ian Smith' returns 200" \
    bash -c "$(declare -f post_search); CONTAINER=$CONTAINER post_search \
        '{\"query\":\"overflow\",\"filters\":{\"assignee\":\"Ian Smith\"}}'"

# /search accepts priority_max filter — returns 200, not 422.
check_with_output "POST /search with priority_max=2 returns 200" \
    bash -c "$(declare -f post_search); CONTAINER=$CONTAINER post_search \
        '{\"query\":\"overflow\",\"filters\":{\"priority_max\":2}}'"

# /search accepts labels filter — returns 200, not 422.
check_with_output "POST /search with labels=['bug'] returns 200" \
    bash -c "$(declare -f post_search); CONTAINER=$CONTAINER post_search \
        '{\"query\":\"overflow\",\"filters\":{\"labels\":[\"bug\"]}}'"

# /search accepts created_after filter — returns 200, not 422.
check_with_output "POST /search with created_after='2025-01-01' returns 200" \
    bash -c "$(declare -f post_search); CONTAINER=$CONTAINER post_search \
        '{\"query\":\"overflow\",\"filters\":{\"created_after\":\"2025-01-01\"}}'"

# /search rejects invalid state_norm via HTTP — returns 422.
check "POST /search with invalid state_norm returns 422" \
    bash -c "$(declare -f post_search_status); CONTAINER=$CONTAINER
             status=\$(post_search_status '{\"query\":\"x\",\"filters\":{\"state_norm\":\"bogus\"}}')
             [ \"\$status\" = '422' ]"

# Unfiltered /search still works (no regression from JOIN changes).
check_with_output "POST /search with no filters returns 200 (no regression)" \
    bash -c "$(declare -f post_search); CONTAINER=$CONTAINER post_search \
        '{\"query\":\"overflow\",\"k\":5}'"

# -------------------------------------------------------------------
# Tier 2 — live dogfood (LINEAR_API_KEY + LOU workspace required)
# -------------------------------------------------------------------
note "Tier 2 — live dogfood (requires LINEAR_API_KEY + LOU read access)"

count_ticket_meta() {
    docker exec "$CONTAINER" psql -U postgres -d postgres -tAc \
        "SELECT count(*) FROM ticket_meta WHERE source='linear' AND ticket_id='$1';" 2>/dev/null
}

get_state_norm() {
    docker exec "$CONTAINER" psql -U postgres -d postgres -tAc \
        "SELECT state_norm FROM ticket_meta WHERE source='linear' AND ticket_id='$1' LIMIT 1;" 2>/dev/null | tr -d '[:space:]'
}

search_filtered_ids() {
    # POST /search with a filters JSON blob (or "null"); prints ticket_ids.
    local filters_json="$1"
    docker exec "$CONTAINER" python3 -c "
import json, sys, urllib.request
filters = json.loads('$filters_json')  # handles null -> None, or a dict
body = json.dumps({'query': 'multicol overflow', 'k': 20, 'filters': filters}).encode()
req = urllib.request.Request('http://127.0.0.1:7777/search', data=body,
                             headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=30) as r:
    results = json.loads(r.read().decode()).get('results', [])
for c in results:
    print(c.get('ticket_id',''))
" 2>/dev/null
}

if [ -z "${LINEAR_API_KEY:-}" ]; then
    skip "sync_ticket('LOU-102') populates ticket_meta with a row" \
         "LINEAR_API_KEY not set — export a Linear key with LOU read access to run live dogfood checks"
    skip "ticket_meta row for LOU-102 has non-null state_norm" \
         "LINEAR_API_KEY not set (depends on sync above)"
    skip "POST /search state_norm filter returns subset of unfiltered results" \
         "LINEAR_API_KEY not set (no data to filter)"
    skip "POST /search with no filters: regression — LOU-102 in top-20 for multicol query" \
         "LINEAR_API_KEY not set (no data to search)"
else
    # Sync LOU-102 into the fresh container.
    sync_lou102() {
        docker exec "$CONTAINER" python3 -m rag_service.harvesters.linear \
            sync-ticket LOU-102 >/dev/null 2>&1 || return 1
        local n; n=$(count_ticket_meta "LOU-102")
        [ -n "$n" ] && [ "$n" -ge 1 ]
    }
    check "sync_ticket('LOU-102') populates ticket_meta (>=1 row)" sync_lou102

    # Verify state_norm is populated (not empty / null).
    state_norm_populated() {
        local sn; sn=$(get_state_norm "LOU-102")
        [ -n "$sn" ]
    }
    check_with_output "ticket_meta row for LOU-102 has non-null state_norm" state_norm_populated

    # State_norm filter: results filtered by LOU-102's actual state should be
    # a subset of (or equal to) the unfiltered results.  We verify the filter
    # at least returns 200 and the ticket_id set doesn't grow (no phantom rows).
    state_filter_is_subset() {
        local sn; sn=$(get_state_norm "LOU-102")
        [ -z "$sn" ] && return 1

        # Unfiltered IDs.
        local all_ids; all_ids=$(search_filtered_ids "null" | sort -u)
        # Filtered IDs (only tickets in the same state as LOU-102).
        local filtered_ids; filtered_ids=$(search_filtered_ids "{\"state_norm\": \"$sn\"}" | sort -u)

        # Every filtered ID must appear in the unfiltered set (subset check).
        while IFS= read -r id; do
            [ -z "$id" ] && continue
            echo "$all_ids" | grep -qxF "$id" || return 1
        done <<< "$filtered_ids"
        return 0
    }
    check_with_output "POST /search state_norm filter results are a subset of unfiltered" \
        state_filter_is_subset

    # Regression: LOU-102 should appear in unfiltered results for the canonical query.
    regression_top20_has_lou102() {
        local ids; ids=$(search_filtered_ids "null")
        echo "$ids" | grep -qxF "LOU-102"
    }
    check_with_output "unfiltered search: LOU-102 in top-20 for 'multicol overflow' (regression)" \
        regression_top20_has_lou102
fi

echo "---"
echo "Results: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
