"""Phase 0 red tests for BILL-57 — docstring ingest + context endpoints (Layer 2).

Tests describe the expected post-implementation behavior of:
  - POST /code-graph/ingest   — updated to return `docstring_rows` count and write
                                docstring rows to ticket_chunks.
  - POST /code-graph/context  — new endpoint: TOUCHES-derived ticket linkage for monikers.

All tests FAIL on current code:
  - /code-graph/ingest does not return docstring_rows yet.
  - /code-graph/context does not exist (returns 404/405).

Layer 2 only: TestClient + dependency_overrides. Pure-function tests are in
test_code_graph_docstring_ingest.py (Layer 1).
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from rag_service.db import get_age_conn, get_db_conn
from rag_service.embed import get_embedder
from rag_service.main import app

# ── Constants ─────────────────────────────────────────────────────────────────

_REPO = "iansmith/slopstop"
_SHA = "9eb70fe1234567890abcdef1234567890abcdef12"
_MONIKER = "scip-go gomod slopstop . slopstop/linesOverlap()."

# ── SCIP index fixtures ───────────────────────────────────────────────────────

_SCIP_WITH_DOCS: dict = {
    "metadata": {"tool_info": {"name": "scip-go"}},
    "documents": [
        {
            "language": "Go",
            "relative_path": "commit_ingest.go",
            "symbols": [
                {
                    "symbol": _MONIKER,
                    "kind": "Function",
                    "relationships": [],
                    "documentation": ["<p>Reports whether the two spans overlap.</p>"],
                }
            ],
            "occurrences": [
                {
                    "symbol": _MONIKER,
                    "range": [10, 5, 13],
                    "symbol_roles": 1,
                    "enclosing_range": [10, 0, 13, 1],
                }
            ],
        }
    ],
    "external_symbols": [],
}

_SCIP_NO_DOCS: dict = {
    "metadata": {"tool_info": {"name": "scip-go"}},
    "documents": [
        {
            "language": "Go",
            "relative_path": "commit_ingest.go",
            "symbols": [
                {
                    "symbol": _MONIKER,
                    "kind": "Function",
                    "relationships": [],
                    # no documentation field
                }
            ],
            "occurrences": [],
        }
    ],
    "external_symbols": [],
}

# ── Fakes ─────────────────────────────────────────────────────────────────────


class FakeDocstringIngestDB:
    """Dual-role fake: serves as both get_age_conn (Cypher) and get_db_conn
    (write_docstring_rows).  The updated /code-graph/ingest endpoint Depends on
    both; this one object handles both roles in tests.

    Records:
      cypher_calls            — all run_cypher() arguments (AGE path)
      docstring_write_calls   — (rows, repo) pairs from write_docstring_rows()
    """

    def __init__(self) -> None:
        self.cypher_calls: list[str] = []
        self.docstring_write_calls: list[tuple] = []

    # AGE interface (used by run_cypher in the endpoint)
    def run_cypher(self, cypher: str) -> list:
        self.cypher_calls.append(cypher)
        return []

    # Regular DB interface (used by write_docstring_rows in the endpoint)
    def write_docstring_rows(self, rows: list, repo: str) -> int:
        self.docstring_write_calls.append((rows, repo))
        return len(rows)

    # Shared stubs
    def ping(self) -> bool:
        return True

    def has_table(self, name: str) -> bool:
        return True

    def knn_search(self, vec, k, filters=None) -> list:
        return []


class FakeIngestEmbedder:
    """Minimal embedder: returns a deterministic zero vector. No model loaded."""

    def encode_passage(self, text: str) -> np.ndarray:
        return np.zeros(1024, dtype="float32")

    def encode_query(self, text: str) -> np.ndarray:
        return np.zeros(1024, dtype="float32")


class FakeContextDB:
    """Fake for get_age_conn in /code-graph/context.

    ``touches_by_moniker`` maps moniker string → list of raw agtype rows the
    Cypher query would return.  Default empty (no TOUCHES in the graph).

    Row format matches the expected TOUCHES traversal output:
    each row is a tuple of agtype-encoded strings:
      (f_moniker, c_sha, c_subject, c_authored_at, c_ticket_ids, f_repo)
    """

    def __init__(self, touches_by_moniker: dict[str, list] | None = None) -> None:
        self.touches_by_moniker: dict[str, list] = touches_by_moniker or {}
        self.cypher_calls: list[str] = []

    def run_cypher(self, cypher: str) -> list:
        self.cypher_calls.append(cypher)
        for moniker, rows in self.touches_by_moniker.items():
            if moniker in cypher:
                return rows
        return []

    def ping(self) -> bool:
        return True

    def has_table(self, name: str) -> bool:
        return True

    def knn_search(self, vec, k, filters=None) -> list:
        return []


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_ingest_db() -> FakeDocstringIngestDB:
    return FakeDocstringIngestDB()


@pytest.fixture
def fake_ingest_embedder() -> FakeIngestEmbedder:
    return FakeIngestEmbedder()


@pytest.fixture
def ingest_client(
    fake_ingest_db: FakeDocstringIngestDB,
    fake_ingest_embedder: FakeIngestEmbedder,
):
    """TestClient overriding all three deps for the updated /code-graph/ingest.

    The endpoint now Depends on get_age_conn (Cypher writes), get_db_conn
    (write_docstring_rows), and get_embedder (bge-m3 encode_passage).
    """
    app.dependency_overrides[get_age_conn] = lambda: fake_ingest_db
    app.dependency_overrides[get_db_conn] = lambda: fake_ingest_db
    app.dependency_overrides[get_embedder] = lambda: fake_ingest_embedder
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def context_client():
    """TestClient for /code-graph/context with no TOUCHES data seeded."""
    db = FakeContextDB()
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def context_client_with_touches():
    """TestClient for /code-graph/context with one TOUCHES result seeded."""
    # Row tuple: (f_moniker, c_sha, c_subject, c_authored_at, c_ticket_ids, f_repo)
    # Values are agtype-encoded strings as returned by run_cypher().
    fake_row = (
        f'"{_MONIKER}"',
        f'"{_SHA}"',
        '"[BILL-56] Implement TOUCHES edges"',
        '"2026-06-03T00:00:00Z"',
        '["BILL-56"]',
        f'"{_REPO}"',
    )
    db = FakeContextDB(touches_by_moniker={_MONIKER: [fake_row]})
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


_FORK_REPO = "fork/slopstop"
_FORK_SHA = "bbbaaa1234567890abcdef1234567890abcdef12"


@pytest.fixture
def context_client_two_repos():
    """TestClient seeded with two TOUCHES rows from different repos (fork scenario)."""
    row_origin = (
        f'"{_MONIKER}"',
        f'"{_SHA}"',
        '"[BILL-56] Implement TOUCHES edges"',
        '"2026-06-03T00:00:00Z"',
        '["BILL-56"]',
        f'"{_REPO}"',
    )
    row_fork = (
        f'"{_MONIKER}"',
        f'"{_FORK_SHA}"',
        '"[BILL-56] Implement TOUCHES edges (fork)"',
        '"2026-06-03T01:00:00Z"',
        '["BILL-99"]',
        f'"{_FORK_REPO}"',
    )
    db = FakeContextDB(touches_by_moniker={_MONIKER: [row_origin, row_fork]})
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ── Layer 2: POST /code-graph/ingest (updated) ────────────────────────────────


class TestIngestEndpointDocstrings:
    def test_returns_docstring_rows_key(
        self,
        ingest_client: TestClient,
    ):
        """Updated ingest endpoint must include docstring_rows in response body."""
        resp = ingest_client.post(
            "/code-graph/ingest",
            json={"repo": _REPO, "index": _SCIP_WITH_DOCS},
        )
        assert resp.status_code == 200, resp.text
        assert "docstring_rows" in resp.json(), (
            f"Missing 'docstring_rows' key in response: {resp.json()}"
        )

    def test_docstring_rows_count_equals_documented_symbols(
        self,
        ingest_client: TestClient,
    ):
        """One documented symbol in the index → docstring_rows == 1."""
        resp = ingest_client.post(
            "/code-graph/ingest",
            json={"repo": _REPO, "index": _SCIP_WITH_DOCS},
        )
        assert resp.status_code == 200
        assert resp.json()["docstring_rows"] == 1

    def test_docstring_rows_zero_when_no_documentation(
        self,
        ingest_client: TestClient,
    ):
        """No documentation fields in index → docstring_rows == 0."""
        resp = ingest_client.post(
            "/code-graph/ingest",
            json={"repo": _REPO, "index": _SCIP_NO_DOCS},
        )
        assert resp.status_code == 200
        assert resp.json()["docstring_rows"] == 0

    def test_write_docstring_rows_called_on_db_conn(
        self,
        ingest_client: TestClient,
        fake_ingest_db: FakeDocstringIngestDB,
    ):
        """Endpoint must call write_docstring_rows on the regular DB connection."""
        ingest_client.post(
            "/code-graph/ingest",
            json={"repo": _REPO, "index": _SCIP_WITH_DOCS},
        )
        assert fake_ingest_db.docstring_write_calls, (
            "Expected write_docstring_rows to be called, but it wasn't"
        )
        _rows, repo_arg = fake_ingest_db.docstring_write_calls[0]
        assert repo_arg == _REPO

    def test_no_write_call_when_no_documented_symbols(
        self,
        ingest_client: TestClient,
        fake_ingest_db: FakeDocstringIngestDB,
    ):
        """When no docstring rows are produced, write_docstring_rows is not called
        (or is called with an empty list — either is acceptable)."""
        ingest_client.post(
            "/code-graph/ingest",
            json={"repo": _REPO, "index": _SCIP_NO_DOCS},
        )
        # Either not called, or called with empty rows list
        for rows, _ in fake_ingest_db.docstring_write_calls:
            assert len(rows) == 0


# ── Layer 2: POST /code-graph/context ────────────────────────────────────────


class TestCodeGraphContextEndpoint:
    def test_endpoint_returns_200(self, context_client: TestClient):
        resp = context_client.post(
            "/code-graph/context",
            json={"monikers": []},
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text}"
        )

    def test_response_has_results_list(self, context_client: TestClient):
        resp = context_client.post(
            "/code-graph/context",
            json={"monikers": [_MONIKER]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert isinstance(body["results"], list)

    def test_returns_ticket_linkage_for_touched_moniker(
        self, context_client_with_touches: TestClient
    ):
        resp = context_client_with_touches.post(
            "/code-graph/context",
            json={"monikers": [_MONIKER]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        result = results[0]
        assert result["moniker"] == _MONIKER
        assert "BILL-56" in result["tickets"]
        assert any(c["sha"] == _SHA for c in result["commits"])

    def test_result_has_required_fields(
        self, context_client_with_touches: TestClient
    ):
        resp = context_client_with_touches.post(
            "/code-graph/context",
            json={"monikers": [_MONIKER]},
        )
        result = resp.json()["results"][0]
        assert "moniker" in result
        assert "repo" in result
        assert "tickets" in result
        assert "commits" in result

    def test_commit_entry_has_sha_subject_authored_at(
        self, context_client_with_touches: TestClient
    ):
        resp = context_client_with_touches.post(
            "/code-graph/context",
            json={"monikers": [_MONIKER]},
        )
        commit = resp.json()["results"][0]["commits"][0]
        assert "sha" in commit
        assert "subject" in commit
        assert "authored_at" in commit

    def test_empty_results_for_unknown_moniker(self, context_client: TestClient):
        unknown = "scip-go gomod unknown . unknown/NoSuchFn()."
        resp = context_client.post(
            "/code-graph/context",
            json={"monikers": [unknown]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        match = next(
            (r for r in results if r["moniker"] == unknown), None
        )
        assert match is None or match["tickets"] == []

    def test_empty_monikers_list_returns_empty_results(
        self, context_client: TestClient
    ):
        resp = context_client.post(
            "/code-graph/context",
            json={"monikers": []},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_groups_results_by_repo(
        self, context_client_two_repos: TestClient
    ):
        """Same moniker touched in two repos → two separate result entries."""
        resp = context_client_two_repos.post(
            "/code-graph/context",
            json={"monikers": [_MONIKER]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        repos = {r["repo"] for r in results}
        assert repos == {_REPO, _FORK_REPO}
        origin = next(r for r in results if r["repo"] == _REPO)
        fork = next(r for r in results if r["repo"] == _FORK_REPO)
        assert "BILL-56" in origin["tickets"]
        assert "BILL-99" in fork["tickets"]
        assert any(c["sha"] == _SHA for c in origin["commits"])
        assert any(c["sha"] == _FORK_SHA for c in fork["commits"])
