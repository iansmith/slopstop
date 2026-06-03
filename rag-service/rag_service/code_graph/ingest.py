"""Pure SCIP index ingestion functions for the AGE code knowledge graph.

All functions in this module are Layer 1 (design/rag-service-testing.md):
pure, deterministic, no I/O, no FastAPI, no DB. They transform a SCIP JSON
index (Python dict, snake_case field names as produced by Python protobuf
bindings) into vertex dicts and Cypher MERGE statements.

The FastAPI endpoint in main.py is the thin glue that calls these functions
and executes the resulting Cypher statements via DB.run_cypher().

Grounded in design/scip-code-graph-spike.md (Parts 1–4).
"""

from __future__ import annotations

import re

from rag_service.code_graph.schema import (
    EDGE_CALLS,
    EDGE_IMPLEMENTS,
    PROP_ENCLOSING_RANGE,
    PROP_EXTERNAL,
    PROP_FILE_PATH,
    PROP_LANG,
    PROP_MONIKER,
    PROP_REPO,
    PROP_TEST,
    VERTEX_EXTERNAL,
    VERTEX_FILE,
    _LOCAL_RE,
    is_callable,
    vertex_type_from_descriptor,
)

# ── Internal helpers ──────────────────────────────────────────────────────────

_GRAPH_NAME: str = "code_graph"


def _descriptor_from_moniker(moniker: str) -> str:
    """Extract the descriptor portion from a SCIP moniker.

    Full moniker grammar: <scheme> <manager> <package> <version> <descriptor>
    Local symbols are just "local N" with no prefix — the moniker IS the descriptor.
    """
    if _LOCAL_RE.match(moniker):
        return moniker
    parts = moniker.split()
    return " ".join(parts[4:]) if len(parts) >= 5 else moniker


def _lang_from_tool_name(tool_name: str) -> str:
    """Convert scip-go / scip-python / scip-typescript to go / python / typescript."""
    return tool_name.split("-", 1)[1] if "-" in tool_name else tool_name


def _is_test_path(path: str, lang: str) -> bool:
    p = path.lower()
    if lang == "go":
        return p.endswith("_test.go")
    if lang == "python":
        return "_test" in p or "tests/" in p
    if lang == "typescript":
        return ".test." in p or ".spec." in p
    return False


def _is_inside(occ_range: list[int], enc_range: list[int]) -> bool:
    """Return True if the start of occ_range falls inside enc_range.

    enc_range is always 4-element [startLine, startChar, endLine, endChar].
    occ_range may be 3-element [line, startChar, endChar] (single-line) or 4.
    Containment is checked at the start position (line, startChar).
    """
    occ_line = occ_range[0]
    occ_char = occ_range[1]
    start_line, start_char, end_line, end_char = enc_range
    if occ_line < start_line or occ_line > end_line:
        return False
    if occ_line == start_line and occ_char < start_char:
        return False
    if occ_line == end_line and occ_char > end_char:
        return False
    return True


_CYPHER_TAG = "$scip$"


def _cypher_str(value: str) -> str:
    """Escape a value for embedding in a Cypher single-quoted string literal.

    Also rejects values containing the dollar-quote tag used by _wrap_cypher so
    a crafted moniker/repo can't break out of the SQL dollar-quoted literal.
    """
    if _CYPHER_TAG in value:
        raise ValueError(f"value contains reserved delimiter {_CYPHER_TAG!r}: {value!r}")
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _wrap_cypher(cypher: str) -> str:
    """Wrap a Cypher statement for execution via AGE's SQL function."""
    return f"SELECT * FROM cypher('{_GRAPH_NAME}', {_CYPHER_TAG} {cypher} {_CYPHER_TAG}) AS (r agtype)"


# ── Public API ────────────────────────────────────────────────────────────────


