"""Phase 0 red tests for BILL-57 — comment/docstring linkage (Layer 1).

Tests describe the expected post-implementation behavior of:
  - _strip_html(html) and _short_name(moniker) utilities (rag_service.code_graph.ingest)
  - extract_docstring_rows(index, repo) pure function (rag_service.code_graph.ingest)
  - Chunk.moniker field (rag_service.models)

All Layer-1 tests FAIL on current code — the functions do not yet exist in
rag_service.code_graph.ingest. Chunk.moniker tests fail because the field is absent.

Layer 1 only: no FastAPI, no DB, no I/O. See test_code_graph_docstring_endpoint.py
for the Layer 2 endpoint tests.
"""

from __future__ import annotations

import pytest

from rag_service.code_graph.ingest import (
    _short_name,
    _strip_html,
    extract_docstring_rows,
)
from rag_service.models import Chunk

# ── Shared test data ──────────────────────────────────────────────────────────

_REPO = "iansmith/slopstop"
_GO_FUNCTION_MONIKER = "scip-go gomod slopstop . slopstop/linesOverlap()."
_GO_METHOD_MONIKER = "scip-go gomod slopstop . slopstop/Scheduler#runqGet()."
_PYTHON_FUNCTION_MONIKER = (
    "scip-python python-package slopstop 0.1.0 rag_service/ingest/extract_vertices()."
)
_TS_METHOD_MONIKER = "scip-typescript npm my-package 1.0.0 src/MyClass#doThing()."


def _make_index(*symbols: dict) -> dict:
    """Minimal SCIP index dict containing the given symbol dicts in one document."""
    return {
        "metadata": {"tool_info": {"name": "scip-go"}},
        "documents": [
            {
                "language": "Go",
                "relative_path": "main.go",
                "symbols": list(symbols),
                "occurrences": [],
            }
        ],
        "external_symbols": [],
    }


def _sym(moniker: str, docs: list[str] | None = None) -> dict:
    """Convenience: minimal symbol dict with optional documentation."""
    s: dict = {"symbol": moniker, "kind": "Function", "relationships": []}
    if docs is not None:
        s["documentation"] = docs
    return s


# ── _strip_html ───────────────────────────────────────────────────────────────


class TestStripHtml:
    def test_removes_p_tags(self):
        assert _strip_html("<p>Reports whether the spans overlap.</p>") == (
            "Reports whether the spans overlap."
        )

    def test_unescapes_html_entities(self):
        assert _strip_html("&amp; &lt;foo&gt;") == "& <foo>"

    def test_collapses_internal_whitespace(self):
        assert _strip_html("<p>  Foo  \n  Bar  </p>") == "Foo Bar"

    def test_empty_string_returns_empty(self):
        assert _strip_html("") == ""

    def test_whitespace_only_returns_empty(self):
        assert _strip_html("   \n  ") == ""

    def test_nested_tags_removed(self):
        result = _strip_html("<p>See <a href='#'>link</a> for details.</p>")
        assert "<" not in result
        assert "See" in result
        assert "link" in result
        assert "for details." in result

    def test_pre_tag_content_preserved(self):
        result = _strip_html("<pre>foo bar</pre>")
        assert "foo bar" in result
        assert "<pre>" not in result


# ── _short_name ───────────────────────────────────────────────────────────────


class TestShortName:
    def test_go_toplevel_function(self):
        m = "scip-go gomod scipspike . scipspike/describe()."
        assert _short_name(m) == "describe"

    def test_go_function_camel_case(self):
        assert _short_name(_GO_FUNCTION_MONIKER) == "linesOverlap"

    def test_go_method_on_type(self):
        assert _short_name(_GO_METHOD_MONIKER) == "runqGet"

    def test_go_struct_type(self):
        m = "scip-go gomod slopstop . slopstop/Scheduler#"
        assert _short_name(m) == "Scheduler"

    def test_python_function(self):
        assert _short_name(_PYTHON_FUNCTION_MONIKER) == "extract_vertices"

    def test_typescript_method(self):
        assert _short_name(_TS_METHOD_MONIKER) == "doThing"


# ── extract_docstring_rows ────────────────────────────────────────────────────


