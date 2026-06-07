"""Unit tests for the GitHub harvester (BILL-32).

No live GitHub API, no postgres, no model weights — per
`design/rag-service-testing.md`. Collaborators are injected:

  - `_FakeEmbedder`: deterministic 1024-dim vectors (same pattern as
    test_jira_harvester.py).
  - `_RecordingConn`: records rows `write_ticket` would persist.
  - `GitHubGraphQLClient` is tested over `httpx.MockTransport` (no live API):
    response parsing, Bearer auth, pagination.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import numpy as np
import pytest

from rag_service.harvesters._common import (
    COMMENT_SEQ_BASE,
    HarvestedTicket,
    RateLimiter,
)
from rag_service.harvesters.github import (
    GH_MAX_RPS,
    SOURCE,
    GitHubError,
    GitHubGraphQLClient,
    sync_recent,
    sync_ticket,
)


# ---------------------------------------------------------------------------
# Fakes (same pattern as test_jira_harvester.py)
# ---------------------------------------------------------------------------


def _word_counter(text: str) -> int:
    return len(text.split())


class _FakeEmbedder:
    def encode_passage(self, text: str) -> np.ndarray:
        return np.full(1024, float(len(text) % 7), dtype=np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return np.stack([self.encode_passage(t) for t in texts])


class _RecordingCursor:
    def __init__(self, conn: _RecordingConn) -> None:
        self._conn = conn

    def execute(self, sql: str, params=None) -> None:
        if "ticket_meta" in sql:
            return
        if sql.strip().upper().startswith("DELETE"):
            self._conn.deletes.append(params)
        else:
            self._conn.inserts.append(params)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingConn:
    def __init__(self) -> None:
        self.deletes: list = []
        self.inserts: list = []

    def cursor(self):
        return _RecordingCursor(self)

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# GraphQL response fixtures
# ---------------------------------------------------------------------------


def _issue_response(
    number: int = 7,
    title: str = "Test issue",
    body: str | None = "A description.",
    state: str = "OPEN",
    author: str | None = "octocat",
    created_at: str = "2024-01-15T10:00:00Z",
    updated_at: str = "2024-01-15T11:00:00Z",
    closed_at: str | None = None,
    comments: list[dict] | None = None,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict:
    """Build a minimal GitHub GraphQL `repository.issue` response."""
    return {
        "data": {
            "repository": {
                "issue": {
                    "number": number,
                    "title": title,
                    "body": body,
                    "state": state,
                    "author": {"login": author} if author else None,
                    "createdAt": created_at,
                    "updatedAt": updated_at,
                    "closedAt": closed_at,
                    "labels": {"nodes": []},
                    "milestone": None,
                    "comments": {
                        "pageInfo": {
                            "hasNextPage": has_next_page,
                            "endCursor": end_cursor,
                        },
                        "nodes": comments or [],
                    },
                }
            }
        }
    }


def _recent_response(
    issues: list[dict] | None = None,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict:
    """Build a minimal GitHub GraphQL `repository.issues` (list) response."""
    return {
        "data": {
            "repository": {
                "issues": {
                    "pageInfo": {
                        "hasNextPage": has_next_page,
                        "endCursor": end_cursor,
                    },
                    "nodes": issues or [],
                }
            }
        }
    }


def _gql_error_response(message: str = "Something went wrong") -> dict:
    """HTTP 200 + errors array — the GraphQL error envelope."""
    return {"errors": [{"message": message}]}


def _comment_node(
    body: str,
    author: str | None = "commenter",
    created_at: str = "2024-01-16T09:00:00Z",
    node_id: str = "IC_kwABCDE",
) -> dict:
    return {
        "id": node_id,
        "body": body,
        "author": {"login": author} if author else None,
        "createdAt": created_at,
    }


def _bare_issue(number: int, updated_at: str = "2024-03-01T00:00:00Z") -> dict:
    """Minimal issue node for a recent-issues list (no comments)."""
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": "Body text.",
        "state": "OPEN",
        "author": {"login": "octocat"},
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": updated_at,
        "closedAt": None,
        "labels": {"nodes": []},
        "milestone": None,
        "comments": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [],
        },
    }


def _mock_client(
    responses: list[dict],
    *,
    token: str = "fake-token",
    owner: str = "iansmith",
    repo: str = "slopstop",
) -> GitHubGraphQLClient:
    """Return a GitHubGraphQLClient backed by a MockTransport."""
    idx = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal idx
        payload = responses[min(idx, len(responses) - 1)]
        idx += 1
        return httpx.Response(200, json=payload)

    return GitHubGraphQLClient(
        owner=owner,
        repo=repo,
        token=token,
        transport=httpx.MockTransport(handler),
        rate_limiter=RateLimiter(max_calls=5000, period_s=3600, min_interval_s=0.0),
    )


# ---------------------------------------------------------------------------
# GitHubGraphQLClient — Bearer auth header
# ---------------------------------------------------------------------------


def test_graphql_client_sends_bearer_auth_header():
    """Client must send 'Authorization: bearer <token>' on every request."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_issue_response())

    client = GitHubGraphQLClient(
        owner="iansmith",
        repo="slopstop",
        token="my-secret-token",
        transport=httpx.MockTransport(handler),
        rate_limiter=RateLimiter(max_calls=5000, period_s=3600, min_interval_s=0.0),
    )
    client.fetch_issue(7)
    assert len(captured) == 1
    auth = captured[0].headers.get("authorization", "")
    assert auth == "bearer my-secret-token", f"Got: {auth!r}"


