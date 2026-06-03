"""Layer 2 tests for BILL-56 — commit provenance endpoint (POST /code-graph/ingest-commits).

Tests describe the behavior of the endpoint via TestClient with a fake AGE DB.
Pure-function tests live in test_code_graph_commit_ingest.py (Layer 1).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_service.db import get_age_conn
from rag_service.main import app

_REPO = "iansmith/slopstop"
_SHA = "9eb70fe1234567890abcdef1234567890abcdef12"
_FUNCTION_MONIKER = "scip-go gomod slopstop . db/setup_age_session()."

# Payload with file-level TOUCHES (changed_lines=None)
_FILE_LEVEL_PAYLOAD: dict = {
    "repo": _REPO,
    "sha": _SHA,
    "subject": "[BILL-55] Implement SCIP ingestion",
    "author": "Ian Smith",
    "authored_at": "2026-06-03T19:53:21Z",
    "ticket_ids": ["BILL-55"],
    "files": [
        {
            "path": "rag-service/rag_service/db.py",
            "change_type": "modified",
            "hunks": 2,
            "changed_lines": None,
        }
    ],
}

# Payload with function-level TOUCHES (changed_lines provided)
_FUNCTION_LEVEL_PAYLOAD: dict = {
    "repo": _REPO,
    "sha": _SHA,
    "subject": "[BILL-55] Implement SCIP ingestion",
    "author": "Ian Smith",
    "authored_at": "2026-06-03T19:53:21Z",
    "ticket_ids": ["BILL-55"],
    "files": [
        {
            "path": "rag-service/rag_service/db.py",
            "change_type": "modified",
            "hunks": 2,
            "changed_lines": [[190, 199]],
        }
    ],
}


# ── Fake ──────────────────────────────────────────────────────────────────────


class FakeCommitDB:
    """Stand-in for DB in the ingest-commits endpoint.

    ``function_rows_by_file`` maps file path to the list of raw agtype
    rows that run_cypher() returns for the function query.  Defaults to
    an empty dict (no functions indexed → file-level fallback).
    """

    def __init__(self, function_rows_by_file: dict | None = None) -> None:
        self.cypher_calls: list[str] = []
        self.function_rows_by_file: dict[str, list] = function_rows_by_file or {}

    def ping(self) -> bool:
        return True

    def has_table(self, name: str) -> bool:
        return True

    def knn_search(self, vec, k, filters=None) -> list:
        return []

    def run_cypher(self, cypher: str) -> list:
        self.cypher_calls.append(cypher)
        # For function queries, return seeded rows; for MERGE statements return [].
        if "MATCH" in cypher and "Function" in cypher and "IS NOT NULL" in cypher:
            for path, rows in self.function_rows_by_file.items():
                if path in cypher:
                    return rows
        return []


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_commit_db() -> FakeCommitDB:
    return FakeCommitDB()


@pytest.fixture
def commit_client(fake_commit_db: FakeCommitDB):
    """TestClient wired to FakeCommitDB only."""
    app.dependency_overrides[get_age_conn] = lambda: fake_commit_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def commit_client_with_functions():
    """TestClient whose fake DB returns one Function row for the test file."""
    db = FakeCommitDB(
        function_rows_by_file={
            "rag-service/rag_service/db.py": [
                (f'["{_FUNCTION_MONIKER}", [190, 0, 199, 4]]',)
            ]
        }
    )
    app.dependency_overrides[get_age_conn] = lambda: db
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()


# ── Layer 2: POST /code-graph/ingest-commits ──────────────────────────────────


class TestCommitIngestEndpoint:
    def test_returns_200(self, commit_client, fake_commit_db):
        resp = commit_client.post("/code-graph/ingest-commits", json=_FILE_LEVEL_PAYLOAD)
        assert resp.status_code == 200, resp.text

    def test_returns_commits_and_touches_counts(self, commit_client, fake_commit_db):
        resp = commit_client.post("/code-graph/ingest-commits", json=_FILE_LEVEL_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert "commits_merged" in body
        assert "touches_merged" in body
        assert body["commits_merged"] == 1
        assert body["touches_merged"] >= 1

    def test_issues_cypher_for_commit_vertex(self, commit_client, fake_commit_db):
        commit_client.post("/code-graph/ingest-commits", json=_FILE_LEVEL_PAYLOAD)
        commit_cypher = [c for c in fake_commit_db.cypher_calls if "Commit" in c]
        assert commit_cypher, "No Commit vertex Cypher was issued"
        assert any("MERGE" in c for c in commit_cypher)

    def test_issues_touches_cypher(self, commit_client, fake_commit_db):
        commit_client.post("/code-graph/ingest-commits", json=_FILE_LEVEL_PAYLOAD)
        touches = [c for c in fake_commit_db.cypher_calls if "TOUCHES" in c]
        assert touches, "No TOUCHES edge Cypher was issued"

    def test_file_level_touches_target_is_file_path(self, commit_client, fake_commit_db):
        """When changed_lines is null, TOUCHES edge target must be the file path."""
        commit_client.post("/code-graph/ingest-commits", json=_FILE_LEVEL_PAYLOAD)
        touches = [c for c in fake_commit_db.cypher_calls if "TOUCHES" in c]
        assert any("db.py" in c for c in touches)

    def test_function_level_touches_uses_function_moniker(
        self, commit_client_with_functions
    ):
        """When functions are found in AGE, TOUCHES target is the function moniker."""
        client, db = commit_client_with_functions
        resp = client.post("/code-graph/ingest-commits", json=_FUNCTION_LEVEL_PAYLOAD)
        assert resp.status_code == 200
        touches = [c for c in db.cypher_calls if "TOUCHES" in c]
        assert any(_FUNCTION_MONIKER in c for c in touches), (
            f"Expected TOUCHES to function moniker; got: {touches}"
        )

    def test_falls_back_to_file_when_no_functions_match(self, commit_client, fake_commit_db):
        """When function query returns empty (no SCIP index), fall back to file TOUCHES."""
        resp = commit_client.post("/code-graph/ingest-commits", json=_FUNCTION_LEVEL_PAYLOAD)
        assert resp.status_code == 200
        touches = [c for c in fake_commit_db.cypher_calls if "TOUCHES" in c]
        assert any("db.py" in c for c in touches)
        assert not any(_FUNCTION_MONIKER in c for c in touches)

    def test_multiple_files_produce_multiple_touches(self, commit_client, fake_commit_db):
        payload = {
            **_FILE_LEVEL_PAYLOAD,
            "files": [
                {"path": "file_a.go", "change_type": "modified", "hunks": 1, "changed_lines": None},
                {"path": "file_b.go", "change_type": "added", "hunks": 1, "changed_lines": None},
            ],
        }
        resp = commit_client.post("/code-graph/ingest-commits", json=payload)
        assert resp.status_code == 200
        assert resp.json()["touches_merged"] == 2

    def test_sha_present_in_cypher(self, commit_client, fake_commit_db):
        commit_client.post("/code-graph/ingest-commits", json=_FILE_LEVEL_PAYLOAD)
        assert any(_SHA in c for c in fake_commit_db.cypher_calls)