def extract_vertices(index: dict, repo: str) -> list[dict]:
    """Extract all vertex dicts from a SCIP JSON index.

    Creates:
    - One File vertex per document (moniker = relative_path).
    - One vertex per non-local SymbolInformation entry, labelled by descriptor suffix.
    - One External stub vertex for each moniker referenced in occurrences
      that has no corresponding SymbolInformation (e.g. stdlib, cross-module deps).

    All vertices carry the `repo` property for multi-repo graph isolation.
    """
    tool_name = index.get("metadata", {}).get("tool_info", {}).get("name", "")
    lang = _lang_from_tool_name(tool_name)

    vertices: dict[str, dict] = {}  # moniker → vertex dict; dict preserves insertion order

    # Collect occurrence monikers while processing each document so External stubs
    # can be created in a single post-loop pass instead of a second document scan.
    seen_in_occurrences: set[str] = set()

    for doc in index.get("documents", []):
        path = doc.get("relative_path", "")
        is_test = _is_test_path(path, lang)

        vertices[path] = {
            PROP_MONIKER: path,
            "label": VERTEX_FILE,
            PROP_REPO: repo,
            PROP_FILE_PATH: path,
            PROP_LANG: lang,
            PROP_TEST: is_test,
            PROP_EXTERNAL: False,
        }

        for sym in doc.get("symbols", []):
            moniker = sym["symbol"]
            if _LOCAL_RE.match(moniker):
                continue
            descriptor = _descriptor_from_moniker(moniker)
            kind = sym.get("kind") or None
            label = vertex_type_from_descriptor(descriptor, kind)
            if label is None:
                continue  # Unknown descriptor shape (e.g. generics) — log-and-skip
            vertices[moniker] = {
                PROP_MONIKER: moniker,
                "label": label,
                PROP_REPO: repo,
                PROP_FILE_PATH: path,
                PROP_LANG: lang,
                PROP_TEST: is_test,
                PROP_EXTERNAL: False,
            }

        for occ in doc.get("occurrences", []):
            m = occ["symbol"]
            if not _LOCAL_RE.match(m):
                seen_in_occurrences.add(m)
            # Capture enclosing_range on Function vertices (BILL-56): definition
            # occurrences carry the function body span; stored in AGE so the
            # commit-provenance endpoint can resolve which functions were touched.
            if (occ.get("symbol_roles", 0) & 1) and "enclosing_range" in occ and m in vertices:
                vertices[m]["enclosing_range"] = occ["enclosing_range"]

    # External stubs: occurrence-referenced monikers with no SymbolInformation.
    for moniker in seen_in_occurrences:
        if moniker not in vertices:
            vertices[moniker] = {
                PROP_MONIKER: moniker,
                "label": VERTEX_EXTERNAL,
                PROP_REPO: repo,
                PROP_FILE_PATH: "",
                PROP_LANG: lang,
                PROP_TEST: False,
                PROP_EXTERNAL: True,
            }

    return list(vertices.values())


def extract_calls_edges(
    index: dict,
    repo: str,
) -> list[tuple[str, str, str]]:
    """Reconstruct CALLS edges via enclosing_range containment.

    For each document, finds every definition occurrence that carries an
    enclosing_range (= a function/method body). Then, for each ReadAccess
    occurrence of a callable symbol, finds the function whose body contains
    the reference position — that function is the caller.

    If no function body contains the reference (module-level call), the
    document's File vertex (moniker = relative_path) is used as the caller.

    Returns a list of (caller_moniker, EDGE_CALLS, callee_moniker) tuples.
    """
    # Build moniker → kind from all SymbolInformation entries so MethodSpecification
    # (Go interface methods, which use the "." suffix instead of "().") can be
    # identified as callable even when kind isn't in the occurrence itself.
    moniker_to_kind: dict[str, str] = {}
    for doc in index.get("documents", []):
        for sym in doc.get("symbols", []):
            kind = sym.get("kind")
            if kind:
                moniker_to_kind[sym["symbol"]] = kind

    edges: list[tuple[str, str, str]] = []

    for doc in index.get("documents", []):
        file_moniker = doc.get("relative_path", "")

        # Collect function bodies: definition occurrences with an enclosing_range.
        callers: list[tuple[str, list[int]]] = [
            (occ["symbol"], occ["enclosing_range"])
            for occ in doc.get("occurrences", [])
            if (occ.get("symbol_roles", 0) & 1) and "enclosing_range" in occ
        ]

        for occ in doc.get("occurrences", []):
            if not (occ.get("symbol_roles", 0) & 8):
                continue  # Not a ReadAccess reference
            callee_moniker = occ["symbol"]
            descriptor = _descriptor_from_moniker(callee_moniker)
            kind = moniker_to_kind.get(callee_moniker) or None
            if not is_callable(descriptor, kind):
                continue

            occ_range = occ["range"]
            caller_moniker = file_moniker  # Default: attribute to File vertex
            for func_moniker, enc_range in callers:
                if _is_inside(occ_range, enc_range):
                    caller_moniker = func_moniker
                    break

            edges.append((caller_moniker, EDGE_CALLS, callee_moniker))

    return edges