def test_graphql_client_does_not_use_basic_auth():
    """GitHub GraphQL uses Bearer, not Basic. No 'Basic ' prefix allowed."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_issue_response())

    client = GitHubGraphQLClient(
        owner="iansmith",
        repo="slopstop",
        token="gh_token_xyz",
        transport=httpx.MockTransport(handler),
        rate_limiter=RateLimiter(max_calls=5000, period_s=3600, min_interval_s=0.0),
    )
    client.fetch_issue(7)
    auth = captured[0].headers.get("authorization", "")
    assert not auth.startswith("Basic "), f"Should not be Basic auth, got: {auth!r}"


# ---------------------------------------------------------------------------
# GitHubGraphQLClient — response parsing
# ---------------------------------------------------------------------------


def test_fetch_issue_returns_harvested_ticket():
    """fetch_issue maps the GraphQL payload to a HarvestedTicket."""
    client = _mock_client([_issue_response(
        number=17,
        title="Entrypoint orchestration",
        body="Runs the startup sequence.",
        author="iansmith",
        comments=[_comment_node("Looks good.")],
    )])
    ticket = client.fetch_issue(17)
    assert isinstance(ticket, HarvestedTicket)
    assert ticket.ticket_id == "iansmith/slopstop#17"
    assert ticket.title == "Entrypoint orchestration"
    assert ticket.description == "Runs the startup sequence."
    assert ticket.source == SOURCE
    assert len(ticket.comments) == 1
    assert ticket.comments[0].body == "Looks good."


def test_fetch_issue_null_body_becomes_empty_string():
    """An issue with body=null (GitHub allows this) produces empty description."""
    client = _mock_client([_issue_response(body=None)])
    ticket = client.fetch_issue(7)
    assert ticket.description == ""


def test_fetch_issue_null_author_produces_none():
    """An issue whose author was deleted (author=null) has assignee=None."""
    client = _mock_client([_issue_response(author=None)])
    ticket = client.fetch_issue(7)
    assert ticket.assignee is None


def test_fetch_issue_no_comments_produces_empty_list():
    """An issue with zero comments → HarvestedTicket.comments == []."""
    client = _mock_client([_issue_response(comments=[])])
    ticket = client.fetch_issue(7)
    assert ticket.comments == []


def test_fetch_issue_comment_null_author_is_none():
    """A comment from a deleted account (author=null) → comment.author is None."""
    client = _mock_client([_issue_response(
        comments=[_comment_node("A comment.", author=None)]
    )])
    ticket = client.fetch_issue(7)
    assert ticket.comments[0].author is None


def test_fetch_issue_state_open_maps_to_open_norm():
    """GitHub OPEN state maps to state_norm='open'."""
    client = _mock_client([_issue_response(state="OPEN")])
    ticket = client.fetch_issue(7)
    assert ticket.state_norm == "open"


def test_fetch_issue_state_closed_maps_to_done_norm():
    """GitHub CLOSED state maps to state_norm='done'."""
    client = _mock_client([_issue_response(state="CLOSED", closed_at="2024-02-01T00:00:00Z")])
    ticket = client.fetch_issue(7)
    assert ticket.state_norm == "done"


def test_fetch_issue_raises_on_graphql_errors():
    """GraphQL error response (HTTP 200 + errors array) raises GitHubError."""
    client = _mock_client([_gql_error_response("Could not resolve to a Repository")])
    with pytest.raises(GitHubError):
        client.fetch_issue(7)


def test_fetch_issue_raises_on_http_error():
    """Non-200 HTTP response raises GitHubError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    client = GitHubGraphQLClient(
        owner="iansmith",
        repo="slopstop",
        token="bad-token",
        transport=httpx.MockTransport(handler),
        rate_limiter=RateLimiter(max_calls=5000, period_s=3600, min_interval_s=0.0),
    )
    with pytest.raises(GitHubError):
        client.fetch_issue(7)


