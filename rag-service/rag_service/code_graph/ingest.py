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

import html as _html
import logging
import os
import re

from rag_service.code_graph.schema import (
    EDGE_CALLS,
    EDGE_IMPLEMENTS,
    PROP_CYCLOMATIC_COMPLEXITY,
    PROP_ENCLOSING_RANGE,
    PROP_EXTERNAL,
    PROP_FILE_PATH,
    PROP_LANG,
    PROP_LAST_INDEXED_SHA,
    PROP_MONIKER,
    PROP_RANGE,
    PROP_REPO,
    PROP_TEST,
    VERTEX_EXTERNAL,
    VERTEX_FILE,
    VERTEX_FUNCTION,
    VERTEX_REPO,
    _LOCAL_RE,
    is_callable,
    vertex_type_from_descriptor,
)
from rag_service.harvesters._common import ChunkRow

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


def _list_prop_clause(prop: str, val: list | None) -> str:
    """Return a Cypher SET clause fragment for an integer-list vertex property.

    Returns ``', v.PROP = [n, n, …]'`` when *val* is not None, else ``''``.
    Used by :func:`build_vertex_cypher` for range-shaped properties.
    """
    if val is None:
        return ""
    return f", v.{prop} = [{', '.join(str(n) for n in val)}]"


def _int_prop_clause(prop: str, val: int | None) -> str:
    """Return a Cypher SET clause fragment for an optional integer vertex property.

    Returns ``', v.PROP = N'`` when *val* is not None, else ``''``.
    Must use ``is not None`` (not ``if val``) so that CC=0 is written correctly.
    """
    if val is None:
        return ""
    return f", v.{prop} = {val}"


def _normalize_enc_range(enc_range: list[int]) -> list[int]:
    """Normalize a SCIP range to 4-element [startLine, startChar, endLine, endChar].

    SCIP ranges are either 3-element [line, startChar, endChar] for single-line
    spans or 4-element. Normalizing to 4-element at every ingestion boundary
    keeps the DB invariant uniform and lets _is_inside always unpack four values.
    Returns the input unchanged if it is already 4-element (or malformed).
    """
    if len(enc_range) == 3:
        return [enc_range[0], enc_range[1], enc_range[0], enc_range[2]]
    return enc_range


def _lookup_cc(file_cc: dict[str, int], short: str, line: int | None) -> int | None:
    """Look up cyclomatic complexity using line-qualified key first, name-only fallback.

    ``file_cc`` keys come from :func:`_lizard_file_cc` which stores both
    ``"start_line:name"`` (preferred) and ``"name"`` (first-occurrence fallback).
    Trying the line-qualified key first ensures same-named methods in a file get
    their own correct CC; the name-only fallback handles cc_maps built without line
    info (manual test fixtures) or when PROP_RANGE wasn't set on a vertex.
    """
    if line is not None:
        cc = file_cc.get(f"{line}:{short}")
        if cc is not None:
            return cc
    return file_cc.get(short)


def _lizard_file_cc(abs_path: str) -> dict[str, int]:
    """Return CC entries for all functions in *abs_path* via lizard.

    Keys use the line-qualified form ``"<start_line>:<name>"`` so two methods
    that share a short name (e.g. ``A.handle`` and ``B.handle``) get distinct
    entries.  A name-only key is also stored (first-occurrence-wins via
    ``setdefault``) as a fallback for callers that can't supply a line number.

    Returns an empty dict when lizard is unavailable or the file can't be parsed.
    """
    try:
        import lizard  # type: ignore[import]
        file_info = lizard.analyze_file(abs_path)
        result: dict[str, int] = {}
        for fn in file_info.function_list:
            result[f"{fn.start_line}:{fn.name}"] = fn.cyclomatic_complexity
            result.setdefault(fn.name, fn.cyclomatic_complexity)
        return result
    except Exception:
        return {}


def _is_inside(occ_range: list[int], enc_range: list[int]) -> bool:
    """Return True if the start of occ_range falls inside enc_range.

    enc_range must be 4-element [startLine, startChar, endLine, endChar].
    Call sites (extract_vertices, extract_calls_edges) normalize SCIP 3-element
    single-line spans via _normalize_enc_range before storing or passing enc_range.
    occ_range may be 3-element (single-line) or 4-element.
    Returns False for malformed enc_range (fewer than 4 elements).
    """
    if len(enc_range) < 4:
        return False
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


