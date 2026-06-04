"""Phase 0 red tests for BILL-58 — query surface (Layer 2).

Tests describe the expected post-implementation behavior of:
  - POST /code-graph/callers       — who calls this moniker?
  - POST /code-graph/implementors  — who implements this interface?
  - POST /code-graph/blast-radius  — transitive callers up to depth N
  - POST /code-graph/ticket-code   — functions touched by a given ticket ID

All tests FAIL on current code (endpoints don't exist → 404).

Layer 2 only: TestClient + dependency_overrides.
Pure-function tests (Cypher builders + row parsers) go in
test_code_graph_query.py (Layer 1) once query.py exists.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_service.db import get_age_conn
from rag_service.main import app

# ── Constants ─────────────────────────────────────────────────────────────────

_REPO = "iansmith/slopstop"
_CALLER_MONIKER = "scip-go gomod slopstop . slopstop/caller()."
_TARGET_MONIKER = "scip-go gomod slopstop . slopstop/linesOverlap()."
_IMPLEMENTOR_MONIKER = "scip-go gomod slopstop . slopstop/ConcreteType."
_INTERFACE_MONIKER = "scip-go gomod slopstop . slopstop/Overlapper#."
_TICKET_ID = "BILL-56"

# Fake agtype-encoded row: (moniker, file_path, range, lang, repo, external)
# range is a 3-element JSON array [startLine, startChar, endChar]; startLine is
# 0-indexed.  The expected `line` in the response is startLine + 1.
_CALLER_ROW = (
    f'"{_CALLER_MONIKER}"',
    '"rag-service/rag_service/code_graph/ingest.py"',
    "[9, 0, 20]",          # startLine=9 → line=10
    '"go"',
    f'"{_REPO}"',
    "false",
)

_IMPLEMENTOR_ROW = (
    f'"{_IMPLEMENTOR_MONIKER}"',
    '"rag-service/rag_service/code_graph/schema.py"',
    "[4, 0, 30]",          # startLine=4 → line=5
    '"go"',
    f'"{_REPO}"',
    "false",
)

_TOUCHED_ROW = (
    f'"{_TARGET_MONIKER}"',
    '"rag-service/rag_service/code_graph/commit_ingest.py"',
    "[41, 0, 50]",         # startLine=41 → line=42
    '"go"',
    f'"{_REPO}"',
    "false",
)


# ── Shared fake DB ────────────────────────────────────────────────────────────


class FakeQueryDB:
    """Fake AGE connection for /code-graph/callers|implementors|blast-radius|ticket-code.

    ``callers_by_moniker``, ``implementors_by_moniker``, and
    ``touched_by_ticket`` map lookup keys → list of raw agtype rows
    that the Cypher query would return.  Rows are 6-tuples of agtype strings:
      (f_moniker, f_file_path, f_range, f_lang, f_repo, f_external)

    Records all cypher calls so tests can inspect the generated queries.
    """

    def __init__(
        self,
        callers_by_moniker: dict[str, list] | None = None,
        implementors_by_moniker: dict[str, list] | None = None,
        touched_by_ticket: dict[str, list] | None = None,
    ) -> None:
        self.callers_by_moniker: dict[str, list] = callers_by_moniker or {}
        self.implementors_by_moniker: dict[str, list] = implementors_by_moniker or {}
        self.touched_by_ticket: dict[str, list] = touched_by_ticket or {}
        self.cypher_calls: list[str] = []

    def run_cypher(self, cypher: str) -> list:
        self.cypher_calls.append(cypher)
        for moniker, rows in self.callers_by_moniker.items():
            if moniker in cypher:
                return rows
        for moniker, rows in self.implementors_by_moniker.items():
            if moniker in cypher:
                return rows
        for ticket_id, rows in self.touched_by_ticket.items():
            if ticket_id in cypher:
                return rows
        return []

    def ping(self) -> bool:
        return True

    def has_table(self, name: str) -> bool:
        return True


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def query_client():
    """TestClient for query endpoints with empty graph (no hits)."""
    db = FakeQueryDB()
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def query_client_with_caller():
    """TestClient seeded with one CALLS result for _TARGET_MONIKER."""
    db = FakeQueryDB(callers_by_moniker={_TARGET_MONIKER: [_CALLER_ROW]})
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def query_client_with_implementor():
    """TestClient seeded with one IMPLEMENTS result for _INTERFACE_MONIKER."""
    db = FakeQueryDB(implementors_by_moniker={_INTERFACE_MONIKER: [_IMPLEMENTOR_ROW]})
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def query_client_with_ticket():
    """TestClient seeded with one TOUCHES result for _TICKET_ID."""
    db = FakeQueryDB(touched_by_ticket={_TICKET_ID: [_TOUCHED_ROW]})
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ── POST /code-graph/callers ──────────────────────────────────────────────────


class TestCallersEndpoint:
    def test_returns_200_and_results_list(self, query_client_with_caller: TestClient):
        resp = query_client_with_caller.post(
            "/code-graph/callers",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.status_code == 200
        assert "results" in resp.json()
        assert isinstance(resp.json()["results"], list)

    def test_result_has_required_fields(self, query_client_with_caller: TestClient):
        resp = query_client_with_caller.post(
            "/code-graph/callers",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        result = resp.json()["results"][0]
        assert "moniker" in result
        assert "file_path" in result
        assert "line" in result
        assert "location" in result
        assert "lang" in result
        assert "repo" in result
        assert "external" in result

    def test_location_is_1indexed_file_colon_line(
        self, query_client_with_caller: TestClient
    ):
        """line = range[0]+1 (SCIP is 0-indexed); location = file_path:line."""
        resp = query_client_with_caller.post(
            "/code-graph/callers",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        result = resp.json()["results"][0]
        assert result["line"] == 10          # _CALLER_ROW range[0]=9, +1=10
        assert result["location"].endswith(":10")

    def test_empty_results_for_unknown_moniker(self, query_client: TestClient):
        resp = query_client.post(
            "/code-graph/callers",
            json={"moniker": "scip-go gomod slopstop . slopstop/NoSuchFn().", "repo": _REPO},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_limit_default_is_50(self, query_client: TestClient):
        """Endpoint accepts request with no explicit limit (defaults to 50)."""
        resp = query_client.post(
            "/code-graph/callers",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.status_code == 200

    def test_explicit_limit_param_accepted(self, query_client: TestClient):
        resp = query_client.post(
            "/code-graph/callers",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO, "limit": 10},
        )
        assert resp.status_code == 200


# ── POST /code-graph/implementors ────────────────────────────────────────────


class TestImplementorsEndpoint:
    def test_returns_200_and_results_list(
        self, query_client_with_implementor: TestClient
    ):
        resp = query_client_with_implementor.post(
            "/code-graph/implementors",
            json={"moniker": _INTERFACE_MONIKER, "repo": _REPO},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["results"], list)

    def test_result_has_required_fields(
        self, query_client_with_implementor: TestClient
    ):
        resp = query_client_with_implementor.post(
            "/code-graph/implementors",
            json={"moniker": _INTERFACE_MONIKER, "repo": _REPO},
        )
        result = resp.json()["results"][0]
        for field in ("moniker", "file_path", "line", "location", "lang", "repo", "external"):
            assert field in result

    def test_location_is_1indexed(self, query_client_with_implementor: TestClient):
        resp = query_client_with_implementor.post(
            "/code-graph/implementors",
            json={"moniker": _INTERFACE_MONIKER, "repo": _REPO},
        )
        result = resp.json()["results"][0]
        assert result["line"] == 5           # _IMPLEMENTOR_ROW range[0]=4, +1=5

    def test_empty_results_for_non_interface(self, query_client: TestClient):
        resp = query_client.post(
            "/code-graph/implementors",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []


# ── POST /code-graph/blast-radius ────────────────────────────────────────────


class TestBlastRadiusEndpoint:
    def test_returns_200_and_results_list(
        self, query_client_with_caller: TestClient
    ):
        resp = query_client_with_caller.post(
            "/code-graph/blast-radius",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["results"], list)

    def test_result_has_required_fields(self, query_client_with_caller: TestClient):
        resp = query_client_with_caller.post(
            "/code-graph/blast-radius",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        result = resp.json()["results"][0]
        for field in ("moniker", "file_path", "line", "location", "lang", "repo", "external"):
            assert field in result

    def test_depth_param_accepted_with_default(self, query_client: TestClient):
        """Default depth=3 is accepted without explicit param."""
        resp = query_client.post(
            "/code-graph/blast-radius",
            json={"moniker": _TARGET_MONIKER, "repo": _REPO},
        )
        assert resp.status_code == 200

    def test_explicit_depth_param_reflected_in_cypher(
        self, query_client_with_caller: TestClient
    ):
        """The generated Cypher must encode the depth cap (e.g. '*1..2' for depth=2)."""
        db = FakeQueryDB(callers_by_moniker={_TARGET_MONIKER: [_CALLER_ROW]})
        app.dependency_overrides[get_age_conn] = lambda: db
        try:
            client = TestClient(app)
            client.post(
                "/code-graph/blast-radius",
                json={"moniker": _TARGET_MONIKER, "repo": _REPO, "depth": 2},
            )
            assert any("*1..2" in q for q in db.cypher_calls)
        finally:
            app.dependency_overrides.clear()

    def test_empty_for_unknown_moniker(self, query_client: TestClient):
        resp = query_client.post(
            "/code-graph/blast-radius",
            json={"moniker": "scip-go . unknown().", "repo": _REPO},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []


# ── POST /code-graph/ticket-code ─────────────────────────────────────────────


class TestTicketCodeEndpoint:
    def test_returns_200_and_results_list(
        self, query_client_with_ticket: TestClient
    ):
        resp = query_client_with_ticket.post(
            "/code-graph/ticket-code",
            json={"ticket_id": _TICKET_ID, "repo": _REPO},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["results"], list)

    def test_result_has_required_fields(
        self, query_client_with_ticket: TestClient
    ):
        resp = query_client_with_ticket.post(
            "/code-graph/ticket-code",
            json={"ticket_id": _TICKET_ID, "repo": _REPO},
        )
        result = resp.json()["results"][0]
        for field in ("moniker", "file_path", "line", "location", "lang", "repo", "external"):
            assert field in result

    def test_location_is_1indexed(self, query_client_with_ticket: TestClient):
        resp = query_client_with_ticket.post(
            "/code-graph/ticket-code",
            json={"ticket_id": _TICKET_ID, "repo": _REPO},
        )
        result = resp.json()["results"][0]
        assert result["line"] == 42          # _TOUCHED_ROW range[0]=41, +1=42

    def test_empty_for_unknown_ticket(self, query_client: TestClient):
        resp = query_client.post(
            "/code-graph/ticket-code",
            json={"ticket_id": "BILL-9999", "repo": _REPO},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_ticket_id_in_generated_cypher(
        self, query_client_with_ticket: TestClient
    ):
        """The generated Cypher must reference the ticket_id string."""
        db = FakeQueryDB(touched_by_ticket={_TICKET_ID: [_TOUCHED_ROW]})
        app.dependency_overrides[get_age_conn] = lambda: db
        try:
            client = TestClient(app)
            client.post(
                "/code-graph/ticket-code",
                json={"ticket_id": _TICKET_ID, "repo": _REPO},
            )
            assert any(_TICKET_ID in q for q in db.cypher_calls)
        finally:
            app.dependency_overrides.clear()


class TestInputValidation:
    """Boundary tests for Pydantic Field constraints on all graph endpoints.

    Validation is enforced by FastAPI before the endpoint body runs, so no
    DB fixture is required — a bare TestClient is sufficient.
    """

    def test_callers_limit_above_max_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/callers",
            json={"moniker": _TARGET_MONIKER, "limit": 201},
        )
        assert resp.status_code == 422

    def test_implementors_limit_above_max_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/implementors",
            json={"moniker": _INTERFACE_MONIKER, "limit": 201},
        )
        assert resp.status_code == 422

    def test_blast_radius_limit_above_max_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/blast-radius",
            json={"moniker": _TARGET_MONIKER, "limit": 201},
        )
        assert resp.status_code == 422

    def test_blast_radius_depth_above_max_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/blast-radius",
            json={"moniker": _TARGET_MONIKER, "depth": 6},
        )
        assert resp.status_code == 422

    def test_ticket_code_limit_above_max_returns_422(self):
        client = TestClient(app)
        resp = client.post(
            "/code-graph/ticket-code",
            json={"ticket_id": _TICKET_ID, "limit": 201},
        )
        assert resp.status_code == 422
