#!/usr/bin/env bash
#
# router/verify.sh — the D9 acceptance test for the Phase-1 metering router.
#
# This IS the acceptance test: its exit code is the assertion. It builds the
# binary, starts it on a free loopback port with the committed prices.toml, then
# runs against it:
#
#   (b) the D9 verification proper — a REAL headless agent session launched
#       through the router with the pre-pointed recipe (ANTHROPIC_BASE_URL +
#       X-Slopstop-Run / X-Slopstop-Ticket headers). This is what D9 requires:
#       it exercises the env-based coverage recipe the fleet depends on. The
#       session authenticates with whatever `claude` is logged in with — a Claude
#       subscription (`/login`, OAuth) flows through the custom ANTHROPIC_BASE_URL
#       unchanged, so NO api key is needed for it.
#   (a) an OPTIONAL curl smoke request to /v1/messages carrying the tagging
#       headers. It hand-builds a request and so needs an api key (x-api-key), so
#       it runs only when ANTHROPIC_API_KEY is present; without one the D9 agent
#       session alone is the verification.
#
# It then queries GET /spend?prefix=<PREFIX> and asserts the run was metered.
#
# Requires an authenticated `claude` (subscription via `/login`, or an api key).
# No key is hardcoded. The captured /spend JSON is written under gitignored
# scratch/ as the verification record — never committed.
#
set -uo pipefail

# ---- config -------------------------------------------------------------------
PREFIX="SOP"
TICKET="${PREFIX}-0"
RUN_ID="verify-router-e2e"
HOST="127.0.0.1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
ROOT="$(dirname "$(git rev-parse --git-common-dir)")"
RUN_DIR="$ROOT/scratch/runs/$RUN_ID"

