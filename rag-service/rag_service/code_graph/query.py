"""Pure Cypher builder functions and row parser for graph query endpoints (BILL-58).

All functions here are Layer 1 (design/rag-service-testing.md): pure,
deterministic, no I/O, no FastAPI, no DB.  The FastAPI endpoints in main.py
are the thin glue that calls these functions and executes the resulting SQL
via DB.run_cypher().

Four query types:
  - callers       — who directly calls a given function (CALLS edge)?
  - implementors  — who implements a given interface (IMPLEMENTS edge)?
  - blast_radius  — transitive callers up to depth N (CALLS*1..N)?
  - ticket_code   — functions touched by commits referencing a ticket ID?
"""

from __future__ import annotations

import json

from rag_service.code_graph.ingest import _CYPHER_TAG, _GRAPH_NAME, _cypher_str
from rag_service.code_graph.commit_ingest import _strip_agtype
from rag_service.code_graph.schema import (
    EDGE_CALLS,
    EDGE_IMPLEMENTS,
    EDGE_TOUCHES,
    VERTEX_COMMIT,
    PROP_MONIKER,
    PROP_REPO,
    PROP_FILE_PATH,
    PROP_RANGE,
    PROP_LANG,
    PROP_EXTERNAL,
    PROP_TICKET_IDS,
)

# ── Safety constants — update these to tune query guards ─────────────────────
# Changing any value here affects ALL four query endpoints. Do not scatter
# these constants; keep them here so a reviewer can audit them in one place.
DEFAULT_LIMIT: int = 50         # default results returned per query call
MAX_LIMIT: int = 200            # Pydantic Field(le=MAX_LIMIT) enforces this ceiling
DEFAULT_DEPTH: int = 3          # default hop depth for get_blast_radius
MAX_DEPTH: int = 5              # Pydantic Field(le=MAX_DEPTH) enforces this ceiling
QUERY_TIMEOUT_MS: int = 10_000  # AGE statement_timeout in milliseconds (10 seconds)


# ---------------------------------------------------------------------------
# SQL wrapper — Layer 1 (pure)
# ---------------------------------------------------------------------------


def _build_query_sql(cypher: str) -> str:
    """Wrap a read Cypher query to return the 6 standard symbol columns.

    Returns:
        SQL SELECT that AGE executes via the cypher() function, projecting
        6 agtype columns: f_moniker, f_file_path, f_range, f_lang, f_repo, f_external.
    """
    return (
        f"SELECT * FROM cypher('{_GRAPH_NAME}', {_CYPHER_TAG} {cypher} {_CYPHER_TAG}) "
        f"AS (f_moniker agtype, f_file_path agtype, f_range agtype, "
        f"f_lang agtype, f_repo agtype, f_external agtype)"
    )


# ---------------------------------------------------------------------------
# Cypher builders — Layer 1 (pure, no I/O)
# ---------------------------------------------------------------------------


def build_callers_cypher(moniker: str, repo: str = "", limit: int = DEFAULT_LIMIT) -> str:
    """Cypher: who calls the function identified by `moniker`?

    Traverses CALLS edges: (caller)-[:CALLS]->(target {moniker: <moniker>}).
    """
    m = _cypher_str(moniker)
    where = f" WHERE caller.{PROP_REPO} = '{_cypher_str(repo)}'" if repo else ""
    cypher = (
        f"MATCH (caller)-[:{EDGE_CALLS}]->(target {{{PROP_MONIKER}: '{m}'}})"
        f"{where}"
        f" RETURN caller.{PROP_MONIKER}, caller.{PROP_FILE_PATH}, caller.{PROP_RANGE},"
        f" caller.{PROP_LANG}, caller.{PROP_REPO}, caller.{PROP_EXTERNAL}"
        f" LIMIT {limit}"
    )
    return _build_query_sql(cypher)


