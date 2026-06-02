#!/usr/bin/env bash
# verify-bill52.sh — BILL-52 acceptance: Apache AGE graph extension coexists
# with pgvector in the single rag image, and a Cypher round-trip works.
#
# Usage:
#   bash docker/postgres-pgvector/verify-bill52.sh [IMAGE_TAG]
#
# Default IMAGE_TAG is slopstop-rag:latest (GREEN once BILL-52 is built).
# To see the RED baseline, run against any pre-BILL-52 image — checks 2-6
# fail there because age.so / the age extension / code_graph do not exist:
#   bash docker/postgres-pgvector/verify-bill52.sh slopstop-rag:<pre-age-sha>
#
# All probes go via `docker exec` (no host port publishing), so the script
# does not conflict with other containers bound to host 7777/5432.
#
# READINESS — why we wait on the "Uvicorn running" log line and probe over
# -h 127.0.0.1 (NOT the Unix socket): on a fresh volume the upstream image
# runs initdb behind a TEMPORARY server that listens on the socket only.
# A socket SELECT 1 therefore succeeds DURING initdb, before entrypoint.sh
# applies any schema/*.sql and before the real TCP server is up. entrypoint.sh
# gates on `-h 127.0.0.1` for exactly this reason, and logs "Uvicorn running"
# only AFTER all schema (incl. 004_age.sql) has been applied. So that log line
# is our single reliable "everything is ready" signal.

set -u

IMAGE="${1:-slopstop-rag:latest}"
CONTAINER="ticket-rag-bill52-verify"
DATA_DIR=$(mktemp -d -t bill52-pgdata.XXXXXX)
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

# Count completed boots by the entrypoint's post-schema uvicorn banner.
uvicorn_count() { docker logs "$CONTAINER" 2>&1 | grep -c 'Uvicorn running on'; }

# Wait until the app has reported ready at least $1 times (1 = fresh boot,
# 2 = after a restart), bounded by $2 seconds. Returns 1 on timeout.
wait_uvicorn_ge() {
    local want="$1" timeout="${2:-60}"
    for _ in $(seq 1 "$timeout"); do
        [ "$(uvicorn_count)" -ge "$want" ] && return 0
        sleep 1
    done
    return 1
}

# Single-value psql probe over TCP: run SQL, trim whitespace, compare.
psql_eq() {
    local sql="$1" expected="$2" out
    out=$(docker exec "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tAc "$sql" \
          2>/dev/null | tr -d '[:space:]')
    [ "$out" = "$expected" ]
}

# Cypher round-trip: write two vertices + an edge, then match the edge back and
# confirm the property survives. Needs LOAD 'age' + search_path per session.
cypher_roundtrip_ok() {
    docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<'EOSQL' \
        | grep -q 'hello world from AGE'
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT * FROM cypher('code_graph', $$
  CREATE (g:Greeting {text: 'hello world from AGE'})-[:SPOKEN_BY]->(s:Service {name: 'slopstop-rag'})
  RETURN g
$$) AS (g agtype);
SELECT * FROM cypher('code_graph', $$
  MATCH (g:Greeting)-[:SPOKEN_BY]->(:Service)
  RETURN g.text
$$) AS (t agtype);
EOSQL
}

# pgvector distance op must still evaluate in a session that loaded AGE.
# psql echoes the LOAD and SET command tags as their own output lines, so take
# the LAST line (the SELECT result) rather than collapsing all output together.
pgvector_after_age_ok() {
    local out
    out=$(docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U postgres -d postgres -tA 2>/dev/null <<'EOSQL'
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector;
EOSQL
)
    [ "$(printf '%s\n' "$out" | tail -n1 | tr -d '[:space:]')" = "1" ]
}

# FAIL only on NON-benign fatal markers. Postgres logs the transient
# "the database system is starting up" / "not yet accepting connections" as
# FATAL when any client (incl. the entrypoint's own readiness probe) connects
# during the real server's startup window — that is expected, not a defect.
no_fatal_markers() {
    ! docker logs "$CONTAINER" 2>&1 \
        | grep -E -i '(FATAL|panic|^Traceback)' \
        | grep -v -i -e 'the database system is starting up' \
                     -e 'not yet accepting connections' \
        | grep -q .
}

echo "BILL-52 verification — image: $IMAGE"
echo "host data dir: $DATA_DIR"
echo "---"

note "Fresh-volume boot"
docker run -d \
    --name "$CONTAINER" \
    -v "$DATA_DIR:/var/lib/postgresql" \
    "$IMAGE" >/dev/null 2>&1

# Check 1 — app reaches ready (real TCP server up AND all schema applied,
# incl. 004_age.sql) within 60s on a fresh volume.
check "fresh-volume boot: app ready (uvicorn up, schema applied) within 60s" \
    wait_uvicorn_ge 1 60

# Check 2 — AGE extension installed.
check "age extension installed (pg_extension)" \
    psql_eq "SELECT 1 FROM pg_extension WHERE extname='age'" "1"

# Check 3 — pgvector extension still installed alongside AGE.
check "vector extension still installed (coexistence)" \
    psql_eq "SELECT 1 FROM pg_extension WHERE extname='vector'" "1"

# Check 4 — code_graph bootstrapped by schema/004_age.sql.
check "code_graph graph exists (ag_catalog.ag_graph)" \
    psql_eq "SELECT 1 FROM ag_catalog.ag_graph WHERE name='code_graph'" "1"

# Check 5 — the headline: a Cypher CREATE + MATCH round-trip works.
check "Cypher round-trip: create edge then match it back" \
    cypher_roundtrip_ok

# Check 6 — pgvector op still evaluates in a session that loaded AGE.
check "pgvector distance op works after LOAD 'age'" \
    pgvector_after_age_ok

# Check 7 — no non-benign fatal markers from either subsystem.
check "logs contain no non-benign FATAL / panic / Traceback markers" \
    no_fatal_markers

# Check 8 — idempotent re-apply: restart and confirm a clean second boot.
note "Reuse-volume restart (idempotent schema re-apply)"
restart_clean() {
    docker stop --time 15 "$CONTAINER" >/dev/null 2>&1 || return 1
    docker start "$CONTAINER" >/dev/null 2>&1 || return 1
    wait_uvicorn_ge 2 60
}
check "restart re-applies schema and reaches ready (idempotent 004_age.sql)" \
    restart_clean
check "second-boot logs contain no AGE schema apply ERROR lines" \
    bash -c "! docker logs --since=1m $CONTAINER 2>&1 | grep -E -i 'ERROR.*(age|code_graph|already exists)'"

# Diagnostics on failure (container is removed by the EXIT trap afterwards).
if [ "$FAIL" -gt 0 ]; then
    echo "--- container logs (tail 50) for debugging ---"
    docker logs --tail 50 "$CONTAINER" 2>&1 || true
fi

echo "---"
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
