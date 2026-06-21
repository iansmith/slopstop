"""
slopstop RAG MCP server — BILL-50

Exposes the slopstop RAG service (POST /search, GET /healthz) as MCP tools
for Claude Code. Runs as a stdio server; Claude Code launches it automatically
via .mcp.json at the project root.

Configuration
-------------
RAG_SERVICE_URL   Base URL of the running RAG container.
                  Default: http://localhost:7777
CODE_GRAPH_REPO   Default repository scope for graph query tools.
                  Example: "iansmith/slopstop". Omit to query all ingested repos.

Usage
-----
Normally started automatically by Claude Code via .mcp.json.
To test manually:

    python3 mcp-server/server.py
    # then type MCP JSON-RPC messages on stdin
"""

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

RAG_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:7777").rstrip("/")
DEFAULT_REPO = os.environ.get("CODE_GRAPH_REPO", "")
"""Default repo scope for graph query tools (e.g. "iansmith/slopstop").
Set to restrict results to one repo; leave empty to query all ingested repos."""

mcp = FastMCP(
    "slopstop-rag",
    instructions=(
        "Semantic search over the slopstop/LOU ticket corpus. "
        "Call search_tickets with a natural-language query to retrieve "
        "ranked ticket chunks. Use rag_health to check whether the "
        "RAG dev container is running before a search."
    ),
)


def _rag_post(path: str, body: dict[str, Any]) -> httpx.Response:
    """POST to the RAG service and raise RuntimeError on any failure."""
    url = f"{RAG_URL}/{path}"
    try:
        resp = httpx.post(url, json=body, timeout=30.0)
        resp.raise_for_status()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach RAG service at {RAG_URL}. "
            "Is the slopstop-rag-dev container running? "
            "Start it with: make rag-dev-start"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"RAG service returned {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"RAG request failed ({url}): {exc}") from exc
    return resp


# ---------------------------------------------------------------------------
# search_tickets
# ---------------------------------------------------------------------------

@mcp.tool()
def search_tickets(
    query: str,
    project: str = "",
    k: int = 10,
    rerank: bool = True,
    source: list[str] | None = None,
    provenance: list[str] | None = None,
    kind: list[str] | None = None,
    ticket_id: str | None = None,
    # --- metadata filters added in BILL-51 ---
    assignee: str | None = None,
    state_norm: str | None = None,
    priority_max: int | None = None,
    labels: list[str] | None = None,
    created_after: str | None = None,
    updated_after: str | None = None,
) -> list[dict[str, Any]]:
    """Search the slopstop ticket corpus using semantic similarity.

    Returns up to `k` ranked chunks, most-relevant first. Each chunk
    contains: id, text, score, source, provenance, kind, ticket_id,
    seq (optional), author (optional).

    Args:
        query:      Natural-language search query (required).
        project:    Restrict to one project prefix, e.g. "LOU" or "BILL".
                    Empty string (default) searches all projects.
        k:          Maximum number of results to return (default 10).
        rerank:     Enable cross-encoder reranking for higher precision
                    (default True; set False for faster but coarser results).
        source:     Filter by source list, e.g. ["linear"]. None = all.
        provenance: Filter by provenance list, e.g. ["upstream"]. None = all.
        kind:       Filter by chunk kind, e.g. ["description", "comment"].
                    None = all.
        ticket_id:  Filter to a single ticket, e.g. "LOU-94". None = all.
        assignee:       Filter to tickets assigned to this person, e.g. "Ian Smith".
        state_norm:     Filter by ticket state: 'open', 'in_progress', 'done', 'canceled'.
        priority_max:   Maximum priority to include: 1=urgent only, 2=urgent+high,
                        3=+medium, 4=all. None = all priorities.
        labels:         Filter to tickets with at least one of these labels,
                        e.g. ["bug", "regression"].
        created_after:  Only include tickets created after this ISO date,
                        e.g. "2025-01-01".
        updated_after:  Only include tickets updated after this ISO date.

    Results may include rows with ``kind='docstring'`` that have a ``moniker``
    field populated — these represent code symbols whose docstrings matched the
    query. Use ``get_code_context(monikers=[result['moniker']])`` to follow up
    on those results and discover which tickets are responsible for each
    function. To exclude docstring hits entirely, pass
    ``kind=['description', 'comment']``.

    Usage examples:
        search_tickets(query="tree data structure", assignee="Ian Smith", state_norm="open")
        search_tickets(query="paint layer overflow", state_norm="in_progress", priority_max=2)
        search_tickets(query="border radius", labels=["bug"], created_after="2025-06-01")
        search_tickets(query="nested multicol", state_norm="open", assignee="Ian Smith", k=5)
    """
    filters: dict[str, Any] | None = None
    if any(v is not None for v in (source, provenance, kind, ticket_id,
                                    assignee, state_norm, priority_max, labels,
                                    created_after, updated_after)):
        filters = {}
        if source is not None:
            filters["source"] = source
        if provenance is not None:
            filters["provenance"] = provenance
        if kind is not None:
            filters["kind"] = kind
        if ticket_id is not None:
            filters["ticket_id"] = ticket_id
        # metadata filters
        if assignee is not None:
            filters["assignee"] = assignee
        if state_norm is not None:
            filters["state_norm"] = state_norm
        if priority_max is not None:
            filters["priority_max"] = priority_max
        if labels is not None:
            filters["labels"] = labels
        if created_after is not None:
            filters["created_after"] = created_after
        if updated_after is not None:
            filters["updated_after"] = updated_after

    body: dict[str, Any] = {
        "query": query,
        "project": project,
        "k": k,
        "rerank": rerank,
    }
    if filters is not None:
        body["filters"] = filters

    return _rag_post("search", body).json()["results"]