def build_implementors_cypher(moniker: str, repo: str = "", limit: int = DEFAULT_LIMIT) -> str:
    """Cypher: who implements the interface identified by `moniker`?

    Traverses IMPLEMENTS edges: (implementor)-[:IMPLEMENTS]->(target {moniker: <moniker>}).
    """
    m = _cypher_str(moniker)
    where = f" WHERE implementor.{PROP_REPO} = '{_cypher_str(repo)}'" if repo else ""
    cypher = (
        f"MATCH (implementor)-[:{EDGE_IMPLEMENTS}]->(target {{{PROP_MONIKER}: '{m}'}})"
        f"{where}"
        f" RETURN implementor.{PROP_MONIKER}, implementor.{PROP_FILE_PATH},"
        f" implementor.{PROP_RANGE}, implementor.{PROP_LANG},"
        f" implementor.{PROP_REPO}, implementor.{PROP_EXTERNAL}"
        f" LIMIT {limit}"
    )
    return _build_query_sql(cypher)


def build_blast_radius_cypher(
    moniker: str, depth: int = DEFAULT_DEPTH, repo: str = "", limit: int = DEFAULT_LIMIT
) -> str:
    """Cypher: transitive callers within `depth` hops (blast radius).

    Traverses: (caller)-[:CALLS*1..depth]->(target {moniker: <moniker>}).
    """
    m = _cypher_str(moniker)
    where = f" WHERE caller.{PROP_REPO} = '{_cypher_str(repo)}'" if repo else ""
    cypher = (
        f"MATCH (caller)-[:{EDGE_CALLS}*1..{depth}]->(target {{{PROP_MONIKER}: '{m}'}})"
        f"{where}"
        f" RETURN caller.{PROP_MONIKER}, caller.{PROP_FILE_PATH}, caller.{PROP_RANGE},"
        f" caller.{PROP_LANG}, caller.{PROP_REPO}, caller.{PROP_EXTERNAL}"
        f" LIMIT {limit}"
    )
    return _build_query_sql(cypher)


def build_ticket_code_cypher(ticket_id: str, repo: str = "", limit: int = DEFAULT_LIMIT) -> str:
    """Cypher: functions touched by commits that reference `ticket_id`.

    Traverses: (Commit where ticket_id IN ticket_ids)-[:TOUCHES]->(f).
    """
    t = _cypher_str(ticket_id)
    and_repo = f" AND f.{PROP_REPO} = '{_cypher_str(repo)}'" if repo else ""
    cypher = (
        f"MATCH (c:{VERTEX_COMMIT})-[:{EDGE_TOUCHES}]->(f)"
        f" WHERE '{t}' IN c.{PROP_TICKET_IDS}{and_repo}"
        f" RETURN f.{PROP_MONIKER}, f.{PROP_FILE_PATH}, f.{PROP_RANGE},"
        f" f.{PROP_LANG}, f.{PROP_REPO}, f.{PROP_EXTERNAL}"
        f" LIMIT {limit}"
    )
    return _build_query_sql(cypher)


# ---------------------------------------------------------------------------
# Row parser — Layer 1 (pure, no I/O)
# ---------------------------------------------------------------------------


def parse_query_rows(rows: list) -> list[dict]:
    """Parse AGE agtype rows from the four graph query endpoints.

    Each row is a 6-tuple of agtype-encoded values:
      (f_moniker, f_file_path, f_range, f_lang, f_repo, f_external)

    f_range is a JSON array [startLine, startChar, endChar] (SCIP 0-indexed);
    line in the result is startLine + 1 (1-indexed). External stub vertices
    return None for range → line and location are None.

    AGE type suffixes (::agtype, ::list) are stripped before JSON decoding.
    Malformed rows are skipped silently.
    """
    result = []
    for row in rows:
        try:
            moniker = json.loads(_strip_agtype(row[0]))
            file_path = json.loads(_strip_agtype(row[1]))
            range_raw = row[2]
            if range_raw is not None:
                range_list = json.loads(_strip_agtype(range_raw))
                line: int | None = range_list[0] + 1
                location: str | None = f"{file_path}:{line}"
            else:
                line = None
                location = None
            lang = json.loads(_strip_agtype(row[3]))
            repo = json.loads(_strip_agtype(row[4])) if row[4] is not None else ""
            external = json.loads(_strip_agtype(row[5])) if row[5] is not None else False
            result.append({
                "moniker": moniker,
                "file_path": file_path,
                "line": line,
                "location": location,
                "lang": lang,
                "repo": repo,
                "external": external,
            })
        except (ValueError, KeyError, IndexError, TypeError):
            continue  # skip malformed rows; other rows still processed
    return result
