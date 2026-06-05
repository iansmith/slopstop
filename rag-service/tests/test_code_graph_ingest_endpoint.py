"""Phase 0 red tests for BILL-55 — SCIP ingestion pipeline (Layer 2).

Tests describe the expected behavior of POST /code-graph/ingest via TestClient.
All tests FAIL on current code — the endpoint does not exist yet.

Layer 2 only: endpoint + FakeDB. Pure-function tests are in
test_code_graph_ingest.py (Layer 1, no FastAPI imports).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import numpy as np

from rag_service.db import get_age_conn, get_db_conn
from rag_service.embed import get_embedder
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


class FakeIngestEmbedder:
    """Minimal embedder for ingest endpoint tests. Returns zero vectors."""

    def encode_passage(self, text: str) -> np.ndarray:
        return np.zeros(1024, dtype="float32")

    def encode_query(self, text: str) -> np.ndarray:
        return np.zeros(1024, dtype="float32")


@pytest.fixture
def fake_cg_embedder() -> FakeIngestEmbedder:
    return FakeIngestEmbedder()


@pytest.fixture
def cg_client(fake_cg_db: FakeCodeGraphDB, fake_cg_embedder: FakeIngestEmbedder):
    """TestClient wired to FakeCodeGraphDB + minimal embedder + fake db_conn.

    The ingest endpoint now also Depends on get_embedder (for docstring
    embedding) and get_db_conn (for write_docstring_rows). The test fixture
    has no documentation fields, so write_docstring_rows is not called —
    the overrides just prevent FastAPI from trying to load real models or
    connect to postgres during tests.
    """
    app.dependency_overrides[get_age_conn] = lambda: fake_cg_db
    app.dependency_overrides[get_db_conn] = lambda: fake_cg_db
    app.dependency_overrides[get_embedder] = lambda: fake_cg_embedder
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

    def test_ingest_with_head_sha_upserts_repo_vertex(
        self, cg_client: TestClient, fake_cg_db: FakeCodeGraphDB
    ):
        """When head_sha is provided, the endpoint must issue a Cypher MERGE for
        the :Repo vertex with last_indexed_sha."""
        payload = {**_INGEST_PAYLOAD, "head_sha": "abc123def456"}
        cg_client.post("/code-graph/ingest", json=payload)
        repo_cypher = [c for c in fake_cg_db.cypher_calls if "Repo" in c and "last_indexed_sha" in c]
        assert repo_cypher, (
            "Expected a :Repo vertex MERGE with last_indexed_sha; "
            f"calls were: {fake_cg_db.cypher_calls}"
        )

    def test_ingest_without_head_sha_no_repo_vertex(
        self, cg_client: TestClient, fake_cg_db: FakeCodeGraphDB
    ):
        """When head_sha is absent, no :Repo vertex Cypher should be issued."""
        cg_client.post("/code-graph/ingest", json=_INGEST_PAYLOAD)
        repo_cypher = [c for c in fake_cg_db.cypher_calls if "Repo" in c and "last_indexed_sha" in c]
        assert not repo_cypher, f"Unexpected :Repo MERGE without head_sha: {repo_cypher}"

    def test_ingest_response_includes_last_indexed_sha(
        self, cg_client: TestClient, fake_cg_db: FakeCodeGraphDB
    ):
        """Response body echoes last_indexed_sha when provided."""
        sha = "deadbeef1234"
        payload = {**_INGEST_PAYLOAD, "head_sha": sha}
        resp = cg_client.post("/code-graph/ingest", json=payload)
        assert resp.status_code == 200
        assert resp.json().get("last_indexed_sha") == sha


# ── Layer 2: GET /code-graph/repo/{repo_id} ──────────────────────────────────


@pytest.fixture
def repo_status_client(fake_cg_db: FakeCodeGraphDB):
    """TestClient for the repo-status GET endpoint."""
    app.dependency_overrides[get_age_conn] = lambda: fake_cg_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestRepoStatusEndpoint:
    def test_unknown_repo_returns_null_sha(
        self, repo_status_client: TestClient, fake_cg_db: FakeCodeGraphDB
    ):
        """When no :Repo vertex exists, last_indexed_sha must be null."""
        # FakeCodeGraphDB.run_cypher always returns [] — simulates missing vertex.
        resp = repo_status_client.get("/code-graph/repo/owner/repo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["repo"] == "owner/repo"
        assert body["last_indexed_sha"] is None

    def test_known_repo_returns_stored_sha(
        self, repo_status_client: TestClient, fake_cg_db: FakeCodeGraphDB
    ):
        """When the DB returns a row, last_indexed_sha must match."""
        fake_cg_db.run_cypher = lambda _cypher: [('"abc123def"',)]  # type: ignore[method-assign]
        resp = repo_status_client.get("/code-graph/repo/iansmith/slopstop")
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_indexed_sha"] == "abc123def"

    def test_repo_id_with_slash_is_captured(
        self, repo_status_client: TestClient
    ):
        """Path converter must capture owner/repo as a single repo_id value."""
        resp = repo_status_client.get("/code-graph/repo/some/nested/path")
        assert resp.status_code == 200
        assert resp.json()["repo"] == "some/nested/path"

    def test_issues_cypher_with_repo(
        self, repo_status_client: TestClient, fake_cg_db: FakeCodeGraphDB
    ):
        repo_status_client.get("/code-graph/repo/iansmith/slopstop")
        sha_cypher = [c for c in fake_cg_db.cypher_calls if "iansmith/slopstop" in c]
        assert sha_cypher, "Endpoint did not issue a Cypher query for the repo"
