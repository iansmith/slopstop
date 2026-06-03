"""Phase 0 red tests for BILL-54 — AGE code graph schema & data model.

These tests describe and validate the behavior of the rag_service.code_graph.schema
module implemented in BILL-54 (Phase 0 red tests, now green).

Layer split (design/rag-service-testing.md):
  - All Layer 1 — pure deterministic functions, no FastAPI, no postgres, no AGE.

Grounded in design/scip-code-graph-spike.md (Parts 1–3), which validated the
data model against scip-go, scip-python, and scip-typescript on both synthetic
and real-repo (louis14, 343 files) inputs.
"""

from __future__ import annotations

import pytest

from rag_service.code_graph.schema import (
    # Vertex label constants
    VERTEX_PACKAGE,
    VERTEX_FILE,
    VERTEX_TYPE,
    VERTEX_FUNCTION,
    VERTEX_FIELD,
    VERTEX_EXTERNAL,
    # Edge type constants
    EDGE_CONTAINS,
    EDGE_DEFINES,
    EDGE_CALLS,
    EDGE_IMPLEMENTS,
    EDGE_REFERENCES,
    # Pure classification helpers
    vertex_type_from_descriptor,
    is_callable,
)


# ---------------------------------------------------------------------------
# Constants — sanity checks (labels must be non-empty strings)
# ---------------------------------------------------------------------------


def test_vertex_labels_are_nonempty_strings():
    for label in (VERTEX_PACKAGE, VERTEX_FILE, VERTEX_TYPE, VERTEX_FUNCTION,
                  VERTEX_FIELD, VERTEX_EXTERNAL):
        assert isinstance(label, str) and label, f"Expected non-empty str, got {label!r}"


def test_edge_types_are_nonempty_strings():
    for edge in (EDGE_CONTAINS, EDGE_DEFINES, EDGE_CALLS,
                 EDGE_IMPLEMENTS, EDGE_REFERENCES):
        assert isinstance(edge, str) and edge, f"Expected non-empty str, got {edge!r}"


def test_vertex_labels_are_distinct():
    labels = [VERTEX_PACKAGE, VERTEX_FILE, VERTEX_TYPE,
              VERTEX_FUNCTION, VERTEX_FIELD, VERTEX_EXTERNAL]
    assert len(labels) == len(set(labels)), "Vertex labels must all be distinct"


def test_edge_types_are_distinct():
    edges = [EDGE_CONTAINS, EDGE_DEFINES, EDGE_CALLS,
             EDGE_IMPLEMENTS, EDGE_REFERENCES]
    assert len(edges) == len(set(edges)), "Edge types must all be distinct"


# ---------------------------------------------------------------------------
# vertex_type_from_descriptor — descriptor suffix → vertex label
#
# Reference: spike §3.1 descriptor grammar + §4.1 vertex mapping + Part 2
# "where they diverge" #1 (kind is scip-go-only; suffix is portable).
# ---------------------------------------------------------------------------


def test_slash_suffix_is_package():
    """Descriptor ending in / = Package (namespace)."""
    # Go: `scipspike/shapes`/
    assert vertex_type_from_descriptor("`scipspike/shapes`/") == VERTEX_PACKAGE
    # Python: plain module path also ends in /
    assert vertex_type_from_descriptor("shapes/") == VERTEX_PACKAGE


def test_hash_suffix_is_type():
    """Descriptor ending in # = Type (struct / interface / class)."""
    assert vertex_type_from_descriptor("Circle#") == VERTEX_TYPE
    assert vertex_type_from_descriptor("Shape#") == VERTEX_TYPE


def test_callable_suffix_is_function():
    """Descriptor ending in (). = Function/Method (all three indexers)."""
    assert vertex_type_from_descriptor("describe().") == VERTEX_FUNCTION
    assert vertex_type_from_descriptor("Circle#Area().") == VERTEX_FUNCTION
    # TypeScript / Python interface methods also use (). (not . like Go)
    assert vertex_type_from_descriptor("Shape#area().") == VERTEX_FUNCTION


