"""Pure commit-provenance functions for the AGE code knowledge graph (BILL-56).

All functions here are Layer 1 (design/rag-service-testing.md): pure,
deterministic, no I/O, no FastAPI, no DB.  The FastAPI endpoint in main.py
is the thin glue that calls these functions and executes the resulting Cypher
via DB.run_cypher().

Design decisions (BILL-56 grill session 2026-06-03):
  - One Commit vertex per (sha, repo) — MERGE key, same pattern as code vertices.
  - No Ticket vertices — ticket_ids is an array property on Commit so queries
    can be MATCH (c:Commit) WHERE 'BILL-42' IN c.ticket_ids.
  - TOUCHES edge properties: change_type (added/modified/deleted) + hunks (int).
  - Historical path (changed_lines=None): file-level TOUCHES only.
  - Forward path (changed_lines provided): function-level TOUCHES via
    enclosing_range lookup in AGE; falls back to file-level when no functions
    match (unindexed file type, or SCIP not yet run for that file).
  - enclosing_range must be stored on Function vertices by the SCIP ingestion
    (BILL-55 update in this same PR) for function-level resolution to work.
"""

from __future__ import annotations

import json

from rag_service.code_graph.ingest import (
    _CYPHER_TAG,
    _GRAPH_NAME,
    _cypher_str,
    _normalize_enc_range,
    _wrap_cypher,
)
from rag_service.code_graph.schema import (
    EDGE_TOUCHES,
    PROP_AUTHOR,
    PROP_AUTHORED_AT,
    PROP_CHANGE_TYPE,
    PROP_ENCLOSING_RANGE,
    PROP_FILE_PATH,
    PROP_HUNKS,
    PROP_MONIKER,
    PROP_REPO,
    PROP_SHA,
    PROP_SUBJECT,
    PROP_TICKET_IDS,
    VERTEX_COMMIT,
    VERTEX_FUNCTION,
)
from rag_service.models import CommitFileChange, CommitIngestRequest

# ---------------------------------------------------------------------------
# Cypher builders — Layer 1 (pure, no I/O)
# ---------------------------------------------------------------------------


def build_commit_vertex_cypher(req: CommitIngestRequest) -> str:
    """Idempotent MERGE for a Commit vertex.

    MERGE key is ``(sha, repo)``.  SET overwrites subject/author/authored_at
    so a re-ingest with corrected metadata is safe.  ticket_ids is stored as a
    Cypher list literal so Cypher ``IN`` predicates work directly.
    """
    sha = _cypher_str(req.sha)
    repo = _cypher_str(req.repo)
    subject = _cypher_str(req.subject)
    author = _cypher_str(req.author)
    authored_at = _cypher_str(req.authored_at)
    ticket_ids_lit = "[" + ", ".join(f"'{_cypher_str(t)}'" for t in req.ticket_ids) + "]"

    cypher = (
        f"MERGE (c:{VERTEX_COMMIT} {{{PROP_SHA}: '{sha}', {PROP_REPO}: '{repo}'}}) "
        f"SET c.{PROP_SUBJECT} = '{subject}', c.{PROP_AUTHOR} = '{author}', "
        f"c.{PROP_AUTHORED_AT} = '{authored_at}', "
        f"c.{PROP_TICKET_IDS} = {ticket_ids_lit} "
        f"RETURN c"
    )
    return _wrap_cypher(cypher)


def build_query_functions_cypher(repo: str, file_path: str) -> str:
    """Cypher that returns ``[moniker, enclosing_range]`` pairs for all
    Function vertices with a known body span in the given file.

    Used by the endpoint to resolve which functions were touched by a commit
    hunk before building TOUCHES edges.  Returns a single agtype list value
    per row so the standard ``_wrap_cypher`` wrapper (one column) works.
    """
    r = _cypher_str(repo)
    fp = _cypher_str(file_path)
    cypher = (
        f"MATCH (f:{VERTEX_FUNCTION} {{{PROP_REPO}: '{r}', {PROP_FILE_PATH}: '{fp}'}}) "
        f"WHERE f.{PROP_ENCLOSING_RANGE} IS NOT NULL "
        f"RETURN [f.{PROP_MONIKER}, f.{PROP_ENCLOSING_RANGE}]"
    )
    return _wrap_cypher(cypher)


