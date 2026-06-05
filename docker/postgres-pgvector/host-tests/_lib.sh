#!/usr/bin/env bash
# _lib.sh — shared helpers for host-side tests.
#
# SOURCE this file; do not execute it directly.
#
# Every test script must:
#   1. Resolve SCRIPT_DIR to its own directory.
#   2. Call assert_repo_root early.
#   3. Call require_container before making HTTP calls.
#   4. Call print_summary at the end and propagate its exit code.
#
# Usage:
#   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
#   . "$SCRIPT_DIR/_lib.sh"
#   assert_repo_root
#   require_container

PASS=0
FAIL=0
RAG_URL="${RAG_URL:-http://localhost:7777}"

# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

assert_repo_root() {
    # Sentinel: .project-conf.toml lives only at the repo root.
    if [ ! -f ".project-conf.toml" ]; then
        printf 'ERROR: must be run from the repo root (no .project-conf.toml found here).\n' >&2
        printf '       cd <repo-root> && bash %s\n' "$0" >&2
        exit 1
    fi
}

require_container() {
    # Fails fast with an actionable message if the RAG service is not up.
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" "$RAG_URL/healthz" 2>/dev/null)
    if [ "$status" != "200" ]; then
        printf 'ERROR: RAG service not reachable at %s (HTTP %s).\n' "$RAG_URL" "$status" >&2
        printf '       Start the container:  make rag-dev-start\n' >&2
        printf '       Or set:               RAG_URL=http://host:port\n' >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

note() { printf '  ----  %s\n' "$*"; }

# check NAME CMD [ARGS…]
# Runs CMD; PASS if it exits 0, FAIL otherwise.  Stdout/stderr suppressed.
check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then
        printf '  PASS  %s\n' "$name"
        PASS=$((PASS + 1))
    else
        printf '  FAIL  %s\n' "$name"
        FAIL=$((FAIL + 1))
    fi
}

# check_show NAME CMD [ARGS…]
# Like check() but prints the command output on failure.
check_show() {
    local name="$1"; shift
    local out rc
    out=$("$@" 2>&1); rc=$?
    if [ $rc -eq 0 ]; then
        printf '  PASS  %s\n' "$name"
        PASS=$((PASS + 1))
    else
        printf '  FAIL  %s\n' "$name"
        printf '        %s\n' "$out"
        FAIL=$((FAIL + 1))
    fi
}

# curl_json URL METHOD BODY → stdout = response body; exits non-zero on non-2xx.
curl_json() {
    local url="$1" method="${2:-GET}" body="${3:-}"
    if [ -n "$body" ]; then
        curl -s -f -X "$method" "$url" \
            -H "Content-Type: application/json" \
            --data-raw "$body"
    else
        curl -s -f "$url"
    fi
}

# curl_status URL METHOD BODY → stdout = HTTP status code only.
curl_status() {
    local url="$1" method="${2:-GET}" body="${3:-}"
    if [ -n "$body" ]; then
        curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json" \
            --data-raw "$body"
    else
        curl -s -o /dev/null -w "%{http_code}" "$url"
    fi
}

print_summary() {
    printf -- '---\n'
    printf 'Results: %d passed, %d failed\n' "$PASS" "$FAIL"
    [ "$FAIL" -gt 0 ] && return 1 || return 0
}
