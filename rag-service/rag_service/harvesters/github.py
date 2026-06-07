"""GitHub upstream harvester stub (BILL-32).

Implementation pending. This stub defines the public interface so pytest
can collect `tests/test_github_harvester.py` without ImportError. All
entry points raise NotImplementedError — see the ticket for the full spec.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import httpx
    import psycopg

    from rag_service.embed import Embedder
    from rag_service.harvesters._common import HarvestedTicket, RateLimiter

from rag_service.harvesters._common import _DEFAULT_TOKEN_COUNTER

SOURCE: str = "github"
GH_MAX_RPS: float = 1.0   # default 1 req/sec — well under 5000 pts/hr budget


class GitHubError(Exception):
    """Raised for GitHub API errors (HTTP errors or GraphQL error envelopes)."""


class GitHubGraphQLClient:
    """Sends GraphQL requests to https://api.github.com/graphql.

    Stub — not yet implemented (BILL-32).
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        # Stub: store args so the constructor doesn't raise; methods do.
        self._owner = owner
        self._repo = repo
        self._token = token
        self._transport = transport
        self._rate_limiter = rate_limiter

    def fetch_issue(self, number: int) -> HarvestedTicket:
        """Fetch a single issue (with all comments) as a HarvestedTicket."""
        raise NotImplementedError("fetch_issue not yet implemented — BILL-32")


def sync_ticket(
    ticket_id: str,
    *,
    client: GitHubGraphQLClient,
    conn: psycopg.Connection,
    embedder: Embedder,
    token_counter: Callable[[str], int] = _DEFAULT_TOKEN_COUNTER,
) -> int:
    """Full re-fetch + replace for one GitHub issue. Returns rows written."""
    raise NotImplementedError("sync_ticket not yet implemented — BILL-32")


def sync_recent(
    since: datetime,
    *,
    client: GitHubGraphQLClient,
    conn: psycopg.Connection,
    embedder: Embedder,
    sleep_per_request_sec: float = 1.0,
    token_counter: Callable[[str], int] = _DEFAULT_TOKEN_COUNTER,
) -> int:
    """Batch catch-up: re-index every issue updated at/after `since`.

    Returns the number of issues ingested (not chunk rows written).
    """
    raise NotImplementedError("sync_recent not yet implemented — BILL-32")
