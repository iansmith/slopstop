"""Phase 0 red tests for BILL-55 — SCIP ingestion pipeline (Layer 2).

Tests describe the expected behavior of POST /code-graph/ingest via TestClient.
All tests FAIL on current code — the endpoint does not exist yet.

Layer 2 only: endpoint + FakeDB. Pure-function tests are in
test_code_graph_ingest.py (Layer 1, no FastAPI imports).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_service.db import get_db_conn
from rag_service.main import app

_TEST_REPO = "iansmith/scip-spike"

# Minimal SCIP JSON fixture — mirrors test_code_graph_ingest.py (Layer 1 test data).
# Duplicated here rather than imported to avoid chaining through the Layer 1 module,
# which itself imports rag_service.code_graph.ingest (the module under development).
_SCIP_INDEX: dict = {
    "metadata": {"tool_info": {"name": "scip-go", "version": "0.2.7"}},
    "documents": [
        {
            "language": "Go",
            "relative_path": "main.go",
            "symbols": [
                {
                    "symbol": "scip-go gomod scipspike . scipspike/describe().",
                    "kind": "Function",
                    "relationships": [],
                }
            ],
            "occurrences": [
                {
                    "symbol": "scip-go gomod scipspike . scipspike/describe().",
                    "range": [10, 5, 13],
                    "symbol_roles": 1,
                    "enclosing_range": [10, 0, 13, 1],
                },
                {
                    # fmt.Println is callable by suffix (ends in ().) — no kind needed
                    "symbol": "scip-go gomod `fmt` v0 fmt/Println().",
                    "range": [11, 4, 8],
                    "symbol_roles": 8,
                },
            ],
        }
    ],
    "external_symbols": [],
}

_INGEST_PAYLOAD: dict = {"repo": _TEST_REPO, "index": _SCIP_INDEX}


# ── Fake ──────────────────────────────────────────────────────────────────────


class FakeCodeGraphDB:
    """Stand-in for DB in the ingest endpoint.  Records Cypher statements."""

    def __init__(self) -> None:
        self.ping_returns: bool = True
        self.tables: set[str] = {"ticket_chunks"}
        self.cypher_calls: list[str] = []

    def ping(self) -> bool:
        return self.ping_returns

    def has_table(self, name: str) -> bool:
        return name in self.tables

    def knn_search(self, vec, k, filters=None) -> list:
        return []

    def run_cypher(self, cypher: str) -> list:
        self.cypher_calls.append(cypher)
        return []


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_cg_db() -> FakeCodeGraphDB:
    return FakeCodeGraphDB()


@pytest.fixture
def cg_client(fake_cg_db: FakeCodeGraphDB):
    """TestClient wired to FakeCodeGraphDB only (no embedder/reranker needed)."""
    app.dependency_overrides[get_db_conn] = lambda: fake_cg_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ── Layer 2: POST /code-graph/ingest ─────────────────────────────────────────


class TestIngestEndpoint:
    def test_post_ingest_returns_200(self, cg_client: TestClient, fake_cg_db: FakeCodeGraphDB):
        resp = cg_client.post("/code-graph/ingest", json=_INGEST_PAYLOAD)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_post_ingest_returns_counts(self, cg_client: TestClient, fake_cg_db: FakeCodeGraphDB):
        """Response includes positive vertices_merged and edges_merged counts."""
        resp = cg_client.post("/code-graph/ingest", json=_INGEST_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert "vertices_merged" in body, f"Missing vertices_merged in {body}"
        assert "edges_merged" in body, f"Missing edges_merged in {body}"
        assert body["vertices_merged"] > 0
        assert body["edges_merged"] > 0

    def test_post_ingest_issues_cypher(self, cg_client: TestClient, fake_cg_db: FakeCodeGraphDB):
        """The endpoint must execute Cypher statements against the DB."""
        cg_client.post("/code-graph/ingest", json=_INGEST_PAYLOAD)
        assert fake_cg_db.cypher_calls, "Endpoint issued no Cypher statements to the DB"