def test_dot_suffix_no_kind_defaults_to_field():
    """Descriptor ending in . with no kind = Field (safe default).

    The . suffix is ambiguous between Field and Go MethodSpecification; without
    a kind hint (TS/Python don't emit kind) we default to Field and let the
    caller override if they have kind information.
    """
    assert vertex_type_from_descriptor("Circle#R.") == VERTEX_FIELD


def test_dot_suffix_method_spec_kind_is_function():
    """Go interface method spec: . suffix + kind='MethodSpecification' = Function."""
    assert vertex_type_from_descriptor("Shape#Area.", kind="MethodSpecification") == VERTEX_FUNCTION


def test_dot_suffix_field_kind_is_field():
    """Explicit Field kind confirms field even when ambiguous."""
    assert vertex_type_from_descriptor("Circle#R.", kind="Field") == VERTEX_FIELD


def test_local_symbol_returns_none():
    """local N symbols are function-scoped, not globally addressable — skip."""
    assert vertex_type_from_descriptor("local 0") is None
    assert vertex_type_from_descriptor("local 42") is None


def test_external_moniker_with_no_kind_uses_suffix():
    """External callees (e.g. stdlib) have no kind; classify by suffix as usual."""
    # fmt.Println has callable suffix — should resolve as Function
    assert vertex_type_from_descriptor("fmt/Println().") == VERTEX_FUNCTION


def test_kind_method_is_function():
    """Explicit kind='Method' → Function regardless of suffix."""
    assert vertex_type_from_descriptor("Circle#Area().", kind="Method") == VERTEX_FUNCTION


def test_kind_struct_is_type():
    """Explicit kind='Struct' → Type."""
    assert vertex_type_from_descriptor("Circle#", kind="Struct") == VERTEX_TYPE


def test_kind_interface_is_type():
    """Explicit kind='Interface' → Type."""
    assert vertex_type_from_descriptor("Shape#", kind="Interface") == VERTEX_TYPE


# ---------------------------------------------------------------------------
# is_callable — portable callable-detection rule (spike Part 2, divergence #2)
#
# Portable rule: callable if descriptor ends in (). OR kind is in
# {Function, Method, MethodSpecification, Constructor}.
# ---------------------------------------------------------------------------


def test_callable_suffix_always_callable():
    """Anything ending in (). is callable — works for all three indexers."""
    assert is_callable("describe().") is True
    assert is_callable("Circle#Area().") is True
    assert is_callable("fmt/Println().") is True
    # TS/Python interface methods also use ().
    assert is_callable("Shape#area().") is True


def test_method_spec_kind_is_callable():
    """Go interface method specs: . suffix but kind=MethodSpecification → callable."""
    assert is_callable("Shape#Area.", kind="MethodSpecification") is True


def test_function_kind_is_callable():
    """Explicit kind=Function → callable even without (). suffix."""
    assert is_callable("describe().", kind="Function") is True


def test_constructor_kind_is_callable():
    """Constructor kind is callable (TypeScript)."""
    assert is_callable("Circle#`<constructor>`().", kind="Constructor") is True


def test_field_not_callable():
    assert is_callable("Circle#R.") is False
    assert is_callable("Circle#R.", kind="Field") is False


def test_type_not_callable():
    assert is_callable("Circle#") is False
    assert is_callable("Circle#", kind="Struct") is False


def test_package_not_callable():
    assert is_callable("`scipspike/shapes`/") is False


def test_local_not_callable():
    """Local symbols are not callable (we skip them entirely)."""
    assert is_callable("local 0") is False


def test_dot_suffix_no_kind_not_callable():
    """Ambiguous . without MethodSpecification kind → not callable (safe default)."""
    assert is_callable("Shape#Area.") is False
