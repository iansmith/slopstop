"""Unit tests for the JIRA harvester (BILL-38).

No live JIRA API, no postgres, no model weights — per
`design/rag-service-testing.md`. Collaborators are injected:

  - `FakeJiraClient`: canned `HarvestedTicket`s for exercising the
    sync_ticket / sync_recent ingestion path without network.
  - `_FakeEmbedder`: deterministic 1024-dim vectors (same pattern as
    test_linear_harvester.py).
  - `_RecordingConn`: records rows `write_ticket` would persist.
  - `JiraRestClient` is tested over `httpx.MockTransport` (no live API):
    response parsing, rate-limit enforcement, and `startAt` pagination.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pytest

from rag_service.harvesters._common import (
    COMMENT_SEQ_BASE,
    HarvestedComment,
    HarvestedTicket,
    RateLimiter,
)
from rag_service.harvesters.jira import (
    JIRA_MAX_RPS,
    SOURCE,
    JiraRateLimitError,
    JiraRestClient,
    adf_to_text,
    sync_recent,
    sync_ticket,
)


# ---------------------------------------------------------------------------
# Fakes (same pattern as test_linear_harvester.py)
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

    def transaction(self):
        conn = self

        class _Txn:
            def __enter__(self):
                return conn

            def __exit__(self, *exc):
                return False

        return _Txn()

    def cursor(self):
        return _RecordingCursor(self)


class _VirtualClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class FakeJiraClient:
    """Canned-response JiraClient for sync orchestration tests.

    `tickets` maps issue key -> HarvestedTicket for fetch_ticket.
    `recent` is the full list fetch_recent yields.  No network involved.
    """

    def __init__(
        self,
        *,
        tickets: dict[str, HarvestedTicket] | None = None,
        recent: list[HarvestedTicket] | None = None,
    ) -> None:
        self._tickets = tickets or {}
        self._recent = recent or []
        self.fetch_ticket_calls: list[str] = []
        self.fetch_recent_calls: list[datetime] = []

    def fetch_ticket(self, issue_key: str) -> HarvestedTicket | None:
        self.fetch_ticket_calls.append(issue_key)
        return self._tickets.get(issue_key)

    def fetch_recent(self, since: datetime, *, start_at: int = 0):
        self.fetch_recent_calls.append((since, start_at))
        yield from self._recent[start_at:]


# ---------------------------------------------------------------------------
# Helpers to build HarvestedTicket test fixtures
# ---------------------------------------------------------------------------


def _ticket(identifier: str = "PROJ-123", **kw) -> HarvestedTicket:
    base = dict(
        source=SOURCE,
        ticket_id=identifier,
        title="Test ticket",
        description="A plain-text description.",
        comments=[HarvestedComment(body="A comment on the ticket.")],
    )
    base.update(kw)
    return HarvestedTicket(**base)


# ---------------------------------------------------------------------------
# ADF → plain-text conversion
# ---------------------------------------------------------------------------


def test_adf_paragraph_to_text():
    node = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Hello, world!"}],
            }
        ],
    }
    result = adf_to_text(node)
    assert "Hello, world!" in result


def test_adf_heading_to_text():
    node = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "My Heading"}],
            }
        ],
    }
    result = adf_to_text(node)
    assert "My Heading" in result


def test_adf_bullet_list_to_text():
    node = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Item one"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Item two"}],
                            }
                        ],
                    },
                ],
            }
        ],
    }
    result = adf_to_text(node)
    assert "Item one" in result
    assert "Item two" in result


def test_adf_ordered_list_to_text():
    node = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "orderedList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Step one"}],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    result = adf_to_text(node)
    assert "Step one" in result


def test_adf_code_block_preserves_fenced_format():
    """Code blocks must survive as fenced strings for the code-ref extractor."""
    node = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "codeBlock",
                "attrs": {"language": "python"},
                "content": [{"type": "text", "text": "def foo(): pass"}],
            }
        ],
    }
    result = adf_to_text(node)
    # The fenced block must contain the code body.
    assert "def foo(): pass" in result
    # Must be wrapped in backtick fences (``` ... ```) so strip_code_blocks
    # can find it later.
    assert "```" in result


def test_adf_unknown_node_falls_back_gracefully():
    """Exotic ADF nodes must not raise — they degrade to empty or their text."""
    node = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "exoticFutureNode",
                "content": [{"type": "text", "text": "some text"}],
            }
        ],
    }
    # Must not raise; may return empty string or fall through to child text.
    result = adf_to_text(node)
    assert isinstance(result, str)


def test_adf_empty_doc_returns_empty_string():
    node = {"type": "doc", "version": 1, "content": []}
    assert adf_to_text(node) == ""


def test_adf_mixed_content_preserves_order():
    """Heading + paragraph text should appear in document order."""
    node = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Title"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Body text here."}],
            },
        ],
    }
    result = adf_to_text(node)
    assert result.index("Title") < result.index("Body text here.")


# ---------------------------------------------------------------------------
# SOURCE constant
# ---------------------------------------------------------------------------


def test_source_constant_is_jira():
    assert SOURCE == "jira"


def test_jira_max_rps_at_most_5():
    """Rate limit must be ≤ 5 req/sec (JIRA Cloud ceiling is 10; we throttle to 5)."""
    assert JIRA_MAX_RPS <= 5


# ---------------------------------------------------------------------------
# sync_ticket — ingestion path with FakeJiraClient
# ---------------------------------------------------------------------------


def test_sync_ticket_writes_description_and_comment_chunks():
    client = FakeJiraClient(tickets={"PROJ-123": _ticket()})
    conn = _RecordingConn()
    n = sync_ticket(
        "PROJ-123",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert n == 2  # description + one comment
    assert client.fetch_ticket_calls == ["PROJ-123"]
    assert len(conn.inserts) == 2
    assert len(conn.deletes) == 1
    assert conn.deletes[0] == ("jira", "PROJ-123", "upstream")


def test_sync_ticket_missing_ticket_is_noop():
    client = FakeJiraClient(tickets={})
    conn = _RecordingConn()
    n = sync_ticket(
        "PROJ-999", client=client, conn=conn, embedder=_FakeEmbedder()
    )
    assert n == 0
    assert conn.inserts == [] and conn.deletes == []


def test_sync_ticket_embeds_every_row():
    client = FakeJiraClient(tickets={"PROJ-123": _ticket()})
    conn = _RecordingConn()
    sync_ticket(
        "PROJ-123",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    for params in conn.inserts:
        vec = next(p for p in params if isinstance(p, list) and len(p) == 1024)
        assert all(isinstance(x, float) for x in vec[:3])


def test_sync_ticket_assigns_seq_bands():
    """Description at seq 0, comment in the comment band (COMMENT_SEQ_BASE)."""
    client = FakeJiraClient(tickets={"PROJ-123": _ticket()})
    conn = _RecordingConn()
    sync_ticket(
        "PROJ-123",
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    seqs = sorted(params[5] for params in conn.inserts)
    assert seqs == [0, COMMENT_SEQ_BASE]


# ---------------------------------------------------------------------------
# sync_recent
# ---------------------------------------------------------------------------


def test_sync_recent_ingests_all_tickets():
    recent = [_ticket(identifier=f"PROJ-{i}") for i in range(5)]
    client = FakeJiraClient(recent=recent)
    conn = _RecordingConn()
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    n = sync_recent(
        since,
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
    )
    assert n == 10  # 5 tickets × (description + comment)
    assert len(conn.deletes) == 5


def test_sync_recent_empty_is_noop():
    client = FakeJiraClient(recent=[])
    conn = _RecordingConn()
    n = sync_recent(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
    )
    assert n == 0
    assert conn.inserts == []


def test_sync_recent_passes_since_to_client():
    since = datetime(2026, 5, 1, tzinfo=timezone.utc)
    client = FakeJiraClient(recent=[])
    conn = _RecordingConn()
    sync_recent(since, client=client, conn=conn, embedder=_FakeEmbedder())
    # fetch_recent_calls stores (since, start_at) tuples; default start_at=0
    assert client.fetch_recent_calls == [(since, 0)]


# ---------------------------------------------------------------------------
# JiraRestClient — real client over httpx.MockTransport (no network)
# ---------------------------------------------------------------------------


_ISSUE_PAYLOAD = {
    "key": "PROJ-123",
    "fields": {
        "summary": "A test issue",
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Issue description text."}],
                }
            ],
        },
        "comment": {
            "comments": [
                {
                    "id": "10001",
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "First comment."}
                                ],
                            }
                        ],
                    },
                    "author": {"displayName": "alice"},
                    "created": "2026-01-01T00:00:00.000+0000",
                }
            ]
        },
        "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
        "assignee": {"displayName": "bob"},
        "reporter": {"displayName": "carol"},
        "priority": {"name": "High"},
        "issuetype": {"name": "Bug"},
        "labels": ["needs-triage"],
        "created": "2026-01-01T00:00:00.000+0000",
        "updated": "2026-01-02T00:00:00.000+0000",
        "resolutiondate": None,
    },
    "self": "https://example.atlassian.net/rest/api/3/issue/PROJ-123",
}

_SEARCH_PAGE_1 = {
    "startAt": 0,
    "maxResults": 1,
    "total": 2,
    "issues": [_ISSUE_PAYLOAD],
}

_SEARCH_PAGE_2 = {
    "startAt": 1,
    "maxResults": 1,
    "total": 2,
    "issues": [
        {
            **_ISSUE_PAYLOAD,
            "key": "PROJ-124",
            "fields": {
                **_ISSUE_PAYLOAD["fields"],
                "summary": "Second issue",
            },
        }
    ],
}


def _mock_rest_client(
    handler,
    *,
    rate_limiter=None,
    **kw,
) -> JiraRestClient:
    """Build a JiraRestClient over httpx.MockTransport with a virtual-clock
    rate limiter so tests never incur real time.sleep.

    Uses the `transport=` injection point (not `http_client=`) so the client
    always builds its own httpx.Client with the real auth headers applied —
    auth correctness is testable by inspecting request.headers in the handler.
    """
    clock = _VirtualClock()
    rl = rate_limiter or RateLimiter(
        max_calls=10_000,
        period_s=1.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    return JiraRestClient(
        base_url="https://example.atlassian.net",
        email="test@example.com",
        api_token="fake-token",
        transport=httpx.MockTransport(handler),
        rate_limiter=rl,
        **kw,
    )


def test_rest_client_sends_basic_auth_header():
    """Authorization header must be Basic base64(email:api_token) on every request."""
    import base64

    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json=_ISSUE_PAYLOAD)

    client = _mock_rest_client(handler)
    client.fetch_ticket("PROJ-123")

    assert len(captured) == 1
    assert captured[0].startswith("Basic "), f"Expected Basic auth, got: {captured[0]!r}"
    # Verify the encoded credentials are correct.
    encoded = captured[0].removeprefix("Basic ")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "test@example.com:fake-token"


def test_rest_client_fetch_ticket_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ISSUE_PAYLOAD)

    client = _mock_rest_client(handler)
    ticket = client.fetch_ticket("PROJ-123")
    assert ticket is not None
    assert ticket.ticket_id == "PROJ-123"
    assert ticket.source == "jira"
    assert "Issue description text." in ticket.description
    assert len(ticket.comments) == 1
    assert "First comment." in ticket.comments[0].body
    assert ticket.comments[0].author == "alice"


def test_rest_client_fetch_ticket_returns_none_for_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errorMessages": ["Issue does not exist."]})

    client = _mock_rest_client(handler)
    ticket = client.fetch_ticket("PROJ-999")
    assert ticket is None


def test_rest_client_raises_on_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Rate limit exceeded"})

    client = _mock_rest_client(handler, max_retries=1, sleep=lambda s: None)
    with pytest.raises(JiraRateLimitError):
        client.fetch_ticket("PROJ-123")


def test_rest_client_paginates_via_start_at():
    """fetch_recent must paginate through all pages using startAt."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start_at = int(request.url.params.get("startAt", "0"))
        calls.append(start_at)
        if start_at == 0:
            return httpx.Response(200, json=_SEARCH_PAGE_1)
        return httpx.Response(200, json=_SEARCH_PAGE_2)

    client = _mock_rest_client(handler)
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tickets = list(client.fetch_recent(since))
    assert len(tickets) == 2
    assert any(t.ticket_id == "PROJ-123" for t in tickets)
    assert any(t.ticket_id == "PROJ-124" for t in tickets)
    # Must have made at least two requests (one per page).
    assert len(calls) >= 2


