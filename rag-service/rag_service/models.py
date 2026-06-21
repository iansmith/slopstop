"""Pydantic request/response models for the rag-service query API.

Shapes match design/ticket-rag.md § Query API → POST /search exactly.
These are the validation + serialization boundary for the HTTP layer;
keep business logic out of here (see design/rag-service-testing.md Rule 4
— type-annotate everything that crosses a boundary).

Pydantic v2 (ships with fastapi==0.115.6).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SearchFilters(BaseModel):
    """Optional retrieval filters. All fields optional; an unset field means
    "no constraint on this dimension" (default = all).

    Mirrors design/ticket-rag.md: `source`/`provenance`/`kind` are lists
    (match-any), `ticket_id`/`project` are single strings (exact match).

    Metadata filters (BILL-51) join against ticket_meta table:
    `assignee`, `state_norm`, `priority_max`, `labels`, `created_after`,
    `updated_after`. All validated at the request boundary so malformed
    values are rejected with a 422 rather than a cryptic SQL error.
    """

    source: list[str] | None = None
    provenance: list[str] | None = None
    kind: list[str] | None = None
    ticket_id: str | None = None
    project: str | None = None
    # --- metadata filters added in BILL-51 ---
    assignee: str | None = None
    state_norm: Literal["open", "in_progress", "done", "canceled"] | None = None
    priority_max: int | None = Field(default=None, ge=0, le=4)
    labels: list[str] | None = None
    # Stored as date objects; Pydantic accepts ISO strings ("2025-01-01") from JSON.
    created_after: date | None = None
    updated_after: date | None = None

    @field_validator("labels")
    @classmethod
    def _normalize_empty_labels(cls, value: list[str] | None) -> list[str] | None:
        """Coerce empty list to None so the meta JOIN is not triggered with a
        match-nothing array (labels && '{}'::text[] always returns false)."""
        return value or None


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
    moniker: str | None = None   # SCIP moniker; non-null for kind='docstring' rows
    repo: str | None = None      # repo identifier for scip rows, e.g. "iansmith/slopstop"


class SearchResponse(BaseModel):
    """POST /search response body: ranked chunks, most-relevant first."""

    results: list[Chunk]


class CodeGraphIngestRequest(BaseModel):
    """POST /code-graph/ingest request body.

    `repo` is the repository identifier (e.g. "iansmith/slopstop") added to
    every vertex so the single global `code_graph` supports multi-repo queries.

    `index` is the SCIP JSON index as a Python dict (snake_case field names,
    as produced by Python protobuf bindings or `scip print --json` decoded).

    `head_sha` is the git HEAD SHA at index time (optional). When provided the
    endpoint upserts a :Repo vertex with `last_indexed_sha = head_sha` so
    subsequent runs can skip re-indexing when HEAD is unchanged (BILL-59
    reconcile-on-start).

    `source_root` is the absolute path to the repository checkout (optional).
    When provided the ingest endpoint calls :func:`build_lizard_cc_map` to
    compute cyclomatic complexity for every Function node via lizard.  When
    absent (e.g. remote CI where source is unavailable) CC is omitted and any
    existing value is preserved by MERGE semantics.
    """

    repo: str
    index: dict
    head_sha: str | None = None
    source_root: str | None = None


class CodeGraphIngestResponse(BaseModel):
    """POST /code-graph/ingest response body."""

    vertices_merged: int
    edges_merged: int
    docstring_rows: int = 0
    last_indexed_sha: str | None = None


class RepoStatusResponse(BaseModel):
    """GET /code-graph/repo/{repo_id} response body.

    Returns the stored ``last_indexed_sha`` for the repository, or ``null``
    when the repo has never been indexed (no :Repo vertex in the graph yet).
    """

    repo: str
    last_indexed_sha: str | None = None


class CommitFileChange(BaseModel):
    """One file changed in a commit.

    ``changed_lines`` is a list of ``[start_line, end_line]`` pairs (0-indexed,
    matching SCIP line numbering) from ``git diff`` hunk headers.  ``None``
    selects the historical (file-level) TOUCHES path — the endpoint creates a
    single TOUCHES edge from the Commit to the File vertex without querying
    AGE for function bodies.
    """

    path: str
    change_type: Literal["added", "modified", "deleted"]
    hunks: int
    changed_lines: list[list[int]] | None = None


class CommitIngestRequest(BaseModel):
    """POST /code-graph/ingest-commits request body.

    One request per commit.  The host-side script (``scripts/ingest_commits.py``)
    mines ticket-referenced commits via ``git log --grep`` and sends one request
    per commit SHA.
    """

    repo: str
    sha: str
    subject: str
    body: str = ""
    author: str
    authored_at: str
    ticket_ids: list[str]
    files: list[CommitFileChange]

    @field_validator("authored_at")
    @classmethod
    def _validate_authored_at(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"authored_at is not a valid ISO 8601 timestamp: {v!r}") from exc
        return v


class CommitIngestResponse(BaseModel):
    """POST /code-graph/ingest-commits response body."""

    commits_merged: int
    touches_merged: int
    chunks_written: int = 0


class CodeGraphContextRequest(BaseModel):
    """POST /code-graph/context request body.

    ``monikers`` is a list of SCIP monikers to look up.  Typically sourced
    from ``ticket_chunks.moniker`` fields in ``kind='docstring'`` search results.
    An empty list returns an empty ``results`` list immediately.
    """

    monikers: list[str]


class CodeGraphContextCommit(BaseModel):
    """One commit entry in a CodeGraphContextResult."""

    sha: str
    subject: str
    authored_at: str


class CodeGraphContextResult(BaseModel):
    """Ticket linkage for a single SCIP moniker.

    ``tickets`` — deduplicated, sorted list of ticket IDs from all commits
    that touched this symbol via TOUCHES edges.

    ``commits`` — the commits themselves, in traversal order.

    ``repo`` — repository identifier (currently empty; reserved for multi-repo
    disambiguation in BILL-58).
    """

    moniker: str
    repo: str
    tickets: list[str]
    commits: list[CodeGraphContextCommit]


class CodeGraphContextResponse(BaseModel):
    """POST /code-graph/context response body."""

    results: list[CodeGraphContextResult]


class CodeGraphQueryResult(BaseModel):
    """One symbol returned by a graph query (callers, implementors, blast-radius, ticket-code)."""

    moniker: str
    file_path: str
    line: int | None = None        # None for External stub vertices (no source location)
    location: str | None = None    # "file_path:line" or None for stubs
    lang: str
    repo: str
    external: bool


class CodeGraphQueryRequest(BaseModel):
    """Request body for /code-graph/callers and /code-graph/implementors."""

    moniker: str
    repo: str = ""                 # empty = all repos; set via CODE_GRAPH_REPO env var client-side
    limit: int = Field(default=50, ge=1, le=200)


class BlastRadiusRequest(BaseModel):
    """Request body for /code-graph/blast-radius."""

    moniker: str
    repo: str = ""
    depth: int = Field(default=3, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=200)


class TicketCodeRequest(BaseModel):
    """Request body for /code-graph/ticket-code."""

    ticket_id: str
    repo: str = ""
    limit: int = Field(default=50, ge=1, le=200)


class CodeGraphQueryResponse(BaseModel):
    """Response wrapper for all four graph query endpoints."""

    results: list[CodeGraphQueryResult]


class DeadCandidatesRequest(BaseModel):
    """Request body for POST /code-graph/dead-candidates (BILL-104)."""

    repo: str = ""
    cc_threshold: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class DeadCandidateResult(BaseModel):
    """One candidate dead-code Function vertex."""

    moniker: str
    file_path: str
    cyclomatic_complexity: int | None = None
    has_implements: bool
    confidence: Literal["likely_dead", "possibly_dead"]


class DeadCandidatesResponse(BaseModel):
    """Response for POST /code-graph/dead-candidates."""

    candidates: list[DeadCandidateResult]


class CallersWithCCRequest(BaseModel):
    """Request body for POST /code-graph/callers-with-cc (BILL-104)."""

    moniker: str
    repo: str = ""
    limit: int = Field(default=50, ge=1, le=200)


class CallerWithCC(BaseModel):
    """One caller entry annotated with cyclomatic complexity."""

    moniker: str
    file_path: str
    cyclomatic_complexity: int | None = None
    test: bool


class CallersWithCCResponse(BaseModel):
    """Response for POST /code-graph/callers-with-cc."""

    target_cc: int | None = None
    callers: list[CallerWithCC]