def extract_implements_edges(index: dict, repo: str) -> list[tuple[str, str, str]]:
    """Extract IMPLEMENTS edges from is_implementation relationships.

    Returns a list of (source_moniker, EDGE_IMPLEMENTS, target_moniker) tuples.
    """
    edges: list[tuple[str, str, str]] = []
    for doc in index.get("documents", []):
        for sym in doc.get("symbols", []):
            source = sym["symbol"]
            for rel in sym.get("relationships", []):
                if rel.get("is_implementation"):
                    edges.append((source, EDGE_IMPLEMENTS, rel["symbol"]))
    return edges


def build_vertex_cypher(vertex: dict) -> str:
    """Generate an idempotent Cypher MERGE statement for a vertex.

    The MERGE key is (moniker, repo) — the combination is globally unique
    across re-indexes and across repos sharing one graph.
    """
    label = vertex["label"]
    moniker = _cypher_str(vertex[PROP_MONIKER])
    repo = _cypher_str(vertex[PROP_REPO])
    file_path = _cypher_str(vertex.get(PROP_FILE_PATH, ""))
    lang = _cypher_str(vertex.get(PROP_LANG, ""))
    test = "true" if vertex.get(PROP_TEST) else "false"
    external = "true" if vertex.get(PROP_EXTERNAL) else "false"

    enc = vertex.get(PROP_ENCLOSING_RANGE)
    enc_clause = (
        f", v.{PROP_ENCLOSING_RANGE} = [{', '.join(str(n) for n in enc)}]"
        if enc is not None
        else ""
    )

    cypher = (
        f"MERGE (v:{label} {{{PROP_MONIKER}: '{moniker}', {PROP_REPO}: '{repo}'}}) "
        f"SET v.{PROP_FILE_PATH} = '{file_path}', v.{PROP_LANG} = '{lang}', "
        f"v.{PROP_TEST} = {test}, v.{PROP_EXTERNAL} = {external}{enc_clause} "
        f"RETURN v"
    )
    return _wrap_cypher(cypher)


def build_edge_cypher(
    src_moniker: str,
    edge_type: str,
    tgt_moniker: str,
    repo: str,
) -> str:
    """Generate an idempotent Cypher MERGE statement for an edge.

    MATCHes both endpoints by (moniker, repo) then MERGEs the directed edge.
    """
    src = _cypher_str(src_moniker)
    tgt = _cypher_str(tgt_moniker)
    r = _cypher_str(repo)

    cypher = (
        f"MATCH (src {{{PROP_MONIKER}: '{src}', {PROP_REPO}: '{r}'}}), "
        f"(tgt {{{PROP_MONIKER}: '{tgt}', {PROP_REPO}: '{r}'}}) "
        f"MERGE (src)-[e:{edge_type}]->(tgt) "
        f"RETURN e"
    )
    return _wrap_cypher(cypher)
