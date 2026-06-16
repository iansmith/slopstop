"""Pure Cypher builders and row parsers for code-quality graph queries (BILL-104).

All functions here are Layer 1 (design/rag-service-testing.md): pure,
deterministic, no I/O, no FastAPI, no DB. The FastAPI endpoints in main.py
are the thin glue that calls these functions and executes the resulting SQL
via DB.run_cypher().

Two query types:
  - dead_candidates  — Function vertices with no incoming CALLS edges, ranked
                       by cyclomatic_complexity descending with confidence
                       classification (likely_dead vs possibly_dead).
  - callers_with_cc  — Direct callers of a given moniker, each annotated with
                       cyclomatic_complexity and test flag. Also looks up the
                       target's own CC via a separate builder.
"""

from __future__ import annotations

import json
import re

from rag_service.code_graph.ingest import _cypher_str, _wrap_cypher
from rag_service.code_graph.commit_ingest import _strip_agtype
from rag_service.code_graph.schema import (
    EDGE_CALLS,
    EDGE_IMPLEMENTS,
    PROP_CYCLOMATIC_COMPLEXITY,
    PROP_FILE_PATH,
    PROP_MONIKER,
    PROP_REPO,
    PROP_TEST,
    VERTEX_FUNCTION,
)

# Name tokens that mark a function as a known entry point even when there are
# no in-graph callers. Matched by exact token after splitting the simple name on
# underscores and camelCase boundaries ("init_db" → "init" matches;
# "initialize" → "initialize" does not).
_ENTRY_POINT_PATTERNS: frozenset[str] = frozenset({"main", "init", "handler", "cli"})

