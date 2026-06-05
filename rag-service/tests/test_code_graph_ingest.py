"""Phase 0 red tests for BILL-55 — SCIP ingestion pipeline (Layer 1).

Tests describe the expected behavior of rag_service.code_graph.ingest pure
functions. All tests FAIL on current code — the module does not exist yet.

Layer 1 only: no FastAPI, no DB, no I/O. See test_code_graph_ingest_endpoint.py
for the Layer 2 endpoint tests.

Fixture data is minimal but grounded in design/scip-code-graph-spike.md: the
synthetic shapes+main module, covering Function, Struct, MethodSpecification,
Field, CALLS reconstruction via enclosing_range, IMPLEMENTS, and the External
stub pattern for stdlib symbols with no SymbolInformation.
"""

from __future__ import annotations

import pytest

from rag_service.code_graph.ingest import (
    _normalize_enc_range,
    build_edge_cypher,
    build_vertex_cypher,
    extract_calls_edges,
    extract_implements_edges,
    extract_vertices,
)
from rag_service.code_graph.schema import (
    EDGE_CALLS,
    EDGE_IMPLEMENTS,
    PROP_MONIKER,
    VERTEX_EXTERNAL,
    VERTEX_FUNCTION,
    VERTEX_TYPE,
)

# ── Monikers ──────────────────────────────────────────────────────────────────

_DESCRIBE = "scip-go gomod scipspike . scipspike/describe()."
_SHAPE_AREA = "scip-go gomod scipspike . `scipspike/shapes`/Shape#Area."
_PRINTLN = "scip-go gomod `fmt` v0 fmt/Println()."
_CIRCLE = "scip-go gomod scipspike . `scipspike/shapes`/Circle#"
_SHAPE = "scip-go gomod scipspike . `scipspike/shapes`/Shape#"


_TEST_REPO = "iansmith/scip-spike"

# ── Fixtures ──────────────────────────────────────────────────────────────────
# Field names are snake_case — what Python protobuf bindings produce.

MINIMAL_INDEX: dict = {
    "metadata": {
        "tool_info": {"name": "scip-go", "version": "0.2.7"},
        "project_root": "file:///tmp/scip-spike",
    },
    "documents": [
        {
            "language": "Go",
            "relative_path": "main.go",
            "symbols": [
                {"symbol": _DESCRIBE, "kind": "Function", "relationships": []},
            ],
            "occurrences": [
                # describe() definition — enclosing_range = full body span [10,0 .. 13,1]
                {
                    "symbol": _DESCRIBE,
                    "range": [10, 5, 13],
                    "symbol_roles": 1,  # Definition
                    "enclosing_range": [10, 0, 13, 1],
                },
                # Shape#Area. referenced at line 11 — inside describe's body
                {"symbol": _SHAPE_AREA, "range": [11, 4, 8], "symbol_roles": 8},
                # fmt.Println referenced inside describe's body — external/stdlib
                {"symbol": _PRINTLN, "range": [11, 12, 19], "symbol_roles": 8},
            ],
        },
        {
            "language": "Go",
            "relative_path": "shapes/circle.go",
            "symbols": [
                {
                    "symbol": _CIRCLE,
                    "kind": "Struct",
                    "relationships": [{"symbol": _SHAPE, "is_implementation": True}],
                },
                {
                    "symbol": _SHAPE_AREA,
                    "kind": "MethodSpecification",
                    "relationships": [],
                },
            ],
            "occurrences": [],
        },
    ],
    "external_symbols": [],
}

INDEX_WITH_LOCAL: dict = {
    "metadata": {"tool_info": {"name": "scip-go", "version": "0.2.7"}},
    "documents": [
        {
            "language": "Go",
            "relative_path": "main.go",
            "symbols": [
                {"symbol": "local 5", "kind": "Variable", "relationships": []},
                {"symbol": _DESCRIBE, "kind": "Function", "relationships": []},
            ],
            "occurrences": [],
        }
    ],
    "external_symbols": [],
}

# describe referenced at module level (no enclosing function in symbols)
INDEX_WITH_TOPLEVEL_CALL: dict = {
    "metadata": {"tool_info": {"name": "scip-go", "version": "0.2.7"}},
    "documents": [
        {
            "language": "Go",
            "relative_path": "main.go",
            "symbols": [
                {"symbol": _DESCRIBE, "kind": "Function", "relationships": []}
            ],
            "occurrences": [
                {"symbol": _DESCRIBE, "range": [0, 0, 8], "symbol_roles": 8}
            ],
        }
    ],
    "external_symbols": [],
}