def test_rest_client_single_page_needs_no_extra_request():
    """When total == len(issues) on page 1, only one HTTP call is made."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "startAt": 0,
                "maxResults": 50,
                "total": 1,
                "issues": [_ISSUE_PAYLOAD],
            },
        )

    client = _mock_rest_client(handler)
    tickets = list(client.fetch_recent(datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert len(tickets) == 1
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# sync_recent — checkpoint / resume
# ---------------------------------------------------------------------------


def test_sync_recent_resumes_from_checkpoint(tmp_path):
    """If a checkpoint exists, sync_recent skips already-processed tickets."""
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cp_file = tmp_path / "jira_sync.json"
    # Simulate: 2 tickets already processed in a prior run.
    cp_file.write_text(json.dumps({"since": since.isoformat(), "start_at": 2}))

    recent = [_ticket(identifier=f"PROJ-{i}") for i in range(5)]
    client = FakeJiraClient(recent=recent)
    conn = _RecordingConn()

    n = sync_recent(
        since,
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
        checkpoint_path=cp_file,
    )
    # Only 3 tickets processed (PROJ-2, PROJ-3, PROJ-4); PROJ-0 and PROJ-1 skipped.
    assert n == 6  # 3 tickets × (description + comment)
    # The client received start_at=2 from the checkpoint.
    assert client.fetch_recent_calls[0][1] == 2


def test_sync_recent_deletes_checkpoint_on_completion(tmp_path):
    """Checkpoint file is removed after a successful run."""
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cp_file = tmp_path / "jira_sync.json"
    # Checkpoint starts empty (fresh run with checkpoint tracking enabled).

    client = FakeJiraClient(recent=[_ticket()])
    conn = _RecordingConn()
    sync_recent(
        since,
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
        checkpoint_path=cp_file,
    )
    # File must not exist after a clean completion.
    assert not cp_file.exists()


def test_sync_recent_updates_checkpoint_during_run(tmp_path):
    """Checkpoint is written incrementally so a mid-run crash is resumable."""
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cp_file = tmp_path / "jira_sync.json"

    checkpoints_seen: list[int] = []

    class _SpyConn(_RecordingConn):
        """Records the checkpoint start_at after every _ingest call."""
        def transaction(self):
            conn = self

            class _Txn:
                def __enter__(self):
                    return conn

                def __exit__(self, *exc):
                    # Capture checkpoint state after each commit boundary.
                    if cp_file.exists():
                        data = json.loads(cp_file.read_text())
                        checkpoints_seen.append(data.get("start_at", 0))
                    return False

            return _Txn()

    recent = [_ticket(identifier=f"PROJ-{i}") for i in range(3)]
    client = FakeJiraClient(recent=recent)
    conn = _SpyConn()

    sync_recent(
        since,
        client=client,
        conn=conn,
        embedder=_FakeEmbedder(),
        token_counter=_word_counter,
        checkpoint_path=cp_file,
    )
    # Checkpoint must have advanced at least once during the run (before the
    # final cleanup delete), proving it's written incrementally not just at end.
    assert len(checkpoints_seen) >= 1
    # The spy fires inside write_ticket's transaction().__exit__, which is one
    # iteration AHEAD of the _write_checkpoint call that follows _ingest.
    # Sequence for 3 tickets:
    #   ticket[0] txn exit  -> cp doesn't exist yet (nothing appended)
    #   _write_checkpoint   -> cp written with start_at=1
    #   ticket[1] txn exit  -> reads cp(1)  -> checkpoints_seen=[1]
    #   _write_checkpoint   -> cp written with start_at=2
    #   ticket[2] txn exit  -> reads cp(2)  -> checkpoints_seen=[1, 2]
    #   _write_checkpoint   -> cp written with start_at=3
    #   cp_file.unlink()    -> deleted (spy never sees start_at=3)
    # So the last snapshot the spy captures is 2, not 3.
    assert checkpoints_seen[-1] == 2
