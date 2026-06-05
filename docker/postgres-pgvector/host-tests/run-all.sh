#!/usr/bin/env bash
# run-all.sh — Run all host-side tests in the correct order.
#
# Order matters:
#   1. smoke-http.sh  — verifies the host-facing port is reachable before any
#                        data is loaded (also re-runs cleanly after data exists).
#   2. run-harvester.sh — populates Commit + TOUCHES data from the git history.
#   3. smoke-mcp.sh   — exercises the server.py httpx call path; schema checks
#                        are meaningful only after the harvester has run.
#
# Usage (from repo root):
#   bash docker/postgres-pgvector/host-tests/run-all.sh
#   RAG_URL=http://other-host:7777 bash docker/postgres-pgvector/host-tests/run-all.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

assert_repo_root

TOTAL_PASS=0
TOTAL_FAIL=0

_run_suite() {
    local label="$1" script="$2"
    echo ""
    echo "════════════════════════════════════════"
    echo "  $label"
    echo "════════════════════════════════════════"
    bash "$script"
    local rc=$?
    # Each script exits 0 on all-pass, non-zero on any failure.
    # Accumulate the script-level result (not individual check counts).
    [ $rc -eq 0 ] && TOTAL_PASS=$((TOTAL_PASS + 1)) || TOTAL_FAIL=$((TOTAL_FAIL + 1))
    return $rc
}

_run_suite "smoke-http  (host-port HTTP)"          "$SCRIPT_DIR/smoke-http.sh"
_run_suite "run-harvester (commit ingest)"         "$SCRIPT_DIR/run-harvester.sh"
_run_suite "smoke-mcp  (server.py httpx path)"     "$SCRIPT_DIR/smoke-mcp.sh"
_run_suite "verify-bill59 (slopstop-ingest/hooks)" "$SCRIPT_DIR/verify-bill59.sh"

echo ""
echo "════════════════════════════════════════"
echo "  AGGREGATE"
echo "════════════════════════════════════════"
echo "Scripts: $TOTAL_PASS passed, $TOTAL_FAIL failed"
[ "$TOTAL_FAIL" -gt 0 ] && exit 1 || exit 0
