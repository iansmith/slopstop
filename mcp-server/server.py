"""
slopstop RAG MCP server — BILL-50

Exposes the slopstop RAG service (POST /search, GET /healthz) as MCP tools
for Claude Code. Runs as a stdio server; Claude Code launches it automatically
via .mcp.json at the project root.

Configuration
-------------
RAG_SERVICE_URL   Base URL of the running RAG container.
                  Default: http://localhost:7777

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

mcp = FastMCP(
    "slopstop-rag",
    instructions=(
        "Semantic search over the slopstop/LOU ticket corpus. "
        "Call search_tickets with a natural-language query to retrieve "
        "ranked ticket chunks. Use rag_health to check whether the "
        "RAG dev container is running before a search."
    ),
)


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

    try:
        resp = httpx.post(f"{RAG_URL}/search", json=body, timeout=30.0)
        resp.raise_for_status()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach RAG service at {RAG_URL}. "
            "Is the slopstop-rag-dev container running? "
            "Start it with: make rag-dev-start"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"RAG service returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"RAG request failed ({RAG_URL}/search): {exc}"
        ) from exc

    return resp.json()["results"]


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
# entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
