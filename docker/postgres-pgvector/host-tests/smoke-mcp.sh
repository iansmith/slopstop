#!/usr/bin/env bash
# smoke-mcp.sh — Test the MCP server's code-graph tool path end-to-end.
#
# Exercises the exact HTTP + response-parsing pattern that mcp-server/server.py
# uses (httpx.post → resp.raise_for_status() → resp.json()["results"]).  This
# catches bugs in server.py that wouldn't be visible from raw curl tests, such
# as wrong key names, missing error handling, or unexpected return shapes.
#
# Requires: python3 with httpx (httpx is a direct dependency of mcp-server/).
#
# Usage (from repo root):
#   bash docker/postgres-pgvector/host-tests/smoke-mcp.sh
#   RAG_URL=http://other-host:7777 bash docker/postgres-pgvector/host-tests/smoke-mcp.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

assert_repo_root
require_container

echo "smoke-mcp — MCP server.py code path against $RAG_URL"
echo "---"

# Delegate to the standalone Python test script.  It reads RAG_URL from env
# and prints its own "Results: N passed, M failed" summary.
export RAG_URL
exec python3 "$SCRIPT_DIR/smoke-mcp.py"
