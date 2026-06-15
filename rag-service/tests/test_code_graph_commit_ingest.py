"""Layer 1 tests for BILL-56 — commit provenance (TOUCHES edges).

Tests describe the expected behavior of rag_service.code_graph.commit_ingest
pure functions.  Layer 1 only: no FastAPI, no DB, no I/O.

Also covers the enclosing_range capture added to rag_service.code_graph.ingest
(extract_vertices) and build_vertex_cypher as part of BILL-56.

See test_code_graph_commit_ingest_endpoint.py for Layer 2 endpoint tests.
"""

from __future__ import annotations

import json

import pytest

from rag_service.code_graph.commit_ingest import (
    build_commit_vertex_cypher,
    build_query_functions_cypher,
    build_touches_cypher,
    lines_overlap,
    parse_function_rows,
    resolve_touches_targets,
)
from rag_service.code_graph.ingest import build_vertex_cypher, extract_vertices
from rag_service.code_graph.schema import (
    EDGE_TOUCHES,
    PROP_ENCLOSING_RANGE,
    VERTEX_COMMIT,
    VERTEX_FUNCTION,
)
from rag_service.models import CommitFileChange, CommitIngestRequest

# ── Fixtures ──────────────────────────────────────────────────────────────────

_REPO = "iansmith/slopstop"
_SHA = "9eb70fe1234567890abcdef1234567890abcdef12"
_FUNCTION_MONIKER = "scip-go gomod slopstop . slopstop/setup_age_session()."


def _make_req(**kwargs) -> CommitIngestRequest:
    defaults = dict(
        repo=_REPO,
        sha=_SHA,
        subject="[BILL-55] Implement SCIP ingestion",
        body="",
        author="Ian Smith",
        authored_at="2026-06-03T19:53:21Z",
        ticket_ids=["BILL-55"],
        files=[
            CommitFileChange(
                path="rag-service/rag_service/db.py",
                change_type="modified",
                hunks=2,
                changed_lines=None,
            )
        ],
    )
    defaults.update(kwargs)
    return CommitIngestRequest(**defaults)


# SCIP index with a Function vertex that has an enclosing_range
_INDEX_WITH_ENC_RANGE: dict = {
    "metadata": {"tool_info": {"name": "scip-go", "version": "0.2.7"}},
    "documents": [
        {
            "language": "Go",
            "relative_path": "db.py",
            "symbols": [
                {"symbol": _FUNCTION_MONIKER, "kind": "Function", "relationships": []},
            ],
            "occurrences": [
                {
                    "symbol": _FUNCTION_MONIKER,
                    "range": [190, 0, 190, 20],
                    "symbol_roles": 1,  # Definition
                    "enclosing_range": [190, 0, 199, 4],
                },
            ],
        }
    ],
    "external_symbols": [],
}


# ── build_commit_vertex_cypher ────────────────────────────────────────────────


class TestBuildCommitVertexCypher:
    @pytest.fixture(scope="class")
    def cypher(self) -> str:
        return build_commit_vertex_cypher(_make_req())

    def test_uses_merge(self, cypher):
        assert "MERGE" in cypher

    def test_merge_key_is_sha_and_repo(self, cypher):
        assert _SHA in cypher
        assert _REPO in cypher
        assert VERTEX_COMMIT in cypher

    def test_sets_subject(self, cypher):
        assert "BILL-55" in cypher
        assert "subject" in cypher

    def test_sets_ticket_ids_as_list(self, cypher):
        assert "ticket_ids" in cypher
        assert "'BILL-55'" in cypher

    def test_multiple_ticket_ids(self):
        req = _make_req(ticket_ids=["BILL-55", "BILL-56"])
        c = build_commit_vertex_cypher(req)
        assert "'BILL-55'" in c
        assert "'BILL-56'" in c

    def test_no_ticket_ids(self):
        req = _make_req(ticket_ids=[])
        c = build_commit_vertex_cypher(req)
        assert "ticket_ids" in c

    def test_idempotent_same_input(self):
        req = _make_req()
        assert build_commit_vertex_cypher(req) == build_commit_vertex_cypher(req)

    def test_cypher_injection_rejected(self):
        with pytest.raises(ValueError):
            build_commit_vertex_cypher(_make_req(sha="$scip$"))


# ── build_query_functions_cypher ──────────────────────────────────────────────


class TestBuildQueryFunctionsCypher:
    @pytest.fixture(scope="class")
    def cypher(self) -> str:
        return build_query_functions_cypher(_REPO, "rag-service/rag_service/db.py")

    def test_matches_function_label(self, cypher):
        assert VERTEX_FUNCTION in cypher

    def test_filters_by_file_path(self, cypher):
        assert "db.py" in cypher

    def test_filters_by_repo(self, cypher):
        assert _REPO in cypher

    def test_returns_moniker_and_enclosing_range(self, cypher):
        assert PROP_ENCLOSING_RANGE in cypher

    def test_enclosing_range_not_null_guard(self, cypher):
        assert "IS NOT NULL" in cypher


