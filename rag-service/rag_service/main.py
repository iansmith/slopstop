"""FastAPI app for the ticket-rag service.

Endpoints:
- GET  /healthz     — liveness/readiness (postgres reachability + schema presence).
- POST /search      — dense retrieval + optional cross-encoder rerank (BILL-31).
- POST /search_note — record a search + project note to pgdata for later analysis.

/healthz is expected to be polled at Docker-healthcheck cadence (~1/min). Each
call does one tiny `SELECT 1` + one `SELECT to_regclass(...)` round-trip; this
is fine at one-per-minute. Do not poll in tight loops.

Per design/rag-service-testing.md, every external resource is reached through a
FastAPI dependency provider (get_db_conn / get_embedder / get_reranker) so tests
can swap them via app.dependency_overrides without monkey-patching globals. The
endpoint bodies stay thin glue; the rerank-and-trim logic lives in the pure
rag_service.search.rank_and_trim helper, tested directly at Layer 1.
"""

import os
import pathlib
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from rag_service.code_graph.commit_ingest import (
    build_code_context_cypher,
    build_commit_vertex_cypher,
    build_query_functions_cypher,
    build_touches_cypher,
    parse_context_rows,
    parse_function_rows,
    resolve_touches_targets,
)
from rag_service.code_graph.query import (
    build_callers_cypher,
    build_implementors_cypher,
    build_blast_radius_cypher,
    build_ticket_code_cypher,
    parse_query_rows,
    QUERY_TIMEOUT_MS,
)
from rag_service.code_graph.ingest import (
    build_edge_cypher,
    build_vertex_cypher,
    extract_calls_edges,
    extract_docstring_rows,
    extract_implements_edges,
    extract_vertices,
)
from rag_service.db import DB, STAGE1_TOP_K, get_age_conn, get_db_conn
from rag_service.embed import Embedder, get_embedder
from rag_service.harvesters._common import embed_rows
from rag_service.models import (
    BlastRadiusRequest,
    CodeGraphContextRequest,
    CodeGraphContextResponse,
    CodeGraphContextResult,
    CodeGraphIngestRequest,
    CodeGraphIngestResponse,
    CodeGraphQueryRequest,
    CodeGraphQueryResponse,
    CodeGraphQueryResult,
    CommitIngestRequest,
    CommitIngestResponse,
    SearchFilters,
    SearchRequest,
    SearchResponse,
    TicketCodeRequest,
)
from rag_service.query_preprocessor import preprocess_query
from rag_service.rerank import Reranker, get_reranker
from rag_service.search import rank_and_trim

app = FastAPI()

# Default notes directory (inside the pgdata volume, durable on host disk).
# Override with RAG_SERVICE_SEARCH_NOTES_DIR for tests or alternate deployments.
_DEFAULT_SEARCH_NOTES_DIR = "/var/lib/postgresql/search_notes"


def _search_notes_dir() -> pathlib.Path:
    """Return the notes directory, resolved at call time so tests can redirect
    writes via the RAG_SERVICE_SEARCH_NOTES_DIR env var without reloading the
    module or monkey-patching module-level state."""
    return pathlib.Path(
        os.environ.get("RAG_SERVICE_SEARCH_NOTES_DIR", _DEFAULT_SEARCH_NOTES_DIR)
    )


@app.get("/healthz")
def healthz(db: DB = Depends(get_db_conn)):
    if not db.ping():
        return JSONResponse(
            status_code=503,
            content={"postgres": "unreachable", "schema": "missing"},
        )

    schema_ok = db.has_table("ticket_chunks")
    body = {"postgres": "ok", "schema": "ok" if schema_ok else "missing"}
    return body if schema_ok else JSONResponse(status_code=503, content=body)