class TestExtractDocstringRows:
    def test_documented_symbol_produces_one_row(self):
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, ["<p>Reports overlap.</p>"]))
        rows = extract_docstring_rows(index, _REPO)
        assert len(rows) == 1

    def test_row_source_kind_provenance_seq(self):
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, ["Reports overlap."]))
        row = extract_docstring_rows(index, _REPO)[0]
        assert row.source == "scip"
        assert row.kind == "docstring"
        assert row.provenance == "scip"
        assert row.seq == 0

    def test_row_moniker_field(self):
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, ["Reports overlap."]))
        row = extract_docstring_rows(index, _REPO)[0]
        assert row.moniker == _GO_FUNCTION_MONIKER

    def test_row_repo_field(self):
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, ["Reports overlap."]))
        row = extract_docstring_rows(index, _REPO)[0]
        assert row.repo == _REPO

    def test_row_ticket_id_is_moniker(self):
        """ticket_id holds the moniker so the UNIQUE constraint works."""
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, ["Reports overlap."]))
        row = extract_docstring_rows(index, _REPO)[0]
        assert row.ticket_id == _GO_FUNCTION_MONIKER

    def test_text_format_shortname_colon_doc(self):
        index = _make_index(
            _sym(_GO_FUNCTION_MONIKER, ["Reports whether the spans overlap."])
        )
        row = extract_docstring_rows(index, _REPO)[0]
        assert row.text == "linesOverlap: Reports whether the spans overlap."

    def test_html_stripped_from_text(self):
        index = _make_index(
            _sym(_GO_FUNCTION_MONIKER, ["<p>Reports &lt;special&gt; cases.</p>"])
        )
        row = extract_docstring_rows(index, _REPO)[0]
        assert "<p>" not in row.text
        assert "&lt;" not in row.text
        assert "<special>" in row.text

    def test_empty_documentation_list_skipped(self):
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, []))
        assert extract_docstring_rows(index, _REPO) == []

    def test_missing_documentation_key_skipped(self):
        # No 'documentation' key — proto3 absent = empty repeated field
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, docs=None))
        assert extract_docstring_rows(index, _REPO) == []

    def test_whitespace_only_after_strip_skipped(self):
        index = _make_index(_sym(_GO_FUNCTION_MONIKER, ["<p>  </p>"]))
        assert extract_docstring_rows(index, _REPO) == []

    def test_multiple_doc_strings_joined_into_one_row(self):
        index = _make_index(
            _sym(_GO_FUNCTION_MONIKER, ["First paragraph.", "Second paragraph."])
        )
        rows = extract_docstring_rows(index, _REPO)
        assert len(rows) == 1
        assert "First paragraph." in rows[0].text
        assert "Second paragraph." in rows[0].text

    def test_multiple_documented_symbols_produce_multiple_rows(self):
        index = _make_index(
            _sym(_GO_FUNCTION_MONIKER, ["Does A."]),
            _sym(_GO_METHOD_MONIKER, ["Does B."]),
        )
        rows = extract_docstring_rows(index, _REPO)
        assert len(rows) == 2

    def test_undocumented_symbols_do_not_produce_rows(self):
        index = _make_index(
            _sym(_GO_FUNCTION_MONIKER, ["Has docs."]),
            _sym(_GO_METHOD_MONIKER, docs=None),  # no docs
        )
        rows = extract_docstring_rows(index, _REPO)
        assert len(rows) == 1

    def test_symbols_across_multiple_documents(self):
        """Symbols in different files within the same index are all processed."""
        index = {
            "metadata": {"tool_info": {"name": "scip-go"}},
            "documents": [
                {
                    "language": "Go",
                    "relative_path": "a.go",
                    "symbols": [_sym(_GO_FUNCTION_MONIKER, ["Docs A."])],
                    "occurrences": [],
                },
                {
                    "language": "Go",
                    "relative_path": "b.go",
                    "symbols": [_sym(_GO_METHOD_MONIKER, ["Docs B."])],
                    "occurrences": [],
                },
            ],
            "external_symbols": [],
        }
        rows = extract_docstring_rows(index, _REPO)
        assert len(rows) == 2


# ── Chunk model ───────────────────────────────────────────────────────────────


class TestChunkModelMoniker:
    def test_chunk_has_moniker_field_defaulting_to_none(self):
        """Chunk response model must expose moniker (nullable) for scip rows."""
        chunk = Chunk(
            id=1,
            text="linesOverlap: Reports overlap.",
            score=0.9,
            source="scip",
            provenance="scip",
            kind="docstring",
            ticket_id=_GO_FUNCTION_MONIKER,
            seq=0,
        )
        assert chunk.moniker is None  # AttributeError if field absent

    def test_chunk_moniker_can_be_set(self):
        chunk = Chunk(
            id=2,
            text="linesOverlap: Reports overlap.",
            score=0.9,
            source="scip",
            provenance="scip",
            kind="docstring",
            ticket_id=_GO_FUNCTION_MONIKER,
            seq=0,
            moniker=_GO_FUNCTION_MONIKER,
        )
        assert chunk.moniker == _GO_FUNCTION_MONIKER

    def test_chunk_moniker_none_for_ticket_rows(self):
        """Ticket rows should have moniker=None (field exists, just unpopulated)."""
        chunk = Chunk(
            id=3,
            text="Some ticket text.",
            score=0.8,
            source="github",
            provenance="upstream",
            kind="description",
            ticket_id="BILL-1",
            seq=0,
        )
        assert chunk.moniker is None