# ---------------------------------------------------------------------------
# rag_health
# ---------------------------------------------------------------------------

@mcp.tool()
def rag_health() -> dict[str, str]:
    """Check whether the slopstop RAG service is up and healthy.

    Returns a dict with keys "postgres" and "schema", each "ok" when healthy.
    Raises a RuntimeError with a helpful message when the container is not
    running.
    """
    try:
        resp = httpx.get(f"{RAG_URL}/healthz", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach RAG service at {RAG_URL}. "
            "Start it with: make rag-dev-start"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"RAG service returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"RAG request failed ({RAG_URL}/healthz): {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# get_code_context
# ---------------------------------------------------------------------------

@mcp.tool()
def get_code_context(monikers: list[str]) -> list[dict[str, Any]]:
    """Get ticket linkage for one or more code symbols by SCIP moniker.

    For each moniker, traverses the code knowledge graph to find commits
    that touched that symbol (TOUCHES edges) and the tickets referenced
    in those commits.

    Use this after search_tickets returns results with kind='docstring' —
    pass the moniker field of those results here to discover which tickets
    are responsible for each function.

    Args:
        monikers: List of SCIP monikers from search_tickets docstring results.
                  Example: ["scip-go gomod iansmith/slopstop . slopstop/linesOverlap()."]

    Returns:
        List of dicts, one per moniker (only monikers with graph hits included):
        [
          {
            "moniker": "scip-go gomod ...",
            "repo": "iansmith/slopstop",
            "tickets": ["BILL-56", "BILL-55"],
            "commits": [
              {"sha": "abc123...", "subject": "[BILL-56] ...", "authored_at": "2026-..."}
            ]
          },
          ...
        ]
    """
    body = {"monikers": monikers}
    return _rag_post("code-graph/context", body).json()["results"]


# ---------------------------------------------------------------------------
# Graph query tools (BILL-58)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_callers(
    moniker: str,
    repo: str = DEFAULT_REPO,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return functions that directly call the given SCIP moniker.

    Traverses CALLS edges in the code knowledge graph: (caller)-[:CALLS]->(target).

    Use after search_tickets returns results with kind='docstring' — pass the moniker
    field to find which functions call that symbol.

    Args:
        moniker: SCIP moniker of the target function/method.
                 Example: "scip-go gomod iansmith/slopstop . slopstop/linesOverlap()."
        repo: Repository to restrict results to (e.g. "iansmith/slopstop").
              Defaults to CODE_GRAPH_REPO env var; empty string queries all repos.
        limit: Maximum results to return (1–200, default 50).

    Returns:
        List of dicts: [{moniker, file_path, line, location, lang, repo, external}, ...]
        location is "file_path:line" for quick navigation. external=True for stdlib stubs.
    """
    body = {"moniker": moniker, "repo": repo, "limit": limit}
    return _rag_post("code-graph/callers", body).json()["results"]


@mcp.tool()
def get_implementors(
    moniker: str,
    repo: str = DEFAULT_REPO,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return functions/types that implement the given interface moniker.

    Traverses IMPLEMENTS edges: (implementor)-[:IMPLEMENTS]->(target).

    Args:
        moniker: SCIP moniker of the target interface.
        repo: Repository filter; defaults to CODE_GRAPH_REPO env var.
        limit: Maximum results (1–200, default 50).

    Returns:
        List of dicts: [{moniker, file_path, line, location, lang, repo, external}, ...]
    """
    body = {"moniker": moniker, "repo": repo, "limit": limit}
    return _rag_post("code-graph/implementors", body).json()["results"]


@mcp.tool()
def get_blast_radius(
    moniker: str,
    depth: int = 3,
    repo: str = DEFAULT_REPO,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return transitive callers of the given moniker up to `depth` hops.

    Traverses CALLS edges transitively: (caller)-[:CALLS*1..depth]->(target).
    Use to estimate blast radius — everything that would break if this function changes.

    Args:
        moniker: SCIP moniker of the target function.
        depth: Transitive hop limit (1–5, default 3). Higher values are slower.
        repo: Repository filter; defaults to CODE_GRAPH_REPO env var.
        limit: Maximum results (1–200, default 50).

    Returns:
        List of dicts: [{moniker, file_path, line, location, lang, repo, external}, ...]
        Results may include indirect callers across multiple hops.
    """
    body = {"moniker": moniker, "depth": depth, "repo": repo, "limit": limit}
    return _rag_post("code-graph/blast-radius", body).json()["results"]


@mcp.tool()
def get_ticket_code(
    ticket_id: str,
    repo: str = DEFAULT_REPO,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return functions touched by commits that reference the given ticket ID.

    Reverse of get_code_context: given a ticket ID, find what code it changed.
    Traverses: (Commit where ticket_id IN ticket_ids)-[:TOUCHES]->(function).

    Use to understand the blast radius of a specific ticket, or to navigate
    from a ticket reference in search_tickets results to the affected code.

    Args:
        ticket_id: Ticket ID to look up (e.g. "BILL-56", "MAZ-42").
        repo: Repository filter; defaults to CODE_GRAPH_REPO env var.
        limit: Maximum results (1–200, default 50).

    Returns:
        List of dicts: [{moniker, file_path, line, location, lang, repo, external}, ...]
        Returns empty list if the ticket ID is not found in any commit.
    """
    body = {"ticket_id": ticket_id, "repo": repo, "limit": limit}
    return _rag_post("code-graph/ticket-code", body).json()["results"]


# ---------------------------------------------------------------------------
# Code quality tools (BILL-104)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_dead_candidates(
    repo: str = DEFAULT_REPO,
    cc_threshold: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return Function vertices with no incoming CALLS edges, ranked by cyclomatic complexity.

    Each candidate is classified as likely_dead or possibly_dead:
    - likely_dead: no callers, no IMPLEMENTS edge, name not an entry-point pattern
      (main, init, handler, cli).
    - possibly_dead: no callers but has an IMPLEMENTS edge OR name matches an
      entry-point pattern (may be called by an external caller not in the graph).

    Use to find dead code that should be cleaned up, or to focus review attention
    on the highest-complexity uncalled functions.

    Args:
        repo: Repository filter (e.g. "iansmith/slopstop"). Defaults to
              CODE_GRAPH_REPO env var; empty string queries all ingested repos.
        cc_threshold: Minimum cyclomatic complexity to include (default 0 = all
                      functions with CC data).
        limit: Maximum results (1–200, default 50).

    Returns:
        List of dicts: [{moniker, file_path, cyclomatic_complexity, has_implements,
        confidence}, ...], sorted by cyclomatic_complexity descending.
    """
    body: dict[str, Any] = {
        "repo": repo,
        "cc_threshold": cc_threshold,
        "limit": limit,
    }
    return _rag_post("code-graph/dead-candidates", body).json()["candidates"]


@mcp.tool()
def get_callers_with_cc(
    moniker: str,
    repo: str = DEFAULT_REPO,
    limit: int = 50,
) -> dict[str, Any]:
    """Return callers of a given moniker, each annotated with cyclomatic complexity.

    Also returns the target function's own CC as target_cc. Use to understand
    the complexity of code that depends on a symbol, e.g. when evaluating a
    refactor risk or reviewing a PR that touches a high-CC function.

    Args:
        moniker: SCIP moniker of the target function.
                 Example: "scip-python ... linesOverlap()."
        repo: Repository filter. Defaults to CODE_GRAPH_REPO env var.
        limit: Maximum callers to return (1–200, default 50).

    Returns:
        Dict with two keys:
          target_cc: int | None — CC of the target function (None if not found or no CC data).
          callers: list of {moniker, file_path, cyclomatic_complexity, test} — each
                   caller with its own CC and a flag indicating it comes from a test file.
    """
    body: dict[str, Any] = {"moniker": moniker, "repo": repo, "limit": limit}
    return _rag_post("code-graph/callers-with-cc", body).json()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