# ── build_touches_cypher ──────────────────────────────────────────────────────


class TestBuildTouchesCypher:
    @pytest.fixture(scope="class")
    def cypher(self) -> str:
        return build_touches_cypher(
            _SHA, _REPO, "rag-service/rag_service/db.py", "modified", 2
        )

    def test_uses_merge(self, cypher):
        assert "MERGE" in cypher

    def test_edge_type_is_touches(self, cypher):
        assert EDGE_TOUCHES in cypher

    def test_sha_in_cypher(self, cypher):
        assert _SHA in cypher

    def test_target_moniker_in_cypher(self, cypher):
        assert "db.py" in cypher

    def test_sets_change_type(self, cypher):
        assert "change_type" in cypher
        assert "modified" in cypher

    def test_sets_hunks(self, cypher):
        assert "hunks" in cypher
        assert "2" in cypher

    def test_idempotent(self):
        args = (_SHA, _REPO, "some/file.py", "added", 1)
        assert build_touches_cypher(*args) == build_touches_cypher(*args)


# ── parse_function_rows ───────────────────────────────────────────────────────


class TestParseFunctionRows:
    def test_parses_agtype_list_row(self):
        rows = [('["scip-go gomod slopstop . db/func().", [10, 0, 20, 4]]',)]
        result = parse_function_rows(rows)
        assert len(result) == 1
        moniker, enc = result[0]
        assert moniker == "scip-go gomod slopstop . db/func()."
        assert enc == [10, 0, 20, 4]

    def test_strips_agtype_suffix(self):
        rows = [('["moniker", [0, 0, 5, 0]]::agtype',)]
        result = parse_function_rows(rows)
        assert len(result) == 1

    def test_strips_list_suffix(self):
        rows = [('["moniker", [0, 0, 5, 0]]::list',)]
        result = parse_function_rows(rows)
        assert len(result) == 1

    def test_multiple_rows(self):
        rows = [
            ('["func_a", [10, 0, 20, 0]]',),
            ('["func_b", [30, 0, 40, 0]]',),
        ]
        result = parse_function_rows(rows)
        assert len(result) == 2
        assert result[0][0] == "func_a"
        assert result[1][0] == "func_b"

    def test_empty_rows(self):
        assert parse_function_rows([]) == []

    def test_malformed_row_skipped(self):
        rows = [("not valid json",), ('["valid", [0, 0, 5, 0]]',)]
        result = parse_function_rows(rows)
        assert len(result) == 1

    def test_accepts_plain_element_not_tuple(self):
        rows = ['["func_c", [5, 0, 10, 0]]']
        result = parse_function_rows(rows)
        assert len(result) == 1
        assert result[0][0] == "func_c"


# ── lines_overlap ─────────────────────────────────────────────────────────────


class TestLinesOverlap:
    # enc_range [10, 0, 20, 4] → function body from line 10 to line 20
    _ENC = [10, 0, 20, 4]

    def test_disjoint_before(self):
        assert not lines_overlap([[0, 8]], self._ENC)

    def test_disjoint_after(self):
        assert not lines_overlap([[21, 30]], self._ENC)

    def test_overlap_straddling_start(self):
        assert lines_overlap([[5, 12]], self._ENC)

    def test_overlap_straddling_end(self):
        assert lines_overlap([[18, 25]], self._ENC)

    def test_fully_inside(self):
        assert lines_overlap([[12, 15]], self._ENC)

    def test_fully_containing(self):
        assert lines_overlap([[0, 30]], self._ENC)

    def test_touching_start_boundary(self):
        assert lines_overlap([[10, 10]], self._ENC)

    def test_touching_end_boundary(self):
        assert lines_overlap([[20, 20]], self._ENC)

    def test_adjacent_before_no_overlap(self):
        assert not lines_overlap([[5, 9]], self._ENC)

    def test_adjacent_after_no_overlap(self):
        assert not lines_overlap([[21, 25]], self._ENC)

    def test_multiple_ranges_one_matches(self):
        assert lines_overlap([[0, 5], [15, 18], [25, 30]], self._ENC)

    def test_multiple_ranges_none_match(self):
        assert not lines_overlap([[0, 5], [25, 30]], self._ENC)


# ── resolve_touches_targets ───────────────────────────────────────────────────