def build_touches_cypher(
    sha: str,
    repo: str,
    target_moniker: str,
    change_type: str,
    hunks: int,
) -> str:
    """Idempotent MERGE for a TOUCHES edge from a Commit to a File or Function.

    MATCHes the Commit by ``(sha, repo)`` and the target by ``(moniker, repo)``,
    then MERGEs the directed TOUCHES edge and SETs change_type and hunks.
    If either endpoint is absent (e.g. SCIP not yet run for the file) the MATCH
    returns nothing and no edge is written — safe and idempotent.
    """
    s = _cypher_str(sha)
    r = _cypher_str(repo)
    t = _cypher_str(target_moniker)
    ct = _cypher_str(change_type)

    cypher = (
        f"MATCH (c:{VERTEX_COMMIT} {{{PROP_SHA}: '{s}', {PROP_REPO}: '{r}'}}), "
        f"(tgt {{{PROP_MONIKER}: '{t}', {PROP_REPO}: '{r}'}}) "
        f"MERGE (c)-[e:{EDGE_TOUCHES}]->(tgt) "
        f"SET e.{PROP_CHANGE_TYPE} = '{ct}', e.{PROP_HUNKS} = {hunks} "
        f"RETURN e"
    )
    return _wrap_cypher(cypher)


def _strip_agtype(raw: object) -> str | None:
    """Strip trailing AGE type annotations before JSON decoding.

    psycopg3 returns agtype columns as Python strings; AGE may append
    ``::agtype`` or ``::list`` in some contexts.  Stripping these suffixes
    (the same approach used in ``parse_function_rows``) lets ``json.loads``
    handle both bare-JSON and annotated forms transparently.

    Returns None when raw is None (psycopg3 NULL column).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    for suffix in ("::agtype", "::list"):
        if s.endswith(suffix):
            return s[: -len(suffix)].strip()
    return s


def build_code_context_cypher(moniker: str) -> str:
    """Cypher that returns TOUCHES-linked commits for a given symbol moniker.

    Traverses: (Commit)-[:TOUCHES]->(symbol with moniker=<moniker>)
    Returns 6 agtype columns per matching commit:
      f_moniker, c_sha, c_subject, c_authored_at, c_ticket_ids, f_repo

    Used by POST /code-graph/context for the ticket-linkage feature (BILL-57).
    Returns are separate columns (not a map) so callers can use positional
    access without JSON-parsing a nested map.
    """
    m = _cypher_str(moniker)
    cypher = (
        f"MATCH (c:{VERTEX_COMMIT})-[:{EDGE_TOUCHES}]->(f {{{PROP_MONIKER}: '{m}'}}) "
        f"RETURN f.{PROP_MONIKER}, c.{PROP_SHA}, c.{PROP_SUBJECT}, "
        f"c.{PROP_AUTHORED_AT}, c.{PROP_TICKET_IDS}, f.{PROP_REPO}"
    )
    return (
        f"SELECT * FROM cypher('{_GRAPH_NAME}', {_CYPHER_TAG} {cypher} {_CYPHER_TAG}) "
        f"AS (f_moniker agtype, c_sha agtype, c_subject agtype, "
        f"c_authored_at agtype, c_ticket_ids agtype, f_repo agtype)"
    )


def parse_context_rows(rows: list, moniker: str) -> list[dict]:
    """Parse AGE rows from ``build_code_context_cypher`` into per-repo context dicts.

    Returns an empty list if rows is empty (no TOUCHES data for this moniker).
    Returns one dict per distinct repo when the same moniker is touched by commits
    from multiple repos (e.g. a fork that shares a Go module path).

    Each row is a 6-tuple of agtype-encoded strings:
      (f_moniker, c_sha, c_subject, c_authored_at, c_ticket_ids, f_repo)

    ticket_ids is a JSON array in agtype; parsed to a deduplicated sorted list.
    AGE type suffixes (``::agtype``, ``::list``) are stripped before decoding.
    """
    if not rows:
        return []
    by_repo: dict[str, dict] = {}
    for row in rows:
        sha = json.loads(_strip_agtype(row[1]))
        subject = json.loads(_strip_agtype(row[2]))
        authored_at = json.loads(_strip_agtype(row[3]))
        raw_ids = json.loads(_strip_agtype(row[4]))
        repo = json.loads(_strip_agtype(row[5])) if row[5] is not None else ""
        bucket = by_repo.setdefault(
            repo,
            {"moniker": moniker, "repo": repo, "tickets": set(), "commits": []},
        )
        if isinstance(raw_ids, list):
            bucket["tickets"].update(str(t) for t in raw_ids)
        bucket["commits"].append({"sha": sha, "subject": subject, "authored_at": authored_at})
    return [
        {**ctx, "tickets": sorted(ctx["tickets"])}
        for ctx in by_repo.values()
    ]


# ---------------------------------------------------------------------------
# Result parsing — Layer 1 (pure, no I/O)
# ---------------------------------------------------------------------------


def parse_function_rows(rows: list) -> list[tuple[str, list[int]]]:
    """Parse AGE agtype rows from ``build_query_functions_cypher`` results.

    Each row is a tuple whose first element is an agtype-encoded list string
    ``["moniker", [start_line, start_col, end_line, end_col]]``.  psycopg3
    returns agtype values as Python strings (no registered type adapter for
    agtype); json.loads() handles both bare JSON and the ``::agtype`` suffix
    that AGE appends in some contexts.

    Rows ingested before ``_normalize_enc_range`` was introduced may carry a
    3-element ``[start_line, start_col, end_col]`` range; these are normalised
    to 4-element here so that ``lines_overlap`` always receives a valid range
    regardless of when the vertex was written.

    Returns a list of ``(moniker, enclosing_range)`` tuples — same shape as
    the ``callers`` list in ``extract_calls_edges``.
    """
    result: list[tuple[str, list[int]]] = []
    for row in rows:
        raw = row[0] if isinstance(row, (list, tuple)) else row
        try:
            pair = json.loads(_strip_agtype(raw))
            # Normalise legacy 3-element ranges so lines_overlap always reads
            # enc_range[2] as end_line, not end_col.
            result.append((pair[0], _normalize_enc_range(pair[1])))
        except (ValueError, KeyError, IndexError, TypeError):
            continue  # Malformed row — skip silently; other rows still processed.
    return result


# ---------------------------------------------------------------------------
# Overlap logic — Layer 1 (pure)
# ---------------------------------------------------------------------------


def lines_overlap(changed_lines: list[list[int]], enc_range: list[int]) -> bool:
    """Return True if any changed-line interval overlaps the function body range.

    ``changed_lines`` is a list of ``[start_line, end_line]`` pairs (0-indexed,
    matching SCIP).  ``enc_range`` is ``[start_line, start_col, end_line,
    end_col]`` — the SCIP enclosing_range of a Function vertex.

    Two intervals ``[lo, hi]`` and ``[s, e]`` overlap iff ``lo <= e AND hi >= s``.
    """
    start_line, end_line = enc_range[0], enc_range[2]
    for lo, hi in changed_lines:
        if lo <= end_line and hi >= start_line:
            return True
    return False


def resolve_touches_targets(
    file_change: CommitFileChange,
    function_rows: list[tuple[str, list[int]]],
) -> list[str]:
    """Decide which AGE vertex monikers a commit TOUCHES for one changed file.

    Two paths:
    - **File-level** (``changed_lines is None`` or no functions in AGE):
      returns ``[file_change.path]`` — the File vertex moniker.
    - **Function-level** (``changed_lines`` provided and functions exist):
      returns monikers of Function vertices whose ``enclosing_range`` overlaps
      any changed-line interval.  Falls back to file-level when no functions
      match (unindexed file types, top-level-only changes, etc.).

    ``function_rows`` is the output of ``parse_function_rows(db.run_cypher(...))``.
    Callers must parse before passing here so this function stays pure.
    """
    if file_change.changed_lines is None or not function_rows:
        return [file_change.path]

    matched = [
        moniker
        for moniker, enc_range in function_rows
        if lines_overlap(file_change.changed_lines, enc_range)
    ]
    return matched if matched else [file_change.path]
