"""Red tests for code-review findings on BILL-90 (PR #95).

These tests describe the DESIRED behavior after each finding is fixed.
All FAIL on the current code — that's intentional.

Findings covered:
  #1 (CRITICAL) — CodeGraphIngestRequest missing source_root, so build_lizard_cc_map
                  can never be called from the endpoint (dead CC pipeline).
  #2 (MEDIUM)   — _lizard_file_cc uses {fn.name: cc} dict comprehension; two methods
                  with the same short name in one file silently clobber each other.
  #5 (PLAUSIBLE) — sym.get("cyclomatic_complexity") is stored raw; a SCIP indexer
                   returning a float or string produces invalid unquoted Cypher.

Test command (from rag-service/):
    .venv/bin/pytest tests/test_bill90_cr_findings.py -v
"""

from __future__ import annotations

import textwrap

import pytest

from rag_service.code_graph.ingest import build_lizard_cc_map, extract_vertices
from rag_service.code_graph.schema import VERTEX_FUNCTION
from rag_service.models import CodeGraphIngestRequest

_REPO = "iansmith/slopstop"
_CC_KEY = "cyclomatic_complexity"
_FN_MONIKER = "scip-python python pip mymod . mymod/compute()."

_INDEX_WITH_FLOAT_CC: dict = {
    "metadata": {"tool_info": {"name": "scip-python", "version": "0.1.0"}},
    "documents": [
        {
            "relative_path": "src/compute.py",
            "symbols": [
                {
                    "symbol": _FN_MONIKER,
                    "cyclomatic_complexity": 3.0,
                    "relationships": [],
                }
            ],
            "occurrences": [],
        }
    ],
}

_INDEX_WITH_STR_CC: dict = {
    "metadata": {"tool_info": {"name": "scip-python", "version": "0.1.0"}},
    "documents": [
        {
            "relative_path": "src/compute.py",
            "symbols": [
                {
                    "symbol": _FN_MONIKER,
                    "cyclomatic_complexity": "high",
                    "relationships": [],
                }
            ],
            "occurrences": [],
        }
    ],
}


# ---------------------------------------------------------------------------
# Finding #1 — CodeGraphIngestRequest must have source_root
# ---------------------------------------------------------------------------


def test_ingest_request_has_source_root():
    """CodeGraphIngestRequest must expose source_root so the endpoint can call
    build_lizard_cc_map.

    Without this field the CC pipeline is dead: extract_vertices always receives
    cc_map=None and no Function node ever gets cyclomatic_complexity.
    """
    assert "source_root" in CodeGraphIngestRequest.model_fields, (
        "CodeGraphIngestRequest is missing 'source_root' — "
        "add it (Optional[str] = None) so the ingest endpoint can build the CC map "
        "(code-review Finding #1)."
    )


# ---------------------------------------------------------------------------
# Finding #2 — duplicate method names must not be clobbered in the CC map
# ---------------------------------------------------------------------------


def test_lizard_cc_map_preserves_duplicate_fn_names(tmp_path):
    """When two methods share a short name (A.handle and B.handle),
    build_lizard_cc_map must preserve both entries.

    Current code: {fn.name: fn.cyclomatic_complexity} — last write wins.
    After fix: keys must distinguish the two (e.g. qualified name or start line)
    so neither CC value is silently dropped.
    """
    src = tmp_path / "dup_names.py"
    src.write_text(
        textwrap.dedent("""\
            class A:
                def handle(self, x):
                    if x:
                        return 1
                    return 2

            class B:
                def handle(self):
                    return 42
        """)
    )
    index = {"documents": [{"relative_path": "dup_names.py"}]}
    cc_map = build_lizard_cc_map(index, str(tmp_path))
    file_cc = cc_map.get("dup_names.py", {})
    assert len(file_cc) >= 2, (
        f"Expected ≥2 entries for A.handle and B.handle; "
        f"got {len(file_cc)}: {file_cc!r} "
        f"(code-review Finding #2 — {'{fn.name: cc}'} dict clobbers the first entry)."
    )


# ---------------------------------------------------------------------------
# Finding #5 — SCIP-native CC must be cast to int before storage
# ---------------------------------------------------------------------------


def test_extract_vertices_casts_float_scip_cc_to_int():
    """SCIP CC emitted as a float (3.0) must be stored as int(3).

    _int_prop_clause embeds the value unquoted in Cypher:
      SET v.cyclomatic_complexity = 3.0   -- AGE parse error
    The fix: int(sym["cyclomatic_complexity"]) with a try/except fallback.
    """
    verts = extract_vertices(_INDEX_WITH_FLOAT_CC, repo=_REPO)
    fn_verts = [v for v in verts if v.get("label") == VERTEX_FUNCTION]
    assert len(fn_verts) == 1
    cc = fn_verts[0].get(_CC_KEY)
    assert cc is not None, "CC should be set when SCIP provides cyclomatic_complexity."
    assert isinstance(cc, int), (
        f"CC must be stored as int, not {type(cc).__name__}({cc!r}) — "
        "a float produces invalid Cypher (code-review Finding #5)."
    )


def test_extract_vertices_skips_nonnumeric_scip_cc():
    """SCIP CC as a non-numeric string must not be stored raw.

    Storing it would embed a bare identifier in Cypher:
      SET v.cyclomatic_complexity = high   -- AGE parse error
    The fix: skip (cc = None) or raise, never store a non-int value.
    """
    verts = extract_vertices(_INDEX_WITH_STR_CC, repo=_REPO)
    fn_verts = [v for v in verts if v.get("label") == VERTEX_FUNCTION]
    assert len(fn_verts) == 1
    cc = fn_verts[0].get(_CC_KEY)
    if cc is not None:
        assert isinstance(cc, int), (
            f"CC stored as {type(cc).__name__}({cc!r}) would produce invalid Cypher — "
            "must be int or absent when SCIP emits a non-numeric value "
            "(code-review Finding #5)."
        )