@app.post("/search", response_model=SearchResponse)
def search(
    req: SearchRequest,
    db: DB = Depends(get_db_conn),
    embedder: Embedder = Depends(get_embedder),
    reranker: Reranker = Depends(get_reranker),
) -> SearchResponse:
    """Dense retrieval → optional rerank → top-K.

    Stage 1 (dense kNN) is capped at db.STAGE1_TOP_K candidates regardless of
    the request's `k`; `k` only bounds the final response length after the
    optional Stage-2 rerank. See design/ticket-rag.md § Embedding & retrieval.
    """
    query = preprocess_query(req.query)
    vec = embedder.encode_query(query)
    # Merge top-level `project` into filters so the DB layer sees one unified
    # filter object.  Normalise to uppercase — project codes are always caps.
    filters = req.filters or SearchFilters()
    project = req.project.strip().upper()
    if project:
        filters = filters.model_copy(update={"project": project})
    candidates = db.knn_search(vec, k=STAGE1_TOP_K, filters=filters)
    results = rank_and_trim(
        candidates, query, reranker, k=req.k, rerank=req.rerank
    )
    return SearchResponse(results=results)


@app.post("/code-graph/ingest", response_model=CodeGraphIngestResponse)
def ingest_code_graph(
    req: CodeGraphIngestRequest,
    db: DB = Depends(get_age_conn),
    db_conn: DB = Depends(get_db_conn),
    embedder: Embedder = Depends(get_embedder),
) -> CodeGraphIngestResponse:
    """Ingest a SCIP JSON index into the AGE code knowledge graph.

    Extracts vertices and edges from the index, generates idempotent Cypher
    MERGE statements for each, and executes them via DB.run_cypher(). Running
    the same index twice is safe — MERGE updates in-place rather than duplicating.

    Also extracts SCIP SymbolInformation.documentation fields, embeds them via
    bge-m3, and writes the resulting rows to ticket_chunks (source='scip',
    kind='docstring') so they participate in unified semantic search (BILL-57).
    """
    vertices = extract_vertices(req.index, req.repo)
    calls_edges = extract_calls_edges(req.index, req.repo)
    implements_edges = extract_implements_edges(req.index, req.repo)

    for vertex in vertices:
        db.run_cypher(build_vertex_cypher(vertex))

    all_edges = calls_edges + implements_edges
    for src, edge_type, tgt in all_edges:
        db.run_cypher(build_edge_cypher(src, edge_type, tgt, req.repo))

    # Extract, embed, and persist docstring rows (BILL-57).
    docstring_rows = extract_docstring_rows(req.index, req.repo)
    if docstring_rows:
        embed_rows(docstring_rows, embedder)
        db_conn.write_docstring_rows(docstring_rows, req.repo)

    return CodeGraphIngestResponse(
        vertices_merged=len(vertices),
        edges_merged=len(all_edges),
        docstring_rows=len(docstring_rows),
    )


@app.post("/code-graph/context", response_model=CodeGraphContextResponse)
def code_graph_context(
    req: CodeGraphContextRequest,
    db: DB = Depends(get_age_conn),
) -> CodeGraphContextResponse:
    """Return ticket linkage for one or more SCIP monikers (BILL-57).

    For each moniker, traverses TOUCHES edges in the code knowledge graph to
    find commits that modified that symbol, then surfaces the ticket IDs those
    commits reference.

    Monikers with no TOUCHES data are omitted from the results list (rather
    than returned as empty entries) so callers can treat a non-empty results
    list as confirmation of graph coverage.

    CALLS/IMPLEMENTS traversal and blast-radius queries are deferred to BILL-58.
    """
    results = []
    for moniker in req.monikers:
        rows = db.run_cypher(build_code_context_cypher(moniker))
        for parsed in parse_context_rows(rows, moniker):
            results.append(
                CodeGraphContextResult(
                    moniker=parsed["moniker"],
                    repo=parsed["repo"],
                    tickets=parsed["tickets"],
                    commits=parsed["commits"],
                )
            )
    return CodeGraphContextResponse(results=results)


def _set_query_timeout(db: DB) -> None:
    """Apply AGE statement timeout for read queries.

    Uses session-scope SET (not SET LOCAL) because the connection runs in
    autocommit mode — SET LOCAL requires an explicit transaction block and
    would silently no-op otherwise. The connection is per-request and closed
    immediately after the response, so the session-level setting does not
    bleed into other requests.
    """
    db.execute_sql(f"SET statement_timeout = '{QUERY_TIMEOUT_MS}'")