# ---------------------------------------------------------------------------
# GitHubGraphQLClient — comment pagination
# ---------------------------------------------------------------------------


def test_fetch_issue_paginates_comments():
    """fetch_issue follows hasNextPage for comments and collects all pages."""
    page1 = _issue_response(
        number=7,
        comments=[_comment_node("First.", node_id="C1")],
        has_next_page=True,
        end_cursor="cursor_abc",
    )
    # Second page: same issue, more comments only
    page2 = {
        "data": {
            "repository": {
                "issue": {
                    "number": 7,
                    "title": "Test issue",
                    "body": "A description.",
                    "state": "OPEN",
                    "author": {"login": "octocat"},
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T11:00:00Z",
                    "closedAt": None,
                    "labels": {"nodes": []},
                    "milestone": None,
                    "comments": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [_comment_node("Second.", node_id="C2")],
                    },
                }
            }
        }
    }
    client = _mock_client([page1, page2])
    ticket = client.fetch_issue(7)
    assert len(ticket.comments) == 2
    assert ticket.comments[0].body == "First."
    assert ticket.comments[1].body == "Second."


# ---------------------------------------------------------------------------
# sync_ticket — ingestion
# ---------------------------------------------------------------------------


def test_sync_ticket_description_and_comment_rows():
    """sync_ticket writes 1 description row + N comment rows."""
    client = _mock_client([_issue_response(
        number=17,
        title="My ticket",
        body="Some description text.",
        comments=[
            _comment_node("Comment A."),
            _comment_node("Comment B."),
        ],
    )])
    conn = _RecordingConn()
    sync_ticket(
        "iansmith/slopstop#17",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert len(conn.deletes) == 1       # one full-resync DELETE
    assert len(conn.inserts) == 3       # 1 description + 2 comments


def test_sync_ticket_delete_before_insert():
    """Full-resync: DELETE must precede every INSERT."""
    ops: list[str] = []

    class _OrderCursor:
        def execute(self, sql: str, params=None) -> None:
            if "ticket_meta" in sql:
                return
            ops.append("DELETE" if sql.strip().upper().startswith("DELETE") else "INSERT")

        def __enter__(self): return self
        def __exit__(self, *exc): return False

    class _OrderConn:
        def cursor(self): return _OrderCursor()
        def transaction(self): return self
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    client = _mock_client([_issue_response(comments=[_comment_node("A.")])])
    sync_ticket(
        "iansmith/slopstop#7",
        client=client,
        conn=_OrderConn(),
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert ops, "No DB operations recorded"
    assert ops[0] == "DELETE", f"First op must be DELETE, got {ops}"
    assert all(op == "INSERT" for op in ops[1:])


def test_sync_ticket_no_comments_still_deletes():
    """Even with no comments, a DELETE is issued (clears any stale rows)."""
    client = _mock_client([_issue_response(comments=[])])
    conn = _RecordingConn()
    sync_ticket(
        "iansmith/slopstop#7",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert len(conn.deletes) == 1
    assert len(conn.inserts) == 1   # description only


def test_sync_ticket_null_body_still_produces_one_chunk():
    """An issue with no body produces 1 chunk (the title)."""
    client = _mock_client([_issue_response(title="Bare title", body=None)])
    conn = _RecordingConn()
    sync_ticket(
        "iansmith/slopstop#7",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert len(conn.inserts) == 1
    # text column is at index 9 in _INSERT_COLUMNS
    assert "Bare title" in conn.inserts[0][9]


def test_sync_ticket_source_is_github():
    """Every persisted row must carry source='github'."""
    client = _mock_client([_issue_response()])
    conn = _RecordingConn()
    sync_ticket(
        "iansmith/slopstop#7",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    for row in conn.inserts:
        assert row[0] == "github", f"source must be 'github', got {row[0]!r}"


def test_sync_ticket_canonical_ticket_id_in_rows():
    """Persisted rows must carry the canonical 'owner/repo#N' ticket_id."""
    client = _mock_client([_issue_response(number=42)])
    conn = _RecordingConn()
    sync_ticket(
        "iansmith/slopstop#42",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    for row in conn.inserts:
        assert row[1] == "iansmith/slopstop#42"


def test_sync_ticket_comment_seq_at_comment_seq_base():
    """First comment chunk must use seq=COMMENT_SEQ_BASE, not seq=1."""
    client = _mock_client([_issue_response(
        comments=[_comment_node("A comment.")]
    )])
    conn = _RecordingConn()
    sync_ticket(
        "iansmith/slopstop#7",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    # seq is index 5 in _INSERT_COLUMNS
    seqs = [row[5] for row in conn.inserts]
    assert seqs[0] == 0, f"description must be seq=0, got {seqs[0]}"
    assert seqs[1] == COMMENT_SEQ_BASE, f"first comment must be seq={COMMENT_SEQ_BASE}, got {seqs[1]}"


def test_sync_ticket_invalid_id_raises_value_error():
    """ticket_id that can't be parsed as 'owner/repo#N' raises ValueError."""
    client = _mock_client([_issue_response()])
    with pytest.raises(ValueError, match="ticket_id"):
        sync_ticket(
            "not-a-valid-id",
            client=client,
            conn=_RecordingConn(),
            embedder=_FakeEmbedder(),
            token_counter=_word_counter,
        )


def test_sync_ticket_bare_number_id_raises_value_error():
    """A bare '#42' without repo context is not a valid sync_ticket identifier."""
    client = _mock_client([_issue_response()])
    with pytest.raises(ValueError, match="ticket_id"):
        sync_ticket(
            "#42",
            client=client,
            conn=_RecordingConn(),
            embedder=_FakeEmbedder(),
            token_counter=_word_counter,
        )


# ---------------------------------------------------------------------------
# sync_recent — pagination, return count, edge cases
# ---------------------------------------------------------------------------


def test_sync_recent_returns_count_of_synced_issues():
    """sync_recent returns number of issues ingested (not chunk rows)."""
    client = _mock_client([
        _recent_response(issues=[_bare_issue(1), _bare_issue(2)])
    ])
    conn = _RecordingConn()
    count = sync_recent(
        since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert count == 2


def test_sync_recent_no_results_returns_zero():
    """sync_recent with no matching issues returns 0 (not an error)."""
    client = _mock_client([_recent_response(issues=[])])
    conn = _RecordingConn()
    count = sync_recent(
        since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert count == 0


def test_sync_recent_paginates_across_pages():
    """sync_recent follows hasNextPage and counts issues from all pages."""
    page1 = _recent_response(
        issues=[_bare_issue(1), _bare_issue(2)],
        has_next_page=True,
        end_cursor="cursor_page2",
    )
    page2 = _recent_response(
        issues=[_bare_issue(3)],
        has_next_page=False,
    )
    client = _mock_client([page1, page2])
    conn = _RecordingConn()
    count = sync_recent(
        since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert count == 3
    assert len(conn.deletes) == 3   # one DELETE per issue (full-resync)


def test_sync_recent_each_issue_separate_resync():
    """Each issue is a standalone full-resync: 5 issues → 5 DELETEs."""
    client = _mock_client([
        _recent_response(issues=[_bare_issue(i) for i in range(5)])
    ])
    conn = _RecordingConn()
    sync_recent(
        since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert len(conn.deletes) == 5


def test_sync_recent_naive_since_treated_as_utc():
    """A naive since datetime (no tzinfo) must be treated as UTC, not crash."""
    client = _mock_client([_recent_response(issues=[])])
    conn = _RecordingConn()
    # Must not raise; must produce the same result as the UTC-aware equivalent.
    count = sync_recent(
        since=datetime(2024, 1, 1),  # naive — no tzinfo
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert count == 0


def test_sync_recent_single_page_no_pagination():
    """When hasNextPage is False, only one page request is made."""
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json=_recent_response(
            issues=[_bare_issue(1)],
            has_next_page=False,
        ))

    client = GitHubGraphQLClient(
        owner="iansmith",
        repo="slopstop",
        token="tok",
        transport=httpx.MockTransport(handler),
        rate_limiter=RateLimiter(max_calls=5000, period_s=3600, min_interval_s=0.0),
    )
    conn = _RecordingConn()
    sync_recent(
        since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert request_count == 1, f"Expected 1 request, got {request_count}"


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


def test_source_constant_is_github():
    assert SOURCE == "github"


def test_gh_max_rps_positive():
    """GH_MAX_RPS must be positive (default 1 req/sec)."""
    assert GH_MAX_RPS > 0
