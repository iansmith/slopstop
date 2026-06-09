"""Phase 0 red tests for BILL-90 — cyclomatic_complexity on Function nodes.

BILL-89 prerequisite (tracked in BILL-90): every Function node written or
updated by the post-commit re-indexer carries ``cyclomatic_complexity: int``.
These Layer 1 tests verify the schema constant exists and that
``build_vertex_cypher`` includes the CC SET clause correctly.

All tests FAIL on current code (PROP_CYCLOMATIC_COMPLEXITY not yet in schema.py,
build_vertex_cypher doesn't handle CC). They turn GREEN once BILL-90 work lands.

Exception: test_build_vertex_cypher_omits_cc_when_absent passes on current
code by accident (CC is never written today) — it stays green after correct
implementation, serving as a regression guard.

Layer 1 only — no FastAPI, no DB, no I/O.

Test command:
    cd rag-service && pytest tests/test_bill90_cc_schema.py -v
"""

from __future__ import annotations

import pytest

from rag_service.code_graph import schema as _schema
from rag_service.code_graph.ingest import build_vertex_cypher
from rag_service.code_graph.schema import (
    PROP_MONIKER,
    PROP_REPO,
    VERTEX_FUNCTION,
)

_REPO = "iansmith/slopstop"
_FN_MONIKER = "scip-python python pip slopstop . rag_service/search/do_search()."

_CC_KEY = "cyclomatic_complexity"


def _fn_vertex(cc=None):
    v = {"label": VERTEX_FUNCTION, PROP_MONIKER: _FN_MONIKER, PROP_REPO: _REPO}
    if cc is not None:
        v[_CC_KEY] = cc
    return v


# ---------------------------------------------------------------------------
# Schema constant
# ---------------------------------------------------------------------------


def test_schema_exports_prop_cyclomatic_complexity():
    """schema.py must export PROP_CYCLOMATIC_COMPLEXITY.

    BILL-90 / BILL-89: CC stored as a node property on Function vertices.
    The constant ensures all code uses a single authoritative key string.
    """
    assert hasattr(_schema, "PROP_CYCLOMATIC_COMPLEXITY"), (
        "schema.py is missing PROP_CYCLOMATIC_COMPLEXITY — "
        "BILL-90 requires this constant for CC storage on Function nodes."
    )


def test_prop_cyclomatic_complexity_value():
    """PROP_CYCLOMATIC_COMPLEXITY must equal the expected AGE property key string."""
    val = getattr(_schema, "PROP_CYCLOMATIC_COMPLEXITY", None)
    assert val == _CC_KEY, (
        f"PROP_CYCLOMATIC_COMPLEXITY={val!r}, expected {_CC_KEY!r} — "
        "Cypher queries and downstream tools depend on this exact string."
    )


# ---------------------------------------------------------------------------
# build_vertex_cypher — CC inclusion/exclusion
# ---------------------------------------------------------------------------


def test_build_vertex_cypher_sets_cc_when_provided():
    """build_vertex_cypher must emit a cyclomatic_complexity SET clause when vertex has it."""
    v = _fn_vertex(cc=7)
    cypher = build_vertex_cypher(v)
    assert _CC_KEY in cypher, (
        "build_vertex_cypher omits cyclomatic_complexity even when set — "
        "BILL-90 requires CC to be written to the Function node in the graph."
    )
    assert "7" in cypher, (
        "CC value (7) not found in Cypher emitted by build_vertex_cypher."
    )


def test_build_vertex_cypher_omits_cc_when_absent():
    """build_vertex_cypher must NOT emit CC SET clause when key is absent.

    Prevents wiping an existing CC value on re-index when the SCIP source
    doesn't provide CC for a given pass. MERGE semantics keep un-SET
    properties intact — omitting is intentional.

    NOTE: this test passes on pre-BILL-90 code by accident (CC not implemented
    at all). It acts as a regression guard post-implementation.
    """
    v = _fn_vertex(cc=None)
    cypher = build_vertex_cypher(v)
    assert _CC_KEY not in cypher, (
        "build_vertex_cypher sets cyclomatic_complexity even when absent — "
        "would null-wipe existing values on re-index without CC source."
    )


def test_build_vertex_cypher_cc_zero_is_written_not_skipped():
    """CC=0 must be written; must not be treated as falsy/absent.

    A degenerate function (e.g. a trivial getter) can legitimately have CC=1
    or even CC=0. Checking `if cc:` instead of `if cc is not None:` would
    silently drop it.
    """
    v = _fn_vertex(cc=0)
    cypher = build_vertex_cypher(v)
    assert _CC_KEY in cypher, (
        "build_vertex_cypher skips CC=0 as if absent — "
        "use 'cc is not None' check, not 'if cc'."
    )


def test_build_vertex_cypher_cc_high_value():
    """Large CC values (e.g. 42) must be written correctly."""
    v = _fn_vertex(cc=42)
    cypher = build_vertex_cypher(v)
    assert _CC_KEY in cypher
    assert "42" in cypher, (
        "CC value (42) not found in Cypher — numeric formatting issue."
    )