class TestResolveTargets:
    _FILE_PATH = "rag-service/rag_service/db.py"

    def _fc(self, changed_lines=None, change_type="modified") -> CommitFileChange:
        return CommitFileChange(
            path=self._FILE_PATH,
            change_type=change_type,
            hunks=1,
            changed_lines=changed_lines,
        )

    def test_no_changed_lines_returns_file(self):
        assert resolve_touches_targets(self._fc(), []) == [self._FILE_PATH]

    def test_no_function_rows_returns_file(self):
        assert resolve_touches_targets(self._fc([[10, 15]]), []) == [self._FILE_PATH]

    def test_matching_function_returned(self):
        func_rows = [(_FUNCTION_MONIKER, [5, 0, 20, 4])]
        targets = resolve_touches_targets(self._fc([[10, 15]]), func_rows)
        assert targets == [_FUNCTION_MONIKER]

    def test_non_overlapping_function_falls_back_to_file(self):
        func_rows = [(_FUNCTION_MONIKER, [100, 0, 110, 4])]
        targets = resolve_touches_targets(self._fc([[10, 15]]), func_rows)
        assert targets == [self._FILE_PATH]

    def test_multiple_functions_all_matching_returned(self):
        func_rows = [
            ("func_a", [5, 0, 20, 4]),
            ("func_b", [10, 0, 30, 4]),
        ]
        targets = resolve_touches_targets(self._fc([[12, 18]]), func_rows)
        assert "func_a" in targets
        assert "func_b" in targets

    def test_partial_match_returns_only_matching(self):
        func_rows = [
            ("func_a", [5, 0, 20, 4]),    # overlaps
            ("func_b", [100, 0, 110, 4]),  # no overlap
        ]
        targets = resolve_touches_targets(self._fc([[10, 15]]), func_rows)
        assert targets == ["func_a"]


# ── extract_vertices + enclosing_range ────────────────────────────────────────


class TestExtractVerticesEnclosingRange:
    @pytest.fixture(scope="class")
    def vertices_by_moniker(self):
        return {v["moniker"]: v for v in extract_vertices(_INDEX_WITH_ENC_RANGE, _REPO)}

    def test_function_vertex_has_enclosing_range(self, vertices_by_moniker):
        v = vertices_by_moniker.get(_FUNCTION_MONIKER)
        assert v is not None, f"Function vertex not found; keys: {list(vertices_by_moniker)}"
        assert PROP_ENCLOSING_RANGE in v, "enclosing_range not captured on Function vertex"
        assert v[PROP_ENCLOSING_RANGE] == [190, 0, 199, 4]

    def test_file_vertex_has_no_enclosing_range(self, vertices_by_moniker):
        file_v = vertices_by_moniker.get("db.py")
        assert file_v is not None
        assert PROP_ENCLOSING_RANGE not in file_v or file_v.get(PROP_ENCLOSING_RANGE) is None


# ── CommitIngestRequest.body ──────────────────────────────────────────────────


class TestCommitBodyField:
    def test_body_defaults_to_empty_string(self):
        req = _make_req()
        assert req.body == ""

    def test_body_roundtrips(self):
        req = _make_req(body="Fix root cause.\n\nLonger explanation here.")
        assert req.body == "Fix root cause.\n\nLonger explanation here."

    def test_single_liner_body_equals_subject(self):
        subject = "[BILL-55] Implement SCIP ingestion"
        # %B for a single-liner commit is just the subject followed by a newline.
        body = subject + "\n"
        req = _make_req(subject=subject, body=body)
        assert req.body.strip() == req.subject.strip()

    def test_multi_line_body_differs_from_subject(self):
        subject = "[BILL-55] Implement SCIP ingestion"
        body = subject + "\n\nAdds the AGE ingest path and TOUCHES edges."
        req = _make_req(subject=subject, body=body)
        assert req.body.strip() != req.subject.strip()


class TestBuildVertexCypherEnclosingRange:
    def test_enclosing_range_in_cypher_when_set(self):
        vertex = {
            "moniker": _FUNCTION_MONIKER,
            "label": VERTEX_FUNCTION,
            "repo": _REPO,
            "file_path": "db.py",
            "lang": "go",
            "test": False,
            "external": False,
            PROP_ENCLOSING_RANGE: [190, 0, 199, 4],
        }
        c = build_vertex_cypher(vertex)
        assert "enclosing_range" in c
        assert "190" in c
        assert "199" in c

    def test_no_enclosing_range_when_not_set(self):
        vertex = {
            "moniker": _FUNCTION_MONIKER,
            "label": VERTEX_FUNCTION,
            "repo": _REPO,
            "file_path": "db.py",
            "lang": "go",
            "test": False,
            "external": False,
        }
        c = build_vertex_cypher(vertex)
        assert "enclosing_range" not in c
