#!/usr/bin/env bash
# run-harvester.sh — Run ingest_commits.py against the live dev container and
#                    verify it reports commits merged.
#
# The harvester mines the git log for [BILL-N] commit messages, extracts per-
# file diff stats, and POSTs them to /code-graph/ingest-commits.  Running it
# populates Commit vertices and TOUCHES edges so that ticket-code queries
# return real results.
#
# The MERGE statements are idempotent — re-running after data already exists
# is safe and still exits 0.
#
# Usage (from repo root):
#   bash docker/postgres-pgvector/host-tests/run-harvester.sh
#   RAG_URL=http://other-host:7777 bash docker/postgres-pgvector/host-tests/run-harvester.sh
#   SINCE_SHA=abc123 bash docker/postgres-pgvector/host-tests/run-harvester.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

assert_repo_root
require_container

echo "run-harvester — ingest commits into $RAG_URL"
echo "---"

# Optional: only process commits reachable after SINCE_SHA (exclusive).
SINCE_SHA="${SINCE_SHA:-}"

# ---------------------------------------------------------------------------
# Run the harvester
# ---------------------------------------------------------------------------

note "Running ingest_commits.py (prefix=BILL, repo=iansmith/slopstop)"

HARVESTER_ARGS=(
    --repo iansmith/slopstop
    --prefix BILL
    --git-dir ..
    --rag-url "$RAG_URL"
)
[ -n "$SINCE_SHA" ] && HARVESTER_ARGS+=(--since-sha "$SINCE_SHA")

# The script lives under rag-service/ and uses relative imports, so run it
# from that subdirectory.  --git-dir .. points back to the repo root.
HARVESTER_OUT=$(
    cd rag-service
    python3 -m scripts.ingest_commits "${HARVESTER_ARGS[@]}" 2>&1
)
HARVESTER_RC=$?

echo "$HARVESTER_OUT"

# ---------------------------------------------------------------------------
# Verify harvester completed successfully
# ---------------------------------------------------------------------------

note "Verifying harvester output"

_harvester_exit_ok() { [ "$HARVESTER_RC" -eq 0 ]; }

_harvester_found_commits() {
    # stderr: "Found N ticket-referenced commits. Ingesting..."
    echo "$HARVESTER_OUT" | grep -qE 'Found [1-9][0-9]* ticket-referenced commit'
}

_harvester_done_line_present() {
    # stdout: "Done: N commits, M TOUCHES edges merged."
    echo "$HARVESTER_OUT" | grep -qE 'Done: [0-9]+ commits'
}

_harvester_nonzero_commits() {
    # "Done: 0 commits" means every commit lacked file changes — suspicious.
    echo "$HARVESTER_OUT" | grep -qE 'Done: [1-9][0-9]* commits'
}

check "harvester exited 0"                      _harvester_exit_ok
check "harvester found ticket-referenced commits" _harvester_found_commits
check "harvester printed Done: line"             _harvester_done_line_present
check "harvester merged at least 1 commit"       _harvester_nonzero_commits

# ---------------------------------------------------------------------------
# Spot-check: ticket-code now returns results for a known-committed ticket.
# BILL-56 has commits that touched source files; if the graph has no Function
# vertices yet (no SCIP ingest), TOUCHES edges won't exist — this probe is
# informational and does not count as a failure.
# ---------------------------------------------------------------------------

note "Spot-check: POST /code-graph/ticket-code {ticket_id: BILL-56}"
TICKET_RESP=$(curl_json "$RAG_URL/code-graph/ticket-code" POST \
    '{"ticket_id":"BILL-56","repo":"iansmith/slopstop"}' 2>/dev/null)
if [ -n "$TICKET_RESP" ]; then
    COUNT=$(echo "$TICKET_RESP" | python3 -c \
        "import sys,json; print(len(json.load(sys.stdin).get('results',[])))" 2>/dev/null)
    if [ "${COUNT:-0}" -gt 0 ]; then
        printf '  INFO  ticket-code BILL-56 → %d result(s) (TOUCHES edges present)\n' "$COUNT"
    else
        printf '  INFO  ticket-code BILL-56 → 0 results (expected until SCIP ingest runs)\n'
    fi
fi

print_summary