# Relationship with is_reference (not is_implementation) — must not produce IMPLEMENTS
INDEX_WITH_REFERENCE_REL: dict = {
    "metadata": {"tool_info": {"name": "scip-go", "version": "0.2.7"}},
    "documents": [
        {
            "language": "Go",
            "relative_path": "main.go",
            "symbols": [
                {
                    "symbol": _DESCRIBE,
                    "kind": "Function",
                    "relationships": [{"symbol": _SHAPE, "is_reference": True}],
                }
            ],
            "occurrences": [],
        }
    ],
    "external_symbols": [],
}

_DESCRIBE_VERTEX: dict = {
    PROP_MONIKER: _DESCRIBE,
    "label": VERTEX_FUNCTION,
    "repo": _TEST_REPO,
    "file_path": "main.go",
    "lang": "go",
    "test": False,
    "external": False,
}


# ── Layer 1: extract_vertices ─────────────────────────────────────────────────


@pytest.fixture(scope="class")
def minimal_vertices_by_moniker():
    return {v[PROP_MONIKER]: v for v in extract_vertices(MINIMAL_INDEX, _TEST_REPO)}


class TestExtractVertices:
    def test_local_symbols_are_skipped(self):
        monikers = {v[PROP_MONIKER] for v in extract_vertices(INDEX_WITH_LOCAL, _TEST_REPO)}
        assert "local 5" not in monikers

    def test_defined_symbols_are_included(self, minimal_vertices_by_moniker):
        assert _DESCRIBE in minimal_vertices_by_moniker
        assert _CIRCLE in minimal_vertices_by_moniker
        assert _SHAPE_AREA in minimal_vertices_by_moniker

    def test_external_stub_created_for_unreferenced_symbol(self, minimal_vertices_by_moniker):
        """fmt.Println is referenced in occurrences but has no SymbolInformation.
        The ingester must create an External stub so CALLS edges have a target.
        """
        assert _PRINTLN in minimal_vertices_by_moniker, (
            f"External stub for {_PRINTLN!r} not created; "
            f"monikers present: {list(minimal_vertices_by_moniker)}"
        )
        assert minimal_vertices_by_moniker[_PRINTLN]["label"] == VERTEX_EXTERNAL

    def test_vertex_carries_repo(self, minimal_vertices_by_moniker):
        for moniker, v in minimal_vertices_by_moniker.items():
            assert v.get("repo") == _TEST_REPO, f"Vertex {moniker!r} missing repo field"

    def test_function_kind_gives_function_label(self, minimal_vertices_by_moniker):
        assert minimal_vertices_by_moniker[_DESCRIBE]["label"] == VERTEX_FUNCTION

    def test_struct_kind_gives_type_label(self, minimal_vertices_by_moniker):
        assert minimal_vertices_by_moniker[_CIRCLE]["label"] == VERTEX_TYPE


# ── Layer 1: extract_calls_edges ──────────────────────────────────────────────


@pytest.fixture(scope="class")
def minimal_calls_edges():
    return extract_calls_edges(MINIMAL_INDEX, _TEST_REPO)


class TestExtractCallsEdges:
    def test_calls_via_enclosing_range(self, minimal_calls_edges):
        """Shape#Area. at line 11 falls inside describe's enclosing_range [10,0,13,1]."""
        assert (_DESCRIBE, EDGE_CALLS, _SHAPE_AREA) in minimal_calls_edges, (
            f"Expected ({_DESCRIBE!r}, CALLS, {_SHAPE_AREA!r}); got: {minimal_calls_edges}"
        )

    def test_external_callee_produces_calls_edge(self, minimal_calls_edges):
        """fmt.Println referenced inside describe's body → CALLS edge to the external stub."""
        assert (_DESCRIBE, EDGE_CALLS, _PRINTLN) in minimal_calls_edges, (
            f"Expected ({_DESCRIBE!r}, CALLS, {_PRINTLN!r}); got: {minimal_calls_edges}"
        )

    def test_reference_outside_any_function_body_is_not_dropped(self):
        """A callable reference at module level must not be silently dropped.
        The caller must be attributed to the document's File vertex, not a Function.
        """
        edges = extract_calls_edges(INDEX_WITH_TOPLEVEL_CALL, _TEST_REPO)
        edges_to_describe = [(src, rel, tgt) for src, rel, tgt in edges if tgt == _DESCRIBE]
        assert edges_to_describe, "Module-level call to describe() was silently dropped"
        # The caller must not be a known Function moniker — it should be the File vertex.
        callers = {src for src, _, _ in edges_to_describe}
        assert _DESCRIBE not in callers, (
            "Module-level call incorrectly attributed to describe() itself (self-loop)"
        )
        function_monikers = {_DESCRIBE, _SHAPE_AREA, _PRINTLN, _CIRCLE, _SHAPE}
        assert not callers.intersection(function_monikers), (
            f"Module-level caller {callers} must be a File vertex, not a Function"
        )


