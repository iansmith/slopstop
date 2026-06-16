"""Layer 1 tests for BILL-104 — quality.py pure functions.

Tests cover:
  - build_dead_candidates_cypher     — correct SQL shape + param encoding
  - build_callers_with_cc_cypher     — correct SQL shape + param encoding
  - build_target_cc_cypher           — correct SQL shape
  - parse_dead_candidates_rows       — agtype parsing + confidence classification
  - parse_callers_with_cc_rows       — agtype parsing + null CC / test handling
  - parse_target_cc_row              — single-value parse + missing / null
  - _name_from_moniker               — name extraction helper
  - _classify_dead                   — classification logic
"""

from __future__ import annotations

import pytest

from rag_service.code_graph.quality import (
    _classify_dead,
    _name_from_moniker,
    build_callers_with_cc_cypher,
    build_dead_candidates_cypher,
    build_target_cc_cypher,
    parse_callers_with_cc_rows,
    parse_dead_candidates_rows,
    parse_target_cc_row,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_REPO = "iansmith/slopstop"
_TARGET = "scip-python ... linesOverlap()."
_CALLER = "scip-python ... processChunks()."


# ── build_dead_candidates_cypher ──────────────────────────────────────────────


class TestBuildDeadCandidatesCypher:
    def test_returns_string(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert isinstance(sql, str)

    def test_references_function_vertex(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert "Function" in sql

    def test_repo_filter_present_when_given(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert _REPO in sql

    def test_no_repo_filter_when_empty(self):
        sql = build_dead_candidates_cypher(repo="")
        assert "iansmith" not in sql

    def test_cc_threshold_in_cypher(self):
        sql = build_dead_candidates_cypher(repo=_REPO, cc_threshold=5)
        assert ">= 5" in sql

    def test_default_cc_threshold_is_zero(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert ">= 0" in sql

    def test_limit_encoded(self):
        sql = build_dead_candidates_cypher(repo=_REPO, limit=25)
        assert "LIMIT 25" in sql

    def test_order_by_cc_descending(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert "DESC" in sql

    def test_columns_include_impl_count(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert "f_impl_count agtype" in sql

    def test_no_callers_pattern_present(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert "CALLS" in sql
        assert "caller_count = 0" in sql

    def test_implements_optional_match_present(self):
        sql = build_dead_candidates_cypher(repo=_REPO)
        assert "IMPLEMENTS" in sql


# ── build_callers_with_cc_cypher ──────────────────────────────────────────────


class TestBuildCallersWithCCCypher:
    def test_returns_string(self):
        sql = build_callers_with_cc_cypher(moniker=_TARGET)
        assert isinstance(sql, str)

    def test_moniker_in_cypher(self):
        sql = build_callers_with_cc_cypher(moniker=_TARGET)
        assert _TARGET in sql

    def test_repo_filter_when_given(self):
        sql = build_callers_with_cc_cypher(moniker=_TARGET, repo=_REPO)
        assert _REPO in sql

    def test_no_repo_filter_when_empty(self):
        sql = build_callers_with_cc_cypher(moniker=_TARGET, repo="")
        assert "WHERE caller" not in sql

    def test_limit_encoded(self):
        sql = build_callers_with_cc_cypher(moniker=_TARGET, limit=20)
        assert "LIMIT 20" in sql

    def test_columns_include_cc_and_test(self):
        sql = build_callers_with_cc_cypher(moniker=_TARGET)
        assert "f_cc agtype" in sql
        assert "f_test agtype" in sql

    def test_calls_edge_present(self):
        sql = build_callers_with_cc_cypher(moniker=_TARGET)
        assert "CALLS" in sql


# ── build_target_cc_cypher ────────────────────────────────────────────────────


class TestBuildTargetCCCypher:
    def test_returns_string(self):
        sql = build_target_cc_cypher(moniker=_TARGET)
        assert isinstance(sql, str)

    def test_moniker_in_cypher(self):
        sql = build_target_cc_cypher(moniker=_TARGET)
        assert _TARGET in sql

    def test_columns_include_f_cc(self):
        sql = build_target_cc_cypher(moniker=_TARGET)
        assert "f_cc agtype" in sql


# ── parse_dead_candidates_rows ────────────────────────────────────────────────


class TestParseDeadCandidatesRows:
    def _row(self, moniker, file_path, cc, impl_count):
        return (
            f'"{moniker}"',
            f'"{file_path}"',
            str(cc) if cc is not None else "null",
            str(impl_count),
        )

    def test_parses_basic_row(self):
        rows = [self._row("scip-python ... foo().", "src/main.py", 7, 0)]
        result = parse_dead_candidates_rows(rows)
        assert len(result) == 1
        assert result[0]["moniker"] == "scip-python ... foo()."
        assert result[0]["file_path"] == "src/main.py"
        assert result[0]["cyclomatic_complexity"] == 7

    def test_has_implements_false_when_impl_count_zero(self):
        rows = [self._row(_TARGET, "f.py", 5, 0)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["has_implements"] is False

    def test_has_implements_true_when_impl_count_nonzero(self):
        rows = [self._row(_TARGET, "f.py", 5, 2)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["has_implements"] is True

    def test_confidence_likely_dead(self):
        rows = [self._row("scip-python ... normalFunc().", "f.py", 5, 0)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["confidence"] == "likely_dead"

    def test_confidence_possibly_dead_from_implements(self):
        rows = [self._row("scip-python ... normalFunc().", "f.py", 5, 1)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["confidence"] == "possibly_dead"

    def test_confidence_possibly_dead_from_main_name(self):
        rows = [self._row("scip-python ... main().", "f.py", 3, 0)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["confidence"] == "possibly_dead"

    def test_confidence_possibly_dead_from_init_name(self):
        rows = [self._row("scip-python ... __init__().", "f.py", 3, 0)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["confidence"] == "possibly_dead"

    def test_confidence_possibly_dead_from_handler_name(self):
        rows = [self._row("scip-python ... request_handler().", "f.py", 4, 0)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["confidence"] == "possibly_dead"

    def test_confidence_possibly_dead_from_cli_name(self):
        rows = [self._row("scip-python ... cli_run().", "f.py", 4, 0)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["confidence"] == "possibly_dead"

    def test_null_cc_yields_none(self):
        rows = [self._row(_TARGET, "f.py", None, 0)]
        result = parse_dead_candidates_rows(rows)
        assert result[0]["cyclomatic_complexity"] is None

    def test_agtype_suffix_stripped(self):
        rows = [(
            '"scip-python ... foo()."::agtype',
            '"src/foo.py"::agtype',
            "5::agtype",
            "0::agtype",
        )]
        result = parse_dead_candidates_rows(rows)
        assert len(result) == 1
        assert result[0]["cyclomatic_complexity"] == 5

    def test_malformed_row_skipped(self):
        good = self._row(_TARGET, "f.py", 3, 0)
        bad = ("not-valid-json", "x", "y", "z")
        result = parse_dead_candidates_rows([bad, good])
        assert len(result) == 1

    def test_empty_rows_returns_empty_list(self):
        assert parse_dead_candidates_rows([]) == []


# ── parse_callers_with_cc_rows ────────────────────────────────────────────────


class TestParseCallersWithCCRows:
    def _row(self, moniker, file_path, cc, test):
        return (
            f'"{moniker}"',
            f'"{file_path}"',
            str(cc) if cc is not None else "null",
            "true" if test else "false",
        )

    def test_parses_basic_row(self):
        rows = [self._row(_CALLER, "src/caller.py", 12, False)]
        result = parse_callers_with_cc_rows(rows)
        assert len(result) == 1
        assert result[0]["moniker"] == _CALLER
        assert result[0]["cyclomatic_complexity"] == 12
        assert result[0]["test"] is False

    def test_test_flag_true(self):
        rows = [self._row(_CALLER, "tests/test_foo.py", 3, True)]
        result = parse_callers_with_cc_rows(rows)
        assert result[0]["test"] is True

    def test_null_cc_yields_none(self):
        rows = [self._row(_CALLER, "src/caller.py", None, False)]
        result = parse_callers_with_cc_rows(rows)
        assert result[0]["cyclomatic_complexity"] is None

    def test_null_test_defaults_to_false(self):
        rows = [(
            f'"{_CALLER}"',
            '"src/caller.py"',
            "5",
            "null",
        )]
        result = parse_callers_with_cc_rows(rows)
        assert result[0]["test"] is False

    def test_agtype_suffix_stripped(self):
        rows = [(
            f'"{_CALLER}"::agtype',
            '"src/caller.py"::agtype',
            "8::agtype",
            "false::agtype",
        )]
        result = parse_callers_with_cc_rows(rows)
        assert result[0]["cyclomatic_complexity"] == 8

    def test_malformed_row_skipped(self):
        good = self._row(_CALLER, "src/c.py", 2, False)
        result = parse_callers_with_cc_rows([("bad",), good])
        assert len(result) == 1

    def test_empty_rows_returns_empty_list(self):
        assert parse_callers_with_cc_rows([]) == []


# ── parse_target_cc_row ───────────────────────────────────────────────────────


class TestParseTargetCCRow:
    def test_parses_integer(self):
        assert parse_target_cc_row([("8",)]) == 8

    def test_parses_agtype_integer(self):
        assert parse_target_cc_row([("12::agtype",)]) == 12

    def test_null_returns_none(self):
        assert parse_target_cc_row([("null",)]) is None

    def test_empty_rows_returns_none(self):
        assert parse_target_cc_row([]) is None

    def test_malformed_returns_none(self):
        assert parse_target_cc_row([("not-a-number",)]) is None


# ── _name_from_moniker ────────────────────────────────────────────────────────


class TestNameFromMoniker:
    def test_python_function(self):
        # "()" is part of the "()." suffix that gets stripped as a unit.
        assert _name_from_moniker("scip-python ... linesOverlap().") == "linesOverlap"

    def test_strips_paren_dot_suffix(self):
        result = _name_from_moniker("scip-python bar foo().")
        assert result == "foo"

    def test_strips_plain_dot_suffix(self):
        result = _name_from_moniker("scip-go bar Baz.")
        assert result == "Baz"

    def test_strips_hash_suffix(self):
        result = _name_from_moniker("scip-python bar MyClass#")
        assert result == "MyClass"

    def test_strips_slash_suffix(self):
        result = _name_from_moniker("scip-python bar mymod/")
        assert result == "mymod"

    def test_no_suffix(self):
        result = _name_from_moniker("just_a_name")
        assert result == "just_a_name"


# ── _classify_dead ────────────────────────────────────────────────────────────


class TestClassifyDead:
    def test_likely_dead_plain(self):
        assert _classify_dead("scip-python ... normalFunc().", has_implements=False) == "likely_dead"

    def test_possibly_dead_has_implements(self):
        assert _classify_dead("scip-python ... normalFunc().", has_implements=True) == "possibly_dead"

    def test_possibly_dead_main_name(self):
        assert _classify_dead("scip-python ... main().", has_implements=False) == "possibly_dead"

    def test_possibly_dead_init_name(self):
        assert _classify_dead("scip-python ... __init__().", has_implements=False) == "possibly_dead"

    def test_possibly_dead_handler_name(self):
        # "handler" must appear as a substring; "handle_request" does not contain "handler".
        assert _classify_dead("scip-python ... request_handler().", has_implements=False) == "possibly_dead"

    def test_possibly_dead_cli_name(self):
        assert _classify_dead("scip-python ... cli().", has_implements=False) == "possibly_dead"

    def test_case_insensitive_entry_point(self):
        assert _classify_dead("scip-python ... MainLoop().", has_implements=False) == "possibly_dead"