ROUTER_PID=""

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# ---- trap: always terminate the router we started, on every exit path ---------
cleanup() {
  if [[ -n "$ROUTER_PID" ]] && kill -0 "$ROUTER_PID" 2>/dev/null; then
    kill "$ROUTER_PID" 2>/dev/null
    wait "$ROUTER_PID" 2>/dev/null
  fi
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

# ---- preflight ----------------------------------------------------------------
command -v jq      >/dev/null 2>&1 || fail "jq is required"
command -v curl    >/dev/null 2>&1 || fail "curl is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required (free-port allocation)"
command -v claude >/dev/null 2>&1 || fail "claude CLI is required for the D9 agent session"

# Auth mode. The D9 agent session (check b) uses the CLI's own auth, so a Claude
# subscription (`/login`) is enough — no api key needed. The optional curl smoke
# (check a) hand-builds a request and needs an api key, so it runs only when
# ANTHROPIC_API_KEY is present. No key is hardcoded.
MIN_REQUESTS=1
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  SMOKE=1            # api-key mode: curl smoke + agent session
  MIN_REQUESTS=2
else
  SMOKE=""           # subscription/OAuth mode: agent session only
  echo "No ANTHROPIC_API_KEY set — using the claude CLI's own auth (e.g. /login);"
  echo "the api-key curl smoke is skipped, the live agent session is the D9 check."
fi

# Pick a free loopback port (ask the OS for an unused one).
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')" \
  || fail "could not allocate a free port"
BASE="http://$HOST:$PORT"

# ---- build + start ------------------------------------------------------------
echo "Building router..."
go build -o build/slopstop-router . || fail "go build failed"

echo "Starting router on $BASE ..."
./build/slopstop-router -port "$PORT" -prices prices.toml >/dev/null 2>&1 &
ROUTER_PID=$!

# Wait for /spend to answer (the only health surface — prefix-required probe).
ready=""
for _ in $(seq 1 50); do
  if curl -fsS -m 2 "$BASE/spend?prefix=$PREFIX" >/dev/null 2>&1; then ready=1; break; fi
  sleep 0.1
done
[[ -n "$ready" ]] || fail "router did not become ready on $BASE"

# ---- check (a): OPTIONAL curl smoke to /v1/messages with tagging headers -------
if [[ -n "$SMOKE" ]]; then
  echo "Smoke check: tagged curl to /v1/messages ..."
  smoke_status="$(curl -sS -o /dev/null -w '%{http_code}' -m 60 \
    -X POST "$BASE/v1/messages" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -H "X-Slopstop-Run: $RUN_ID" \
    -H "X-Slopstop-Ticket: $TICKET" \
    -d '{"model":"claude-haiku-4-5","max_tokens":16,"messages":[{"role":"user","content":"reply with the single word ok"}]}')" \
    || fail "smoke curl to /v1/messages failed to execute"
  [[ "$smoke_status" == "200" ]] || fail "smoke curl returned HTTP $smoke_status (expected 200)"
fi

# ---- check (b): the D9 verification — a real headless agent session -----------
echo "D9 check: live headless 'claude -p' through the router ..."
agent_log="$(mktemp)"
if ! ANTHROPIC_BASE_URL="$BASE" \
     ANTHROPIC_CUSTOM_HEADERS=$'X-Slopstop-Run: '"$RUN_ID"$'\nX-Slopstop-Ticket: '"$TICKET" \
     claude -p 'reply with the single word ok' >"$agent_log" 2>&1; then
  echo "---- claude -p output ----" >&2
  cat "$agent_log" >&2
  echo "--------------------------" >&2
  rm -f "$agent_log"
  fail "headless 'claude -p' through the router failed (output above — a stale ANTHROPIC_AUTH_TOKEN/ANTHROPIC_API_KEY in the env can override /login)"
fi
rm -f "$agent_log"

# ---- query /spend and record the verification JSON ----------------------------
echo "Querying /spend?prefix=$PREFIX ..."
SPEND_JSON="$(curl -fsS -m 5 "$BASE/spend?prefix=$PREFIX")" \
  || fail "GET /spend?prefix=$PREFIX failed"

mkdir -p "$RUN_DIR"
printf '%s\n' "$SPEND_JSON" > "$RUN_DIR/spend-verification.json"
echo "Captured /spend JSON -> $RUN_DIR/spend-verification.json"
printf '%s\n' "$SPEND_JSON" | jq .

# ---- assertions ---------------------------------------------------------------
# At least the agent session must have metered (MIN_REQUESTS=1); with the api-key
# curl smoke also run, at least two (MIN_REQUESTS=2).
requests="$(printf '%s' "$SPEND_JSON" | jq -r '.requests')"
[[ "$requests" =~ ^[0-9]+$ ]] || fail "requests is not a number: $requests"
(( requests >= MIN_REQUESTS )) || fail "requests = $requests (expected >= $MIN_REQUESTS)"

# Real spend must be positive.
total_ok="$(printf '%s' "$SPEND_JSON" | jq -r '.total_usd > 0')"
if [[ "$total_ok" != "true" ]]; then
  # Distinguish "no traffic" from "traffic seen but usage unreadable". The meter
  # counts a response whose usage it cannot parse as unpriced.requests with zero
  # tokens — the usual cause is a response Content-Encoding the meter cannot decode
  # (it handles gzip and deflate; brotli/zstd are not supported).
  unpriced_reqs="$(printf '%s' "$SPEND_JSON" | jq -r '.unpriced.requests')"
  if (( requests > 0 )) && [[ "$unpriced_reqs" =~ ^[0-9]+$ ]] && (( unpriced_reqs > 0 )); then
    fail "total_usd is 0 but $requests request(s) were metered and $unpriced_reqs had unparseable usage — the router received the responses but could not read their token counts. Most likely their Content-Encoding is unsupported (the meter decodes gzip/deflate, not brotli/zstd)."
  fi
  fail "total_usd is not > 0"
fi

# The agent session's model must appear in by_model carrying a REAL tier.
# Assert positive membership in the four-tier set {small,medium,large,huge}.
# We deliberately do NOT write a negative check against the 'untagged' bucket
# (a run/ticket/prefix fallback, never a valid label): such a check would pass
# vacuously because 'untagged' is not one of the four labels above.
printf '%s' "$SPEND_JSON" \
  | jq -e 'any(.by_model[]; .tier=="small" or .tier=="medium" or .tier=="large" or .tier=="huge")' >/dev/null \
  || fail "no by_model entry carries a tier in {small,medium,large,huge}"

# by_ticket must contain the tagged ticket from the launch headers.
has_ticket="$(printf '%s' "$SPEND_JSON" | jq -r --arg t "$TICKET" 'has("by_ticket") and (.by_ticket | has($t))')"
[[ "$has_ticket" == "true" ]] || fail "by_ticket does not contain the tagged ticket $TICKET"

echo "PASS: router metered a live headless agent session (requests=$requests, ticket=$TICKET)."