@app.post("/code-graph/callers", response_model=CodeGraphQueryResponse)
def graph_callers(
    req: CodeGraphQueryRequest,
    db: DB = Depends(get_age_conn),
) -> CodeGraphQueryResponse:
    """Return functions that directly call the given moniker (CALLS edge)."""
    _set_query_timeout(db)
    rows = db.run_cypher(build_callers_cypher(req.moniker, req.repo, req.limit))
    return CodeGraphQueryResponse(
        results=[CodeGraphQueryResult(**r) for r in parse_query_rows(rows)]
    )


@app.post("/code-graph/implementors", response_model=CodeGraphQueryResponse)
def graph_implementors(
    req: CodeGraphQueryRequest,
    db: DB = Depends(get_age_conn),
) -> CodeGraphQueryResponse:
    """Return functions/types that implement the given interface moniker (IMPLEMENTS edge)."""
    _set_query_timeout(db)
    rows = db.run_cypher(build_implementors_cypher(req.moniker, req.repo, req.limit))
    return CodeGraphQueryResponse(
        results=[CodeGraphQueryResult(**r) for r in parse_query_rows(rows)]
    )


@app.post("/code-graph/blast-radius", response_model=CodeGraphQueryResponse)
def graph_blast_radius(
    req: BlastRadiusRequest,
    db: DB = Depends(get_age_conn),
) -> CodeGraphQueryResponse:
    """Return transitive callers of the given moniker up to `depth` hops (CALLS*1..depth)."""
    _set_query_timeout(db)
    rows = db.run_cypher(
        build_blast_radius_cypher(req.moniker, req.depth, req.repo, req.limit)
    )
    return CodeGraphQueryResponse(
        results=[CodeGraphQueryResult(**r) for r in parse_query_rows(rows)]
    )


@app.post("/code-graph/ticket-code", response_model=CodeGraphQueryResponse)
def graph_ticket_code(
    req: TicketCodeRequest,
    db: DB = Depends(get_age_conn),
) -> CodeGraphQueryResponse:
    """Return functions touched by commits that reference the given ticket ID."""
    _set_query_timeout(db)
    rows = db.run_cypher(build_ticket_code_cypher(req.ticket_id, req.repo, req.limit))
    return CodeGraphQueryResponse(
        results=[CodeGraphQueryResult(**r) for r in parse_query_rows(rows)]
    )


@app.post("/code-graph/ingest-commits", response_model=CommitIngestResponse)
def ingest_commits(
    req: CommitIngestRequest,
    db: DB = Depends(get_age_conn),
) -> CommitIngestResponse:
    """Ingest commit provenance into the AGE code knowledge graph.

    Writes one Commit vertex and one TOUCHES edge per changed file (file-level)
    or per matching Function vertex (function-level, when changed_lines are
    provided and the file has been SCIP-indexed).  Running the same commit
    twice is safe — all Cypher statements are idempotent MERGE.
    """
    db.run_cypher(build_commit_vertex_cypher(req))

    touches = 0
    for fc in req.files:
        function_rows = []
        if fc.changed_lines is not None:
            rows = db.run_cypher(build_query_functions_cypher(req.repo, fc.path))
            function_rows = parse_function_rows(rows)
        targets = resolve_touches_targets(fc, function_rows)

        for moniker in targets:
            db.run_cypher(
                build_touches_cypher(req.sha, req.repo, moniker, fc.change_type, fc.hunks)
            )
            touches += 1

    return CommitIngestResponse(commits_merged=1, touches_merged=touches)


@app.post("/search_note", status_code=201)
def search_note(req: SearchRequest) -> dict:
    """Record a search note to pgdata for later analysis.

    Writes the project and query string to a timestamped plain-text file in
    /var/lib/postgresql/search_notes/ (the pgdata volume — durable on the host
    at pgdata/search_notes/). No retrieval is performed.

    Use this when a search doesn't return what you expect: the file captures
    enough context for offline debugging — project scope, exact query text,
    and timestamp.
    """
    notes_dir = _search_notes_dir()
    notes_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc)
    fname = notes_dir / f"search_note-{ts.strftime('%Y%m%d-%H%M%S-%f')}.txt"
    fname.write_text(
        f"timestamp: {ts.isoformat()}\n"
        f"project:   {req.project.strip() or '(all)'}\n"
        f"query:     {req.query}\n"
    )
    return {"file": str(fname)}