# ── Layer 1: extract_implements_edges ────────────────────────────────────────


class TestExtractImplementsEdges:
    def test_implements_from_is_implementation(self):
        edges = extract_implements_edges(MINIMAL_INDEX, _TEST_REPO)
        assert (_CIRCLE, EDGE_IMPLEMENTS, _SHAPE) in edges, (
            f"Expected ({_CIRCLE!r}, IMPLEMENTS, {_SHAPE!r}); got: {edges}"
        )

    def test_non_implementation_relationships_excluded(self):
        edges = extract_implements_edges(INDEX_WITH_REFERENCE_REL, _TEST_REPO)
        assert (_DESCRIBE, EDGE_IMPLEMENTS, _SHAPE) not in edges


# ── Layer 1: build_vertex_cypher ─────────────────────────────────────────────


@pytest.fixture
def describe_vertex_cypher():
    return build_vertex_cypher(_DESCRIBE_VERTEX)


class TestBuildVertexCypher:
    def test_merge_uses_moniker_and_is_idempotent(self, describe_vertex_cypher):
        """MERGE with moniker as key; identical inputs must produce identical output."""
        assert "MERGE" in describe_vertex_cypher
        assert _DESCRIBE in describe_vertex_cypher
        assert build_vertex_cypher(_DESCRIBE_VERTEX) == describe_vertex_cypher

    def test_merge_contains_label(self, describe_vertex_cypher):
        assert VERTEX_FUNCTION in describe_vertex_cypher


# ── Layer 1: build_edge_cypher ───────────────────────────────────────────────


class TestBuildEdgeCypher:
    def test_edge_cypher_shape(self):
        """Single call covers: MERGE present, both monikers present, edge type present."""
        cypher = build_edge_cypher(_DESCRIBE, EDGE_CALLS, _PRINTLN, _TEST_REPO)
        assert "MERGE" in cypher
        assert _DESCRIBE in cypher
        assert _PRINTLN in cypher
        assert EDGE_CALLS in cypher


# ── Layer 1: _normalize_enc_range ─────────────────────────────────────────────


class TestNormalizeEncRange:
    def test_four_element_unchanged(self):
        """4-element ranges are returned as-is."""
        assert _normalize_enc_range([10, 0, 13, 1]) == [10, 0, 13, 1]

    def test_three_element_becomes_single_line_four(self):
        """3-element [line, startChar, endChar] → 4-element [line, startChar, line, endChar]."""
        result = _normalize_enc_range([5, 2, 9])
        assert result == [5, 2, 5, 9]

    def test_malformed_short_returned_unchanged(self):
        """Inputs shorter than 3 elements are returned unchanged (caller guards)."""
        assert _normalize_enc_range([]) == []
        assert _normalize_enc_range([1]) == [1]

    def test_extract_calls_edges_handles_three_element_enclosing_range(self):
        """CALLS edges are built correctly when enclosing_range is 3-element (scip-go).

        scip-go emits 3-element enclosing_range [line, startChar, endChar] for
        single-line function bodies.  After normalization to [line, 0, line, endChar]
        containment must work correctly for references on the same line.
        """
        # MyFunc body is on line 52 only: enclosing_range [52, 0, 48] →
        # normalized to [52, 0, 52, 48].  Helper() is called at char 19 on
        # line 52 — inside the normalized body span.
        index = {
            "metadata": {"tool_info": {"name": "scip-go"}},
            "documents": [
                {
                    "relative_path": "pkg/foo.go",
                    "symbols": [
                        {"symbol": "scip-go gomod pkg v1.0.0 pkg/MyFunc().", "kind": "Function"},
                        {"symbol": "scip-go gomod pkg v1.0.0 pkg/Helper().", "kind": "Function"},
                    ],
                    "occurrences": [
                        # MyFunc definition — 3-element enclosing_range (single-line body)
                        {
                            "symbol": "scip-go gomod pkg v1.0.0 pkg/MyFunc().",
                            "symbol_roles": 1,  # Definition
                            "range": [52, 5, 11],
                            "enclosing_range": [52, 0, 48],  # 3-element: line 52, chars 0–48
                        },
                        # ReadAccess of Helper on the same line (char 19–25, inside [52,0,52,48])
                        {
                            "symbol": "scip-go gomod pkg v1.0.0 pkg/Helper().",
                            "symbol_roles": 8,  # ReadAccess
                            "range": [52, 19, 25],
                        },
                    ],
                }
            ],
        }
        edges = extract_calls_edges(index, "test/repo")
        # Helper() should be attributed to MyFunc() (not the file vertex)
        callee = "scip-go gomod pkg v1.0.0 pkg/Helper()."
        caller = "scip-go gomod pkg v1.0.0 pkg/MyFunc()."
        assert (caller, "CALLS", callee) in edges
