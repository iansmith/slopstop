#!/usr/bin/env python3
"""smoke-mcp.py — Test the MCP server's code-graph tool path end-to-end.

Replicates the exact httpx call pattern from mcp-server/server.py and
verifies response handling for the four BILL-58 MCP tools.

Invoked by smoke-mcp.sh (which provides assert_repo_root / require_container
guards and the RAG_URL env var).  Can also be run directly:

    RAG_URL=http://localhost:7777 python3 docker/postgres-pgvector/host-tests/smoke-mcp.py

If the graph is empty (harvester hasn't run) the tools return [] — expected
behaviour, not a failure.  Schema checks are vacuous on empty result sets.
"""

import os
import sys

try:
    import httpx
except ImportError:
    print("  SKIP  httpx not available; install mcp-server/requirements.txt")
    sys.exit(0)

RAG_URL = os.environ.get("RAG_URL", "http://localhost:7777").rstrip("/")
REPO = "iansmith/slopstop"
REQUIRED_KEYS = {"moniker", "file_path", "line", "location", "lang", "repo", "external"}

pass_count = 0
fail_count = 0


def ok(name: str) -> None:
    global pass_count
    print(f"  PASS  {name}")
    pass_count += 1


def fail(name: str, reason: str = "") -> None:
    global fail_count
    msg = f"  FAIL  {name}"
    if reason:
        msg += f"\n        {reason}"
    print(msg)
    fail_count += 1


def _call_tool(path: str, body: dict) -> list | None:
    """POST to path with body; return results list or None on any error.

    Absorbs the three exception types that mcp-server/server.py handles:
    ConnectError, HTTPStatusError, and JSON/key parsing errors.  On error,
    records a FAIL and returns None so callers can skip their assertion.
    """
    try:
        resp = httpx.post(f"{RAG_URL}{path}", json=body, timeout=30.0)
        resp.raise_for_status()
        return resp.json()["results"]
    except httpx.ConnectError as exc:
        fail(f"{path}: ConnectError (container down?)", str(exc))
    except httpx.HTTPStatusError as exc:
        fail(f"{path}: unexpected HTTP error",
             f"{exc.response.status_code}: {exc.response.text}")
    except (KeyError, ValueError) as exc:
        fail(f"{path}: response parsing error", str(exc))
    return None


def _assert_422(path: str, body: dict, label: str) -> None:
    """Assert that POST path with body returns HTTP 422 (validation gate)."""
    try:
        resp = httpx.post(f"{RAG_URL}{path}", json=body, timeout=30.0)
        resp.raise_for_status()
        fail(f"{label} should return 422 but got 200")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            ok(f"{label} raises HTTPStatusError(422)")
        else:
            fail(f"{label} wrong status", str(exc.response.status_code))


def _check_results_shape(name: str, results: list) -> None:
    """Verify results is a list; if non-empty, each row must have REQUIRED_KEYS."""
    if not isinstance(results, list):
        fail(name, f"'results' is not a list: {type(results)}")
        return
    for row in results:
        missing = REQUIRED_KEYS - set(row.keys())
        if missing:
            fail(name, f"result row missing keys {missing}: {row}")
            return
    ok(name)


# ---------------------------------------------------------------------------
# Tool: get_callers
# ---------------------------------------------------------------------------
print("  ----  get_callers")
results = _call_tool(
    "/code-graph/callers",
    {"moniker": "scip-go gomod slopstop . slopstop/nonexistent().", "repo": REPO, "limit": 50},
)
if results is not None:
    _check_results_shape("get_callers: returns list with correct schema", results)

_assert_422(
    "/code-graph/callers",
    {"moniker": "x", "repo": REPO, "limit": 201},
    "get_callers: limit=201",
)

# ---------------------------------------------------------------------------
# Tool: get_implementors
# ---------------------------------------------------------------------------
print("  ----  get_implementors")
results = _call_tool(
    "/code-graph/implementors",
    {"moniker": "scip-go gomod slopstop . slopstop/NoSuchInterface#.", "repo": REPO, "limit": 50},
)
if results is not None:
    _check_results_shape("get_implementors: returns list with correct schema", results)

_assert_422(
    "/code-graph/implementors",
    {"moniker": "x", "repo": REPO, "limit": 201},
    "get_implementors: limit=201",
)

# ---------------------------------------------------------------------------
# Tool: get_blast_radius
# ---------------------------------------------------------------------------
print("  ----  get_blast_radius")
results = _call_tool(
    "/code-graph/blast-radius",
    {"moniker": "scip-go gomod slopstop . slopstop/nonexistent().", "depth": 3,
     "repo": REPO, "limit": 50},
)
if results is not None:
    _check_results_shape("get_blast_radius: returns list with correct schema", results)

_assert_422(
    "/code-graph/blast-radius",
    {"moniker": "x", "depth": 6, "repo": REPO},
    "get_blast_radius: depth=6",
)
_assert_422(
    "/code-graph/blast-radius",
    {"moniker": "x", "repo": REPO, "limit": 201},
    "get_blast_radius: limit=201",
)

# ---------------------------------------------------------------------------
# Tool: get_ticket_code
# ---------------------------------------------------------------------------
print("  ----  get_ticket_code")
results = _call_tool(
    "/code-graph/ticket-code",
    {"ticket_id": "BILL-XXXXXX", "repo": REPO, "limit": 50},
)
if results is not None:
    if results == []:
        ok("get_ticket_code: unknown ticket_id returns []")
    else:
        fail("get_ticket_code: unknown ticket should return []", f"got: {results}")

# If graph has data for BILL-56, schema-check its results too.
results = _call_tool(
    "/code-graph/ticket-code",
    {"ticket_id": "BILL-56", "repo": REPO, "limit": 5},
)
if results is not None:
    if results:
        _check_results_shape("get_ticket_code BILL-56: result schema correct", results)
    else:
        ok("get_ticket_code BILL-56: returned [] (no SCIP data yet — schema vacuously ok)")

_assert_422(
    "/code-graph/ticket-code",
    {"ticket_id": "x", "repo": REPO, "limit": 201},
    "get_ticket_code: limit=201",
)

# ---------------------------------------------------------------------------
# Tool: rag_health  (mirrors server.py: rag_health → GET /healthz)
# ---------------------------------------------------------------------------
print("  ----  rag_health")
try:
    resp = httpx.get(f"{RAG_URL}/healthz", timeout=5.0)
    resp.raise_for_status()
    d = resp.json()
    assert d.get("postgres") == "ok" and d.get("schema") == "ok", f"unexpected: {d}"
    ok("rag_health: returns {postgres:ok, schema:ok}")
except Exception as exc:
    fail("rag_health: unexpected error", str(exc))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("---")
print(f"Results: {pass_count} passed, {fail_count} failed")
sys.exit(0 if fail_count == 0 else 1)
