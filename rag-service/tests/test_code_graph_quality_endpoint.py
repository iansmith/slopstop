"""Layer 2 tests for BILL-104 — dead-candidates and callers-with-cc endpoints.

Tests cover:
  - POST /code-graph/dead-candidates
  - POST /code-graph/callers-with-cc

All tests use TestClient + dependency_overrides (no real DB). The fake DB
routes cypher calls to canned row lists based on substring matching.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_service.db import get_age_conn
from rag_service.main import app

# ── Constants ─────────────────────────────────────────────────────────────────

_REPO = "iansmith/slopstop"
_TARGET_MONIKER = "scip-python ... linesOverlap()."
_CALLER_MONIKER = "scip-python ... processChunks()."

# dead-candidates row: (f_moniker, f_file_path, f_cc, f_impl_count)
_DEAD_ROW_LIKELY = (
    f'"{_TARGET_MONIKER}"',
    '"rag-service/rag_service/code_graph/query.py"',
    "12",
    "0",
)

# dead-candidates row where function has IMPLEMENTS edge → possibly_dead
_DEAD_ROW_POSSIBLY = (
    '"scip-python ... processIface()."',
    '"rag-service/rag_service/iface.py"',
    "5",
    "1",
)

# callers-with-cc row: (f_moniker, f_file_path, f_cc, f_test)
_CALLER_CC_ROW = (
    f'"{_CALLER_MONIKER}"',
    '"rag-service/rag_service/search.py"',
    "8",
    "false",
)

# target CC row: (f_cc,)
_TARGET_CC_ROW = ("14",)


# ── Fake DB ───────────────────────────────────────────────────────────────────


class FakeQualityDB:
    """Fake AGE connection for quality endpoints.

    Matches cypher calls by substring and returns canned row lists. Records
    all cypher calls for inspection.
    """

    def __init__(
        self,
        dead_rows: list | None = None,
        caller_rows: list | None = None,
        target_cc_rows: list | None = None,
    ) -> None:
        self.dead_rows: list = dead_rows or []
        self.caller_rows: list = caller_rows or []
        self.target_cc_rows: list = target_cc_rows or []
        self.cypher_calls: list[str] = []

    def run_cypher(self, cypher: str) -> list:
        self.cypher_calls.append(cypher)
        # dead-candidates query is identified by impl_count column
        if "f_impl_count" in cypher:
            return self.dead_rows
        # callers-with-cc query has both f_cc and f_test columns
        if "f_test" in cypher:
            return self.caller_rows
        # target-cc query has only f_cc column
        if "f_cc" in cypher:
            return self.target_cc_rows
        return []

    def execute_sql(self, sql: str) -> None:
        pass

    def ping(self) -> bool:
        return True

    def has_table(self, name: str) -> bool:
        return True


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def quality_client():
    """TestClient with empty graph."""
    db = FakeQualityDB()
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def dead_client():
    """TestClient seeded with dead-candidate rows."""
    db = FakeQualityDB(dead_rows=[_DEAD_ROW_LIKELY, _DEAD_ROW_POSSIBLY])
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def callers_cc_client():
    """TestClient seeded with callers-with-cc rows and a target CC."""
    db = FakeQualityDB(
        caller_rows=[_CALLER_CC_ROW],
        target_cc_rows=[_TARGET_CC_ROW],
    )
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ── POST /code-graph/dead-candidates ─────────────────────────────────────────


class TestDeadCandidatesEndpoint:
    def test_returns_200_and_candidates_list(self, dead_client: TestClient):
        resp = dead_client.post(
            "/code-graph/dead-candidates",
            json={"repo": _REPO},
        )
        assert resp.status_code == 200
        assert "candidates" in resp.json()
        assert isinstance(resp.json()["candidates"], list)

    def test_candidate_has_required_fields(self, dead_client: TestClient):
        resp = dead_client.post(
            "/code-graph/dead-candidates",
            json={"repo": _REPO},
        )
        c = resp.json()["candidates"][0]
        for field in ("moniker", "file_path", "cyclomatic_complexity", "has_implements", "confidence"):
            assert field in c

    def test_likely_dead_classification(self, dead_client: TestClient):
        resp = dead_client.post(
            "/code-graph/dead-candidates",
            json={"repo": _REPO},
        )
        first = resp.json()["candidates"][0]
        assert first["has_implements"] is False
        assert first["confidence"] == "likely_dead"

    def test_possibly_dead_classification(self, dead_client: TestClient):
        resp = dead_client.post(
            "/code-graph/dead-candidates",
            json={"repo": _REPO},
        )
        second = resp.json()["candidates"][1]
        assert second["has_implements"] is True
        assert second["confidence"] == "possibly_dead"

    def test_empty_graph_returns_empty_candidates(self, quality_client: TestClient):
        resp = quality_client.post(
            "/code-graph/dead-candidates",
            json={"repo": _REPO},
        )
        assert resp.status_code == 200
        assert resp.json()["candidates"] == []

    def test_repo_in_generated_cypher(self):
        db = FakeQualityDB(dead_rows=[_DEAD_ROW_LIKELY])
        app.dependency_overrides[get_age_conn] = lambda: db
        try:
            client = TestClient(app)
            client.post("/code-graph/dead-candidates", json={"repo": _REPO})
            assert any(_REPO in q for q in db.cypher_calls)
        finally:
            app.dependency_overrides.clear()

    def test_cc_threshold_in_generated_cypher(self):
        db = FakeQualityDB()
        app.dependency_overrides[get_age_conn] = lambda: db
        try:
            client = TestClient(app)
            client.post(
                "/code-graph/dead-candidates",
                json={"repo": _REPO, "cc_threshold": 5},
            )
            assert any(">= 5" in q for q in db.cypher_calls)
        finally:
            app.dependency_overrides.clear()

    def test_limit_above_max_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/dead-candidates",
            json={"repo": _REPO, "limit": 201},
        )
        assert resp.status_code == 422

    def test_negative_cc_threshold_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/dead-candidates",
            json={"repo": _REPO, "cc_threshold": -1},
        )
        assert resp.status_code == 422

    def test_default_params_accepted(self, quality_client: TestClient):
        resp = quality_client.post("/code-graph/dead-candidates", json={})
        assert resp.status_code == 200


# ── POST /code-graph/callers-with-cc ─────────────────────────────────────────


class TestCallersWithCCEndpoint:
    def test_returns_200_with_target_cc_and_callers(self, callers_cc_client: TestClient):
        resp = callers_cc_client.post(
            "/code-graph/callers-with-cc",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "target_cc" in body
        assert "callers" in body
        assert isinstance(body["callers"], list)

    def test_target_cc_value(self, callers_cc_client: TestClient):
        resp = callers_cc_client.post(
            "/code-graph/callers-with-cc",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.json()["target_cc"] == 14

    def test_caller_has_required_fields(self, callers_cc_client: TestClient):
        resp = callers_cc_client.post(
            "/code-graph/callers-with-cc",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        caller = resp.json()["callers"][0]
        for field in ("moniker", "file_path", "cyclomatic_complexity", "test"):
            assert field in caller

    def test_caller_cc_value(self, callers_cc_client: TestClient):
        resp = callers_cc_client.post(
            "/code-graph/callers-with-cc",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.json()["callers"][0]["cyclomatic_complexity"] == 8

    def test_caller_test_flag_false(self, callers_cc_client: TestClient):
        resp = callers_cc_client.post(
            "/code-graph/callers-with-cc",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.json()["callers"][0]["test"] is False

    def test_unknown_moniker_returns_null_target_cc_and_empty_callers(
        self, quality_client: TestClient
    ):
        resp = quality_client.post(
            "/code-graph/callers-with-cc",
            json={"moniker": "scip-python ... NoSuchFn().", "repo": _REPO},
        )
        assert resp.status_code == 200
        assert resp.json()["target_cc"] is None
        assert resp.json()["callers"] == []

    def test_moniker_required_returns_422_when_missing(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/callers-with-cc",
            json={"repo": _REPO},
        )
        assert resp.status_code == 422

    def test_limit_above_max_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/callers-with-cc",
            json={"moniker": _TARGET_MONIKER, "limit": 201},
        )
        assert resp.status_code == 422

    def test_moniker_in_generated_cypher(self):
        db = FakeQualityDB(caller_rows=[_CALLER_CC_ROW], target_cc_rows=[_TARGET_CC_ROW])
        app.dependency_overrides[get_age_conn] = lambda: db
        try:
            client = TestClient(app)
            client.post(
                "/code-graph/callers-with-cc",
                json={"moniker": _TARGET_MONIKER, "repo": _REPO},
            )
            assert any(_TARGET_MONIKER in q for q in db.cypher_calls)
        finally:
            app.dependency_overrides.clear()

    def test_two_cypher_calls_made(self):
        """Endpoint must make two DB calls: one for target CC, one for callers."""
        db = FakeQualityDB(caller_rows=[_CALLER_CC_ROW], target_cc_rows=[_TARGET_CC_ROW])
        app.dependency_overrides[get_age_conn] = lambda: db
        try:
            client = TestClient(app)
            client.post(
                "/code-graph/callers-with-cc",
                json={"moniker": _TARGET_MONIKER, "repo": _REPO},
            )
            assert len(db.cypher_calls) == 2
        finally:
            app.dependency_overrides.clear()

    def test_repo_forwarded_to_target_cc_cypher(self):
        """The repo filter must appear in the target-CC cypher call, not just the callers call."""
        db = FakeQualityDB(caller_rows=[_CALLER_CC_ROW], target_cc_rows=[_TARGET_CC_ROW])
        app.dependency_overrides[get_age_conn] = lambda: db
        try:
            client = TestClient(app)
            client.post(
                "/code-graph/callers-with-cc",
                json={"moniker": _TARGET_MONIKER, "repo": _REPO},
            )
            # The first DB call is build_target_cc_cypher; it must include the repo.
            target_cc_call = db.cypher_calls[0]
            assert _REPO in target_cc_call
        finally:
            app.dependency_overrides.clear()
