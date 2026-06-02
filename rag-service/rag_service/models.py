"""Pydantic request/response models for the rag-service query API.

Shapes match design/ticket-rag.md § Query API → POST /search exactly.
These are the validation + serialization boundary for the HTTP layer;
keep business logic out of here (see design/rag-service-testing.md Rule 4
— type-annotate everything that crosses a boundary).

Pydantic v2 (ships with fastapi==0.115.6).
"""

from __future__ import annotations

from pydantic import BaseModel


class SearchFilters(BaseModel):
    """Optional retrieval filters. All fields optional; an unset field means
    "no constraint on this dimension" (default = all).

    Mirrors design/ticket-rag.md: `source`/`provenance`/`kind` are lists
    (match-any), `ticket_id`/`project` are single strings (exact match).

    Metadata filters (BILL-51) join against ticket_meta table:
    `assignee`, `state_norm`, `priority_max`, `labels`, `created_after`,
    `updated_after`.
    """

    source: list[str] | None = None
    provenance: list[str] | None = None
    kind: list[str] | None = None
    ticket_id: str | None = None
    project: str | None = None
    # --- metadata filters added in BILL-51 ---
    assignee: str | None = None          # ILIKE match on ticket_meta.assignee
    state_norm: str | None = None        # exact: 'open'|'in_progress'|'done'|'canceled'
    priority_max: int | None = None      # include tickets with priority_num <= this
    labels: list[str] | None = None      # any-of: ticket has at least one of these labels
    created_after: str | None = None     # ISO date string, e.g. "2025-01-01"
    updated_after: str | None = None     # ISO date string


class SearchRequest(BaseModel):
    """POST /search (and POST /search_note) request body.

    `project` — if non-empty after stripping whitespace, restricts results to
    that project only (e.g. "LOU", "BILL", "PLTF"). Case-insensitive: the
    endpoint normalises to uppercase before filtering. Empty string means all
    projects (default).

    `query` is required. `k` caps the RESPONSE length; Stage-1 dense
    retrieval is separately capped at db.STAGE1_TOP_K.
    """

    project: str = ""
    query: str
    k: int = 10
    filters: SearchFilters | None = None
    rerank: bool = True


class Chunk(BaseModel):
    """A single retrieval result. Subset of the `ticket_chunks` columns
    (design/ticket-rag.md § Data model) plus the computed relevance `score`.

    `score` is cosine similarity (1 - cosine_distance) after Stage-1, then
    overwritten with the reranker score when rerank=true. Higher = more
    relevant either way.
    """

    id: int
    text: str
    score: float
    source: str
    provenance: str
    kind: str
    ticket_id: str
    seq: int | None = None
    author: str | None = None


class SearchResponse(BaseModel):
    """POST /search response body: ranked chunks, most-relevant first."""

    results: list[Chunk]