def _wrap_cypher(cypher: str, columns: str = "r agtype") -> str:
    """Wrap a Cypher statement for execution via AGE's SQL function.

    ``columns`` is the ``AS (...)`` alias list for the ``SELECT * FROM cypher(...)``
    wrapper.  Defaults to ``"r agtype"`` (single opaque column); pass a different
    value for queries that project named columns (e.g. ``"sha agtype"``).
    """
    return f"SELECT * FROM cypher('{_GRAPH_NAME}', {_CYPHER_TAG} {cypher} {_CYPHER_TAG}) AS ({columns})"


# ── Public API ────────────────────────────────────────────────────────────────


def extract_vertices(
    index: dict,
    repo: str,
    *,
    cc_map: dict[str, dict[str, int]] | None = None,
) -> list[dict]:
    """Extract all vertex dicts from a SCIP JSON index.

    Creates:
    - One File vertex per document (moniker = relative_path).
    - One vertex per non-local SymbolInformation entry, labelled by descriptor suffix.
    - One External stub vertex for each moniker referenced in occurrences
      that has no corresponding SymbolInformation (e.g. stdlib, cross-module deps).

    All vertices carry the `repo` property for multi-repo graph isolation.

    cc_map: optional ``{relative_path: {key: cc}}`` pre-computed by the caller
    (e.g. via :func:`build_lizard_cc_map`).  Keys are either
    ``"<start_line>:<name>"`` (preferred, from :func:`_lizard_file_cc`) or plain
    ``"<name>"`` (fallback / manual test fixtures).  Cyclomatic complexity is
    assigned in a post-occurrence pass so line numbers from PROP_RANGE are
    available for disambiguation.  The caller is responsible for I/O;
    ``extract_vertices`` remains a pure Layer-1 function.
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
            vertex: dict = {
                PROP_MONIKER: moniker,
                "label": label,
                PROP_REPO: repo,
                PROP_FILE_PATH: path,
                PROP_LANG: lang,
                PROP_TEST: is_test,
                PROP_EXTERNAL: False,
            }
            if label == VERTEX_FUNCTION:
                # NOTE(scip-cc): SCIP-native CC when available; cast to int so
                # floats/strings from future indexers never embed unquoted in Cypher.
                # No standard SCIP indexer emits this field today — lizard via the
                # post-occurrence pass below is the actual source.
                scip_cc = sym.get("cyclomatic_complexity")
                if scip_cc is not None:
                    try:
                        vertex[PROP_CYCLOMATIC_COMPLEXITY] = int(scip_cc)
                    except (ValueError, TypeError):
                        pass  # Non-numeric — skip; lizard post-pass may fill it
            vertices[moniker] = vertex

        for occ in doc.get("occurrences", []):
            m = occ["symbol"]
            if not _LOCAL_RE.match(m):
                seen_in_occurrences.add(m)
            if (occ.get("symbol_roles", 0) & 1) and m in vertices:
                v = vertices[m]
                # Capture the name-token range on every definition occurrence so
                # the query endpoints can return a line number (BILL-58).
                if "range" in occ:
                    v[PROP_RANGE] = occ["range"]
                # Capture enclosing_range on Function vertices (BILL-56): the
                # function-body span used by commit-provenance TOUCHES edge resolution.
                # Normalize to 4-element here so the DB invariant is always uniform
                # and _is_inside can unconditionally unpack four values.
                if "enclosing_range" in occ and v["label"] == VERTEX_FUNCTION:
                    v["enclosing_range"] = _normalize_enc_range(occ["enclosing_range"])

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

    # Lizard CC post-pass: assign from cc_map using line numbers now available from
    # the occurrence loop above (PROP_RANGE is set on definition occurrences).
    # Two-pass design is intentional: SCIP-native CC is assigned per-symbol (where
    # the symbol dict lives), but lizard CC needs PROP_RANGE for line-qualified
    # disambiguation, and PROP_RANGE is only available after occurrence processing.
    # The "already has CC" guard ensures SCIP-native values are never overwritten.
    #
    # Line assumption: PROP_RANGE[0] (name-token start line) is used as a proxy
    # for lizard's fn.start_line (function-def start line).  For well-formed SCIP
    # output these are the same line; if they ever diverge the lookup silently falls
    # back to the name-only key in _lookup_cc.
    if cc_map:
        for moniker, v in vertices.items():
            if v["label"] != VERTEX_FUNCTION or PROP_CYCLOMATIC_COMPLEXITY in v:
                continue
            file_cc = cc_map.get(v.get(PROP_FILE_PATH, ""), {})
            if not file_cc:
                continue
            short = _short_name(moniker)
            rng = v.get(PROP_RANGE)
            cc = _lookup_cc(file_cc, short, rng[0] if rng else None)
            if cc is not None:
                v[PROP_CYCLOMATIC_COMPLEXITY] = cc

    return list(vertices.values())


def build_lizard_cc_map(index: dict, source_root: str) -> dict[str, dict[str, int]]:
    """Return ``{relative_path: {fn_name: cc}}`` for all documents in the SCIP index.

    Calls lizard on each source file under ``source_root``. Files that don't exist
    or that lizard can't parse return an empty inner dict (non-fatal). This function
    does I/O and is intended for the ingestion endpoint layer, not Layer-1 tests.

    Pass the result to :func:`extract_vertices` as ``cc_map`` to annotate Function
    nodes with cyclomatic complexity without making ``extract_vertices`` itself do I/O.
    """
    return {
        rel: _lizard_file_cc(os.path.join(source_root, rel))
        for doc in index.get("documents", [])
        if (rel := doc.get("relative_path", ""))
    }


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
        # Normalize to 4-element here so _is_inside receives a uniform format.
        callers: list[tuple[str, list[int]]] = [
            (occ["symbol"], _normalize_enc_range(occ["enclosing_range"]))
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

            if "range" not in occ:
                logging.debug(
                    "skipping ReadAccess occurrence without range: symbol=%s",
                    occ.get("symbol", "<unknown>"),
                )
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


def _strip_html(text: str) -> str:
    """Strip HTML tags, unescape entities, and collapse whitespace.

    Tags are removed first so that entity-encoded angle brackets (e.g.
    ``&lt;foo&gt;``) are not mistaken for tags after unescaping.
    """
    no_tags = re.sub(r"<[^>]+>", " ", text)
    unescaped = _html.unescape(no_tags)
    return " ".join(unescaped.split())


def _short_name(moniker: str) -> str:
    """Extract the short symbol name from a SCIP moniker's descriptor.

    Examples:
      "scip-go gomod pkg . pkg/linesOverlap()."      -> "linesOverlap"
      "scip-go gomod pkg . pkg/Scheduler#runqGet()." -> "runqGet"
      "scip-go gomod pkg . pkg/Scheduler#"           -> "Scheduler"
      "scip-python ... rag_service/ingest/foo()."    -> "foo"
    """
    # Descriptor is the last space-separated token
    descriptor = moniker.split(" ")[-1]
    # Strip trailing punctuation: ()., #, /
    descriptor = descriptor.rstrip(".").rstrip("()")
    # Split on path/type separators and take the last non-empty segment
    parts = re.split(r"[/#]", descriptor)
    name = next((p for p in reversed(parts) if p), descriptor)
    return name


def extract_docstring_rows(index: dict, repo: str) -> list[ChunkRow]:
    """Extract SCIP SymbolInformation.documentation into embeddable ChunkRows.

    One row per symbol that has non-empty documentation after HTML stripping.
    Symbols with no documentation key, an empty list, or whitespace-only
    content after stripping are skipped.

    Row identity: source='scip', ticket_id=moniker, provenance='scip',
    kind='docstring', seq=0.  One row per symbol (no seq banding needed).

    Deduplication: some indexers (e.g. scip-go) assign the same moniker to
    distinct struct fields named `_` in the same package.  The unique index
    enforces one row per (source, repo, moniker) — only the first occurrence
    of any repeated moniker is kept.
    """
    rows: list[ChunkRow] = []
    seen_monikers: set[str] = set()
    for doc_entry in index.get("documents", []):
        for sym in doc_entry.get("symbols", []):
            if "symbol" not in sym:
                continue
            moniker = sym["symbol"]
            # Local symbols (e.g. "local 0") are scoped to one document; their
            # monikers are not globally unique and would collide across files in
            # the unique index (source, repo, ticket_id, provenance, kind, seq).
            if _LOCAL_RE.match(moniker):
                continue
            if moniker in seen_monikers:
                continue
            raw_docs = sym.get("documentation")
            if not raw_docs:
                continue
            # Join multiple doc strings, strip HTML from the combined text
            combined = _strip_html(" ".join(raw_docs))
            if not combined:
                continue
            seen_monikers.add(moniker)
            short = _short_name(moniker)
            text = f"{short}: {combined}"
            rows.append(
                ChunkRow(
                    source="scip",
                    ticket_id=moniker,
                    provenance="scip",
                    kind="docstring",
                    seq=0,
                    text=text,
                    code_refs=[],
                    ticket_refs=[],
                    moniker=moniker,
                    repo=repo,
                )
            )
    return rows


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

    range_clause = _list_prop_clause(PROP_RANGE, vertex.get(PROP_RANGE))
    enc_clause   = _list_prop_clause(PROP_ENCLOSING_RANGE, vertex.get(PROP_ENCLOSING_RANGE))
    cc_clause    = (
        _int_prop_clause(PROP_CYCLOMATIC_COMPLEXITY, vertex.get(PROP_CYCLOMATIC_COMPLEXITY))
        if label == VERTEX_FUNCTION else ""
    )

    cypher = (
        f"MERGE (v:{label} {{{PROP_MONIKER}: '{moniker}', {PROP_REPO}: '{repo}'}}) "
        f"SET v.{PROP_FILE_PATH} = '{file_path}', v.{PROP_LANG} = '{lang}', "
        f"v.{PROP_TEST} = {test}, v.{PROP_EXTERNAL} = {external}{range_clause}{enc_clause}{cc_clause} "
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


def build_repo_vertex_cypher(repo: str, head_sha: str) -> str:
    """Generate an idempotent Cypher MERGE/SET for the :Repo tracking vertex.

    The Repo vertex is keyed on ``repo`` alone (one per repository). After
    each successful full index slopstop-ingest calls this to record the HEAD
    SHA so subsequent runs can skip when HEAD is unchanged (BILL-59
    reconcile-on-start).
    """
    r = _cypher_str(repo)
    sha = _cypher_str(head_sha)
    cypher = (
        f"MERGE (r:{VERTEX_REPO} {{{PROP_REPO}: '{r}'}}) "
        f"SET r.{PROP_LAST_INDEXED_SHA} = '{sha}' "
        f"RETURN r"
    )
    return _wrap_cypher(cypher)


def build_get_repo_sha_cypher(repo: str) -> str:
    """Generate a Cypher SELECT for the :Repo tracking vertex.

    Returns the ``last_indexed_sha`` property as an agtype column named
    ``sha``.  Returns an empty result set when no Repo vertex exists yet
    (first-time index — caller should treat missing as ``None``).
    """
    r = _cypher_str(repo)
    cypher = (
        f"MATCH (r:{VERTEX_REPO} {{{PROP_REPO}: '{r}'}}) "
        f"RETURN r.{PROP_LAST_INDEXED_SHA} AS sha"
    )
    return _wrap_cypher(cypher, columns="sha agtype")


def parse_repo_sha(rows: list) -> str | None:
    """Extract ``last_indexed_sha`` from a :Repo vertex query result.

    ``run_cypher`` returns rows as tuples; this query projects a single
    ``sha agtype`` column so each row is a 1-tuple.  AGE encodes string
    values with surrounding double-quotes (e.g. ``'"abc123"'``), which are
    stripped before returning.

    Returns ``None`` when the result set is empty (vertex not yet created) or
    when the property value is null/empty.
    """
    if not rows:
        return None
    sha_raw = rows[0][0] or ""
    return sha_raw.strip().strip('"') or None