_CAMEL_SPLIT_RE: re.Pattern[str] = re.compile(
    r"[_]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


def _parse_optional_int(raw: object) -> int | None:
    """Strip AGE type suffix, JSON-decode, and cast to int; return None on null or failure."""
    stripped = _strip_agtype(raw)
    if stripped in (None, "null"):
        return None
    try:
        return int(json.loads(stripped))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Cypher builders — Layer 1 (pure, no I/O)
# ---------------------------------------------------------------------------


def build_dead_candidates_cypher(
    repo: str = "", cc_threshold: int = 0, limit: int = 50
) -> str:
    """Cypher: Function vertices with no incoming CALLS edges, ranked by CC.

    Returns rows: (f_moniker agtype, f_file_path agtype, f_cc agtype, f_impl_count agtype).

    f_impl_count is the count of IMPLEMENTS edges pointing *out* from f (i.e.
    f implements some interface). > 0 elevates confidence to possibly_dead.

    Only Function vertices with a cyclomatic_complexity value are included; the
    WHERE comparison against cc_threshold implicitly skips vertices where
    cyclomatic_complexity is absent (NULL comparisons return NULL, which is falsy).
    """
    repo_filter = f" AND f.{PROP_REPO} = '{_cypher_str(repo)}'" if repo else ""
    cypher = (
        f"MATCH (f:{VERTEX_FUNCTION})"
        f" WHERE f.{PROP_CYCLOMATIC_COMPLEXITY} >= {cc_threshold}{repo_filter}"
        f" OPTIONAL MATCH (c)-[:{EDGE_CALLS}]->(f)"
        f" WITH f, count(c) AS caller_count"
        f" WHERE caller_count = 0"
        f" OPTIONAL MATCH (f)-[:{EDGE_IMPLEMENTS}]->(iface)"
        f" WITH f.{PROP_MONIKER} AS fm, f.{PROP_FILE_PATH} AS fp,"
        f" f.{PROP_CYCLOMATIC_COMPLEXITY} AS cc, count(iface) AS impl_count"
        f" RETURN fm, fp, cc, impl_count"
        f" ORDER BY cc DESC"
        f" LIMIT {limit}"
    )
    columns = "f_moniker agtype, f_file_path agtype, f_cc agtype, f_impl_count agtype"
    return _wrap_cypher(cypher, columns)


def build_callers_with_cc_cypher(
    moniker: str, repo: str = "", limit: int = 50
) -> str:
    """Cypher: direct callers of `moniker`, each annotated with CC and test flag.

    Returns rows: (f_moniker agtype, f_file_path agtype, f_cc agtype, f_test agtype).
    """
    m = _cypher_str(moniker)
    where = f" WHERE caller.{PROP_REPO} = '{_cypher_str(repo)}'" if repo else ""
    cypher = (
        f"MATCH (caller)-[:{EDGE_CALLS}]->(target {{{PROP_MONIKER}: '{m}'}})"
        f"{where}"
        f" RETURN DISTINCT caller.{PROP_MONIKER}, caller.{PROP_FILE_PATH},"
        f" caller.{PROP_CYCLOMATIC_COMPLEXITY}, caller.{PROP_TEST}"
        f" LIMIT {limit}"
    )
    columns = "f_moniker agtype, f_file_path agtype, f_cc agtype, f_test agtype"
    return _wrap_cypher(cypher, columns)


def build_target_cc_cypher(moniker: str, repo: str = "") -> str:
    """Cypher: return the CC of the Function identified by `moniker`.

    Returns rows: (f_cc agtype). Typically zero or one rows.

    The :Function label prevents External stub vertices that share the same
    moniker from shadowing the actual function. The repo filter mirrors the
    filter in build_callers_with_cc_cypher so both queries stay in the same
    repo scope.
    """
    m = _cypher_str(moniker)
    repo_clause = f" WHERE f.{PROP_REPO} = '{_cypher_str(repo)}'" if repo else ""
    cypher = (
        f"MATCH (f:{VERTEX_FUNCTION} {{{PROP_MONIKER}: '{m}'}})"
        f"{repo_clause}"
        f" RETURN f.{PROP_CYCLOMATIC_COMPLEXITY}"
    )
    return _wrap_cypher(cypher, "f_cc agtype")


# ---------------------------------------------------------------------------
# Classification helpers — Layer 1 (pure)
# ---------------------------------------------------------------------------


def _name_from_moniker(moniker: str) -> str:
    """Extract the simple function name token from a SCIP moniker.

    For "scip-python ... linesOverlap()." the result is "linesOverlap".
    For "scip-go gomod org/repo . pkg/FuncName()." the result is "FuncName".
    Strips the trailing descriptor suffix ("().", ".", "#", "/"), takes the last
    whitespace-delimited token, then strips any path-qualifier prefix so that
    "pkg/FuncName" or "Mod.Class#method" reduces to the bare name.
    """
    stripped = re.sub(r"\(\)\.$|\.$|#$|/$", "", moniker.strip())
    parts = stripped.rsplit(None, 1)
    name = parts[-1] if parts else moniker
    return re.split(r"[/#.]", name)[-1]


def _classify_dead(moniker: str, has_implements: bool) -> str:
    """Confidence classification for a zero-caller Function vertex.

    Returns:
        "likely_dead"   — no callers, no IMPLEMENTS edge, name not an entry point.
        "possibly_dead" — has an IMPLEMENTS edge OR name matches an entry-point pattern.

    Entry-point matching uses exact token comparison after splitting on underscores
    and camelCase boundaries, so "initialize" does not match "init" and "client"
    does not match "cli", but "init_db" and "MainLoop" both match.
    """
    raw_name = _name_from_moniker(moniker)
    tokens = {t.lower() for t in _CAMEL_SPLIT_RE.split(raw_name) if t}
    if has_implements or tokens & _ENTRY_POINT_PATTERNS:
        return "possibly_dead"
    return "likely_dead"


# ---------------------------------------------------------------------------
# Row parsers — Layer 1 (pure, no I/O)
# ---------------------------------------------------------------------------


def parse_dead_candidates_rows(rows: list) -> list[dict]:
    """Parse AGE rows from build_dead_candidates_cypher.

    Each row is a 4-tuple of agtype strings:
      (f_moniker, f_file_path, f_cc, f_impl_count)

    Returns list of dicts:
      {moniker, file_path, cyclomatic_complexity, has_implements, confidence}

    Malformed rows are skipped silently.
    """
    result = []
    for row in rows:
        try:
            moniker = json.loads(_strip_agtype(row[0]))
            file_path = json.loads(_strip_agtype(row[1]))
            cc = _parse_optional_int(row[2])
            impl_count = int(json.loads(_strip_agtype(row[3])))
            has_implements = impl_count > 0
            result.append({
                "moniker": moniker,
                "file_path": file_path,
                "cyclomatic_complexity": cc,
                "has_implements": has_implements,
                "confidence": _classify_dead(moniker, has_implements),
            })
        except (ValueError, KeyError, IndexError, TypeError):
            continue
    return result


def parse_callers_with_cc_rows(rows: list) -> list[dict]:
    """Parse AGE rows from build_callers_with_cc_cypher.

    Each row is a 4-tuple of agtype strings:
      (f_moniker, f_file_path, f_cc, f_test)

    Returns list of dicts:
      {moniker, file_path, cyclomatic_complexity, test}

    Malformed rows are skipped silently.
    """
    result = []
    for row in rows:
        try:
            moniker = json.loads(_strip_agtype(row[0]))
            file_path = json.loads(_strip_agtype(row[1]))
            cc = _parse_optional_int(row[2])
            test_raw = _strip_agtype(row[3])
            test: bool = json.loads(test_raw) if test_raw not in (None, "null") else False
            result.append({
                "moniker": moniker,
                "file_path": file_path,
                "cyclomatic_complexity": cc,
                "test": test,
            })
        except (ValueError, KeyError, IndexError, TypeError):
            continue
    return result


def parse_target_cc_row(rows: list) -> int | None:
    """Parse the single-row, single-column result from build_target_cc_cypher.

    Returns the CC as int, or None when the target has no CC value or was
    not found in the graph.
    """
    if not rows:
        return None
    return _parse_optional_int(rows[0][0])
