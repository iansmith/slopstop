"""GitHub upstream harvester (BILL-32).

Fetches issues and comments from the GitHub GraphQL API v4, normalises them
into the source-neutral `HarvestedTicket` shape, and feeds them through the
shared ingestion spine in `_common.py` (chunking, code/ticket-ref extraction,
embedding, full-resync DB write). Source-specific concerns live here; nothing
GitHub-specific leaks into `_common.py`.

Two public sync entry points, matching the design's harvester interface
(`design/ticket-rag.md` §Ingestion → Upstream harvesters):

    sync_ticket(ticket_id, *, client, conn, embedder) -> int
    sync_recent(since, *, client, conn, embedder) -> int

Both accept injected collaborators (GitHubGraphQLClient, psycopg.Connection,
Embedder) so unit tests drive them with MockTransport + _FakeEmbedder +
_RecordingConn — zero live API calls, no postgres, no model weights
(`design/rag-service-testing.md`).

Auth: GitHub GraphQL API uses a Bearer token in the `Authorization: bearer
<token>` header (NOT Basic auth — the `Authorization: Basic …` form is for
the v3 REST API only). Tokens are personal access tokens (PATs) or GitHub
App installation tokens.

Rate-limit budget (`design/ticket-rag.md` §Rate-limit budgets):
GitHub GraphQL has a 5000-point/hr primary rate limit. A query for one issue
with up to 100 comments costs roughly 2–5 points, so the default 1 req/sec
(GH_MAX_RPS) keeps us well below the ceiling for typical harvests.

Credentials: `GITHUB_TOKEN` env var (takes precedence) or `[github] token`
in `.harvester.toml`. The CLI also reads `[github] repo = "owner/repo"` to
know which repository to harvest.

READ-ONLY: this harvester only issues POST requests to the GraphQL endpoint.
It never mutates any GitHub repository.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

_log = logging.getLogger(__name__)

import httpx

from rag_service.harvesters._common import (
    HARVESTER_CONFIG_PATH,
    HarvestedComment,
    HarvestedTicket,
    RateLimiter,
    _DEFAULT_TOKEN_COUNTER,
    ingest_ticket,
    ingest_ticket_batch,
    load_harvester_conf,
    open_conn,
    parse_harvester_dt,
    read_project_conf,
)

if TYPE_CHECKING:
    import psycopg

    from rag_service.embed import Embedder

SOURCE: str = "github"
GH_MAX_RPS: float = 1.0    # default 1 req/sec — well under 5000 pts/hr
_GH_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
_GH_TOKEN_ENV = "GITHUB_TOKEN"

# Validates "owner/repo" repo slugs (config, CLI).
_GH_OWNER_REPO_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")

# Validates and parses "owner/repo#N" ticket identifiers.
_GH_TICKET_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#(\d+)$")

# Map GitHub issue state → source-neutral state_norm.
# GitHub has exactly two states: OPEN / CLOSED (no in_progress or canceled).
_GH_STATE_NORM: dict[str, str] = {
    "OPEN": "open",
    "CLOSED": "done",
}


# ---------------------------------------------------------------------------
# GraphQL query strings
# ---------------------------------------------------------------------------

# Single-issue fetch with paginated comments.
# $cursor is null on the first page; set to endCursor on subsequent pages.
# Fields are inlined (no shared fragment constants) so changes to the
# paginated path can't accidentally affect the batch-recent path.
_FETCH_ISSUE_QUERY = """
query FetchIssue($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      number
      title
      body
      state
      author { login }
      createdAt
      updatedAt
      closedAt
      labels(first: 100) { nodes { name } }
      milestone { title }
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          author { login }
          createdAt
        }
      }
    }
  }
}
"""

# Comment-pagination continuation query — used by _fetch_comment_page.
# Fetches ONLY the comments block so continuation pages don't re-transmit all
# issue metadata (title, body, labels, etc.) that would be silently discarded.
_FETCH_ISSUE_COMMENTS_PAGE_QUERY = """
query FetchIssueCommentPage(
  $owner: String!
  $repo:  String!
  $number: Int!
  $cursor: String
) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        # NOTE: comment fields MUST match _FETCH_ISSUE_QUERY (lines 111–116).
        # Both feed all_comment_nodes → _issue_node_to_harvested in fetch_issue.
        nodes {
          id
          body
          author { login }
          createdAt
        }
      }
    }
  }
}
"""

# Batch recent-issues fetch — inline comments (first 100 per issue, no cursor).
# Issues with >100 comments are truncated on the batch path; use sync_ticket
# for completeness on high-comment issues.
# Fields are inlined independently from _FETCH_ISSUE_QUERY so the two query
# shapes can diverge without affecting each other.
_FETCH_RECENT_QUERY = """
query FetchRecentIssues(
  $owner: String!
  $repo:  String!
  $since: DateTime!
  $cursor: String
) {
  repository(owner: $owner, name: $repo) {
    issues(
      first: 100
      after: $cursor
      filterBy: { since: $since }
      orderBy: { field: UPDATED_AT, direction: DESC }
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        state
        author { login }
        createdAt
        updatedAt
        closedAt
        labels(first: 100) { nodes { name } }
        milestone { title }
        comments(first: 100) {
          nodes {
            id
            body
            author { login }
            createdAt
          }
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GitHubError(Exception):
    """Raised for GitHub API errors (HTTP errors or GraphQL error envelopes)."""


# ---------------------------------------------------------------------------
# GraphQL client
# ---------------------------------------------------------------------------


class GitHubGraphQLClient:
    """Sends GraphQL requests to https://api.github.com/graphql.

    Authenticates via `Authorization: bearer <token>` (PAT or App token).
    Rate-limits via the injected `RateLimiter` (default: GH_MAX_RPS req/sec).

    `transport=` injection keeps auth correctness testable: pass
    `transport=httpx.MockTransport(handler)` and the handler receives the real
    `Authorization` header — same approach as `JiraRestClient`.

    Unit tests do NOT build a real `GitHubGraphQLClient`; they pass a
    `_mock_client(responses)` factory that wraps the real class with a
    `MockTransport`.
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
        self.owner = owner
        self.repo = repo
        self._rate_limiter = rate_limiter or RateLimiter(
            max_calls=int(GH_MAX_RPS * 3600),
            period_s=3600.0,
            min_interval_s=1.0 / GH_MAX_RPS,
        )
        # Auth header is always applied here so the `transport=MockTransport`
        # path (tests) sees the real `Authorization` header — keeps auth
        # correctness testable without hitting the live API.
        self._http = httpx.Client(
            headers={
                "Authorization": f"bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
            transport=transport,
        )

    def close(self) -> None:
        """Release the underlying httpx connection pool."""
        self._http.close()

    def _post(self, query: str, variables: dict) -> dict:
        """Rate-limited POST to the GraphQL endpoint.

        Raises GitHubError on:
          - HTTP status != 200
          - Hard GraphQL failure: ``errors`` present and ``data`` absent or null.

        Partial-success responses (both ``data`` and ``errors`` present, e.g. a
        comment author who deleted their account) are logged as a single warning
        and returned — callers must guard against null fields in the payload.
        """
        self._rate_limiter.acquire()
        resp = self._http.post(
            _GH_GRAPHQL_ENDPOINT,
            json={"query": query, "variables": variables},
        )
        if resp.status_code != 200:
            raise GitHubError(
                f"GitHub GraphQL HTTP {resp.status_code}: {resp.text[:200]}"
            )
        payload = resp.json()
        if payload.get("errors"):
            if not payload.get("data"):
                # Hard failure: no usable data alongside the errors.
                msgs = "; ".join(e.get("message", str(e)) for e in payload["errors"])
                raise GitHubError(f"GitHub GraphQL error: {msgs}")
            # Partial success: valid data present alongside field-level errors
            # (e.g. a comment whose author deleted their account).  Log the
            # errors as warnings but continue with the data we have.
            _log.warning(
                "GitHub GraphQL partial success (%d field error(s)): %s",
                len(payload["errors"]),
                "; ".join(e.get("message", str(e)) for e in payload["errors"]),
            )
        return payload

    def _fetch_comment_page(
        self,
        number: int,
        cursor: str,
    ) -> tuple[list[dict], dict]:
        """Fetch one comment-pagination page for an issue.

        Called by ``fetch_issue`` for each continuation page after the first.
        Returns ``(comment_nodes, page_info)``.

        Raises ``GitHubError`` if the repository or issue disappears mid-pagination
        (e.g. the issue was deleted between the first and second requests).
        """
        payload = self._post(
            _FETCH_ISSUE_COMMENTS_PAGE_QUERY,
            {"owner": self.owner, "repo": self.repo, "number": number, "cursor": cursor},
        )
        repo_page = (payload.get("data") or {}).get("repository")
        if repo_page is None:
            raise GitHubError(
                f"Repository {self.owner!r}/{self.repo!r} became inaccessible "
                f"during comment pagination for issue #{number}"
            )
        issue_node = repo_page.get("issue")
        if issue_node is None:
            raise GitHubError(
                f"Issue #{number} disappeared during comment pagination in "
                f"{self.owner}/{self.repo}"
            )
        comments_block = issue_node.get("comments") or {}
        return comments_block.get("nodes") or [], comments_block.get("pageInfo") or {}

    def fetch_issue(self, number: int) -> HarvestedTicket:
        """Fetch a single issue (with ALL comments, paginated) as a HarvestedTicket.

        Paginates ``comments(first: 100, after: cursor)`` until
        ``pageInfo.hasNextPage`` is false, accumulating all comment nodes.
        Each continuation page is fetched via ``_fetch_comment_page``.
        """
        payload = self._post(
            _FETCH_ISSUE_QUERY,
            {"owner": self.owner, "repo": self.repo, "number": number, "cursor": None},
        )
        repo_data = (payload.get("data") or {}).get("repository")
        if repo_data is None:
            raise GitHubError(
                f"Repository {self.owner!r}/{self.repo!r} not found or inaccessible"
            )
        base_node = repo_data.get("issue")
        if base_node is None:
            raise GitHubError(f"Issue #{number} not found in {self.owner}/{self.repo}")
        comments_block = base_node.get("comments") or {}
        all_comment_nodes = list(comments_block.get("nodes") or [])
        page_info = comments_block.get("pageInfo") or {}

        prev_cursor: str | None = None
        while page_info.get("hasNextPage"):
            end_cursor = page_info.get("endCursor")
            if not end_cursor:
                raise GitHubError(
                    f"hasNextPage=true but endCursor missing for issue #{number}"
                )
            if end_cursor == prev_cursor:
                raise GitHubError(
                    f"Cursor loop detected for issue #{number} — aborting comment pagination"
                )
            prev_cursor = end_cursor
            more_nodes, page_info = self._fetch_comment_page(number, end_cursor)
            all_comment_nodes.extend(more_nodes)

        return _issue_node_to_harvested(base_node, self.owner, self.repo, all_comment_nodes)

    def fetch_recent_page(
        self,
        since_iso: str,
        cursor: str | None = None,
    ) -> tuple[list[HarvestedTicket], bool, str | None]:
        """Fetch one page of issues updated at/after `since_iso`.

        Returns ``(tickets, has_next_page, end_cursor)``.

        Nodes are mapped to ``HarvestedTicket`` objects before returning —
        consistent with ``fetch_issue``, which also returns a ``HarvestedTicket``.
        ``end_cursor`` is ``None`` when ``has_next_page`` is ``False``.

        Raises ``GitHubError`` if the repository or issues block is missing from
        the response (e.g. repository not found, Issues API disabled).
        """
        payload = self._post(
            _FETCH_RECENT_QUERY,
            {"owner": self.owner, "repo": self.repo, "since": since_iso, "cursor": cursor},
        )
        repo_data = (payload.get("data") or {}).get("repository")
        if repo_data is None:
            raise GitHubError(
                f"Repository {self.owner!r}/{self.repo!r} not found or inaccessible"
            )
        issues_block = repo_data.get("issues")
        if issues_block is None:
            raise GitHubError(
                f"Issues API unavailable for {self.owner!r}/{self.repo!r} "
                "(feature disabled or insufficient permissions)"
            )
        page_info = issues_block.get("pageInfo") or {}
        has_next = bool(page_info.get("hasNextPage"))
        end_cursor = page_info.get("endCursor") if has_next else None
        tickets = [
            _issue_node_to_harvested(
                node, self.owner, self.repo,
                (node.get("comments") or {}).get("nodes") or [],
            )
            for node in issues_block.get("nodes") or []
        ]
        return tickets, has_next, end_cursor


# ---------------------------------------------------------------------------
# Issue node → HarvestedTicket mapping
# ---------------------------------------------------------------------------


def _issue_node_to_harvested(
    node: dict,
    owner: str,
    repo: str,
    comment_nodes: list[dict],
) -> HarvestedTicket:
    """Map a GitHub GraphQL issue node to a source-neutral HarvestedTicket.

    `comment_nodes` is the full comment list assembled by the caller — may
    span multiple pagination pages (fetch_issue) or just the inline first-100
    (sync_recent).
    """
    number = node["number"]
    ticket_id = f"{owner}/{repo}#{number}"

    comments = [
        HarvestedComment(
            body=c.get("body") or "",
            author=c["author"]["login"] if c.get("author") else None,
            created_at=parse_harvester_dt(c.get("createdAt")),
            upstream_id=c.get("id"),
        )
        for c in comment_nodes
    ]

    label_nodes = (node.get("labels") or {}).get("nodes") or []
    milestone_node = node.get("milestone")

    return HarvestedTicket(
        source=SOURCE,
        ticket_id=ticket_id,
        title=node.get("title") or "",
        description=node.get("body") or "",
        url=f"https://github.com/{owner}/{repo}/issues/{number}",
        comments=comments,
        state_norm=_GH_STATE_NORM.get(node.get("state") or "OPEN", "open"),
        state_name=node.get("state"),
        # GitHub author = issue creator = reporter; assignees are separate.
        # We map reporter here; assignees not included in the minimal query
        # (tests don't require it; can be added in a follow-up).
        reporter=node["author"]["login"] if node.get("author") else None,
        ticket_labels=[lbl["name"] for lbl in label_nodes],
        milestone=milestone_node["title"] if milestone_node else None,
        ticket_created_at=parse_harvester_dt(node.get("createdAt")),
        ticket_updated_at=parse_harvester_dt(node.get("updatedAt")),
        ticket_closed_at=parse_harvester_dt(node.get("closedAt")),
    )


# ---------------------------------------------------------------------------
# Sync orchestration (injection-driven; unit-tested with fakes)
# ---------------------------------------------------------------------------


def sync_ticket(
    ticket_id: str,
    *,
    client: GitHubGraphQLClient,
    conn: psycopg.Connection,
    embedder: Embedder,
    token_counter: Callable[[str], int] = _DEFAULT_TOKEN_COUNTER,
) -> int:
    """Full re-fetch + replace for one GitHub issue. Returns rows written.

    `ticket_id` must be in `owner/repo#N` format (e.g. 'iansmith/slopstop#17').
    Raises ValueError for any other format — bare `#42` and unparseable strings
    are both rejected.
    """
    m = _GH_TICKET_RE.match(ticket_id)
    if m is None:
        raise ValueError(
            f"ticket_id {ticket_id!r} is not a valid GitHub ticket_id "
            "(expected 'owner/repo#N', e.g. 'iansmith/slopstop#17')"
        )
    number = int(m.group(3))
    ticket = client.fetch_issue(number)
    return ingest_ticket(ticket, conn=conn, embedder=embedder, token_counter=token_counter)


def sync_recent(
    since: datetime,
    *,
    client: GitHubGraphQLClient,
    conn: psycopg.Connection,
    embedder: Embedder,
    token_counter: Callable[[str], int] = _DEFAULT_TOKEN_COUNTER,
) -> int:
    """Batch catch-up: re-index every issue updated at/after `since`.

    Returns the number of issues ingested (not chunk rows written — one issue
    may produce multiple chunk rows depending on body/comment length).

    A naive `since` (no tzinfo) is coerced to UTC so the ISO-8601 string sent
    to GitHub is unambiguous.

    Comments are fetched inline (first 100 per issue). Issues with more than
    100 comments will be missing the tail on the batch path; use `sync_ticket`
    for high-comment issues if completeness is required.
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    since_iso = since.isoformat()
    cursor: str | None = None
    count = 0

    while True:
        prev_cursor = cursor
        page_tickets, has_next, cursor = client.fetch_recent_page(since_iso, cursor)
        ingest_ticket_batch(page_tickets, conn=conn, embedder=embedder, token_counter=token_counter)
        count += len(page_tickets)

        if not has_next:
            break
        if cursor is not None and cursor == prev_cursor:
            raise GitHubError(
                f"Cursor loop detected in sync_recent for "
                f"{client.owner!r}/{client.repo!r} — aborting pagination"
            )

    return count


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def _resolve_github_credentials(
    config_path: str = HARVESTER_CONFIG_PATH,
    *,
    cwd: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve (token, repo_slug).

    Priority:
    - token: ``GITHUB_TOKEN`` env var → ``~/.harvester.toml [github] token``
    - repo_slug: ``~/.harvester.toml [github] repo`` → ``.project-conf.toml key``
    """
    raw = os.environ.get(_GH_TOKEN_ENV)
    conf = (load_harvester_conf(config_path).get("github") or {})
    # Strip whitespace from both sources — trailing newlines are common when
    # the token comes from $(cat .token-file) or a copy-paste into .harvester.toml.
    token = (raw or conf.get("token") or "").strip() or None
    repo_slug = conf.get("repo") or read_project_conf(cwd).get("key") or None
    return (token, repo_slug)


def _build_real_client() -> GitHubGraphQLClient:
    token, repo_slug = _resolve_github_credentials()

    if not token:
        raise SystemExit(
            f"GitHub token not found. Set {_GH_TOKEN_ENV!r} or add to .harvester.toml:\n"
            "  [github]\n"
            '  token = "ghp_..."\n'
            '  repo  = "owner/repo"\n'
            "See design/ticket-rag.md § Harvester credentials."
        )
    if not repo_slug:
        raise SystemExit(
            "GitHub repo not configured. Add to .harvester.toml:\n"
            "  [github]\n"
            '  repo = "owner/repo"  # e.g. "iansmith/slopstop"\n'
        )

    m = _GH_OWNER_REPO_RE.match(repo_slug)
    if m is None:
        raise SystemExit(
            f"Invalid [github] repo {repo_slug!r} in .harvester.toml — expected 'owner/repo'."
        )

    return GitHubGraphQLClient(owner=m.group(1), repo=m.group(2), token=token)


# ---------------------------------------------------------------------------
# CLI (the only place real collaborators are constructed)
# ---------------------------------------------------------------------------

try:
    import click
except ImportError:  # pragma: no cover
    click = None  # type: ignore[assignment]


if click is not None:

    @click.group()
    def cli() -> None:
        """GitHub harvester for the ticket-rag service."""

    @cli.command("sync-ticket")
    @click.option(
        "--id",
        "ticket_id",
        required=True,
        help="GitHub issue in 'owner/repo#N' format, e.g. iansmith/slopstop#17",
    )
    def sync_ticket_cmd(ticket_id: str) -> None:
        """Re-index a single GitHub issue."""
        from rag_service.embed import get_embedder

        client = _build_real_client()
        conn = None
        try:
            conn = open_conn()
            n = sync_ticket(ticket_id, client=client, conn=conn, embedder=get_embedder())
        finally:
            if conn is not None:
                conn.close()
            client.close()
        click.echo(f"{ticket_id}: wrote {n} chunk row(s)")

    @cli.command("sync-recent")
    @click.option(
        "--since",
        required=True,
        help="ISO-8601 timestamp (e.g. 2024-01-01 or 2024-01-01T00:00:00+00:00)",
    )
    def sync_recent_cmd(since: str) -> None:
        """Re-index every GitHub issue updated at/after a given timestamp."""
        from rag_service.embed import get_embedder

        since_dt = parse_harvester_dt(since)
        if since_dt is None:
            raise click.BadParameter(
                f"Could not parse {since!r} as a datetime",
                param_hint="'--since'",
            )

        client = _build_real_client()
        conn = None
        try:
            conn = open_conn()
            n = sync_recent(since_dt, client=client, conn=conn, embedder=get_embedder())
        finally:
            if conn is not None:
                conn.close()
            client.close()
        click.echo(f"since {since}: synced {n} issue(s)")

    if __name__ == "__main__":  # pragma: no cover
        cli()
