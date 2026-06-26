"""JIRA upstream harvester (BILL-38).

Fetches tickets from the JIRA Cloud REST API v3, normalises them into the
source-neutral `HarvestedTicket` shape, and feeds them through the shared
ingestion spine in `_common.py` (chunking, code/ticket-ref extraction,
embedding, full-resync DB write). Source-specific concerns live here; nothing
JIRA-specific leaks into `_common.py`.

Two public sync entry points, matching the design's harvester interface
(`design/ticket-rag.md` §Ingestion → Upstream harvesters):

    sync_ticket(identifier, *, client, conn, embedder) -> int
    sync_recent(since, *, client, conn, embedder[, checkpoint_path]) -> int

Both take their collaborators by injection (a `JiraClient`, a psycopg
`Connection`, an `Embedder`) so unit tests drive them with a `FakeJiraClient`
+ `_FakeEmbedder` + a recording fake connection — **zero live API calls, no
postgres, no model weights** (`design/rag-service-testing.md`). The `click` CLI
at the bottom is the only place that constructs the real collaborators.

Rate-limit budget (`design/ticket-rag.md` §Rate-limit budgets). JIRA Cloud's
ceiling is 10 req/sec per user; we throttle to 5 req/sec — well inside the
ceiling and leaves headroom for the user's other JIRA-touching tools.
Rate-limiting is simpler than Linear: REST (not GraphQL), so there are no
complexity points — only a request-count `RateLimiter`.

JIRA signals rate-limiting with **HTTP 429** (unlike Linear's HTTP 400 +
RATELIMITED GraphQL error). `JiraRestClient._get()` detects 429, backs off
exponentially, and raises `JiraRateLimitError` after `max_retries` attempts.

Pagination uses JIRA's cursor-based `nextPageToken` (POST /rest/api/3/search/jql).
`fetch_recent()` is a **generator** that yields tickets as they arrive from
each page, so `sync_recent` interleaves HTTP fetches with embedding work (each
page's embedding time is free throttle before the next API call).

`sync_recent` accepts an optional `checkpoint_path`. After each page is
committed, a checkpoint is written atomically (write temp + rename). On re-run
the checkpoint is read and `fetch_recent` starts at the saved cursor — no
redundant API calls for already-processed pages. The checkpoint is deleted on
clean completion.

NOTE: Atlassian removed `GET /rest/api/3/search` in 2026 (changelog CHANGE-2046).
The harvester was migrated to `POST /rest/api/3/search/jql` which uses cursor-based
pagination (`nextPageToken`) instead of `startAt`/`total`.

Credentials: `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_BASE_URL` env vars (takes
precedence), then `[jira]` section in `.harvester.toml`. JIRA Cloud uses HTTP
Basic auth: `Authorization: Basic base64(email:api_token)`.

JIRA descriptions and comments are returned as Atlassian Document Format (ADF)
JSON trees. `adf_to_text()` converts them to plain text. Common node types are
handled explicitly; unknown types fall back to child-text extraction (never
raises). Code blocks are preserved as triple-backtick fences so the shared
`strip_code_blocks()` pipeline can mine them for code refs.

READ-ONLY: this harvester only ever issues GET/POST read-only requests against
JIRA. It never mutates any JIRA workspace.
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, Protocol

from rag_service.harvesters._common import (
    HARVESTER_CONFIG_PATH,
    _DEFAULT_TOKEN_COUNTER,
    HarvestedComment,
    HarvestedTicket,
    RateLimiter,
    ingest_ticket,
    load_harvester_conf,
    open_conn,
    parse_harvester_dt,
    read_project_conf_prefix,
)

import httpx

if TYPE_CHECKING:
    import psycopg

    from rag_service.embed import Embedder

SOURCE = "jira"
JIRA_MAX_RPS = 5           # req/sec ceiling we enforce (Cloud limit is 10)
JIRA_RATE_PERIOD_S = 1.0   # sliding-window period
JIRA_BATCH_SIZE = 50       # tickets per search-API page

JIRA_EMAIL_ENV = "JIRA_EMAIL"
JIRA_API_TOKEN_ENV = "JIRA_API_TOKEN"
JIRA_BASE_URL_ENV = "JIRA_BASE_URL"

# Map JIRA `statusCategory.key` → source-neutral state_norm.
# JIRA Cloud defines exactly three stable category keys (Atlassian docs):
#   "new"           → not-started work
#   "indeterminate" → in-progress work
#   "done"          → completed/resolved work
_JIRA_STATUS_NORM: dict[str, str] = {
    "new": "open",
    "indeterminate": "in_progress",
    "done": "done",
}

# Fields to request from JIRA's issue and search endpoints.
# Stored as a list so it can be used as a JSON array in the POST search body.
# For the GET /issue/{key} endpoint, join with commas: ",".join(_ISSUE_FIELDS).
_ISSUE_FIELDS = [
    "summary", "description", "comment", "status", "assignee", "reporter",
    "priority", "issuetype", "labels", "created", "updated", "resolutiondate",
]


# ---------------------------------------------------------------------------
# ADF → plain-text converter
# ---------------------------------------------------------------------------

# Handler signature: (node, content) -> str.
# Each function handles one ADF block type; _adf_text_node is the
# default for unknown types (recurse into children, never raise).

def _adf_text_node(node: dict, content: list) -> str:
    return "".join(adf_to_text(c) for c in content)


def _adf_para_node(node: dict, content: list) -> str:
    return _adf_text_node(node, content) + "\n"


def _adf_heading_node(node: dict, content: list) -> str:
    level = (node.get("attrs") or {}).get("level", 1)
    return "#" * level + " " + _adf_text_node(node, content) + "\n"


def _adf_bullet_node(node: dict, content: list) -> str:
    return "\n".join("- " + adf_to_text(item).rstrip("\n") for item in content) + "\n"


def _adf_ordered_node(node: dict, content: list) -> str:
    return "\n".join(
        f"{i}. " + adf_to_text(item).rstrip("\n") for i, item in enumerate(content, 1)
    ) + "\n"


def _adf_code_node(node: dict, content: list) -> str:
    language = (node.get("attrs") or {}).get("language", "")
    return f"```{language}\n{_adf_text_node(node, content)}\n```\n"


_ADF_DISPATCH: dict[str, Callable] = {
    "doc":         _adf_text_node,
    "paragraph":   _adf_para_node,
    "listItem":    _adf_text_node,
    "heading":     _adf_heading_node,
    "bulletList":  _adf_bullet_node,
    "orderedList": _adf_ordered_node,
    "codeBlock":   _adf_code_node,
}


def adf_to_text(node: dict | str) -> str:
    """Convert an Atlassian Document Format (ADF) node to plain text.

    Handles JIRA Cloud (ADF dict) and JIRA Server (raw string) descriptions.
    Code blocks are wrapped in triple-backtick fences so the shared
    `strip_code_blocks()` pipeline can extract them for code-ref analysis.
    Headings use markdown `#` prefixes so the heading-anchored chunker
    recognises them.

    Unknown node types recurse into their children (never raises).
    """
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type", "")
    if node_type == "text":
        return node.get("text", "")
    if node_type == "hardBreak":
        return "\n"
    content = node.get("content") or []
    return _ADF_DISPATCH.get(node_type, _adf_text_node)(node, content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _adf_or_str(raw: dict | str | None) -> str:
    """Normalise a JIRA text field: ADF dict → plain text, str → passthrough, None → ""."""
    if isinstance(raw, dict):
        return adf_to_text(raw)
    if isinstance(raw, str):
        return raw
    return ""


def _dig2(d: dict | None, key1: str, key2: str):
    """Two-level safe get; returns None when any level is absent or non-dict."""
    if not isinstance(d, dict):
        return None
    inner = d.get(key1)
    if not isinstance(inner, dict):
        return None
    return inner.get(key2)


def _extract_comments(fields: dict) -> list[HarvestedComment]:
    raw = fields.get("comment")
    if not isinstance(raw, dict):
        return []
    result: list[HarvestedComment] = []
    for c in raw.get("comments") or []:
        result.append(HarvestedComment(
            body=_adf_or_str(c.get("body")),
            author=_dig2(c, "author", "displayName"),
            created_at=parse_harvester_dt(c.get("created")),
            upstream_id=c.get("id"),
        ))
    return result


def _issue_status(fields: dict) -> tuple[str | None, str | None]:
    """Return (state_norm, state_name) from a JIRA issue fields dict."""
    status = fields.get("status") or {}
    key = (_dig2(status, "statusCategory", "key") or "").lower()
    return _JIRA_STATUS_NORM.get(key), status.get("name")


def _issue_to_harvested(issue: dict) -> HarvestedTicket:
    """Map one JIRA REST issue JSON object into a HarvestedTicket."""
    fields = issue.get("fields") or {}
    state_norm, state_name = _issue_status(fields)
    return HarvestedTicket(
        source=SOURCE,
        ticket_id=issue["key"],
        title=fields.get("summary") or "",
        description=_adf_or_str(fields.get("description")),
        url=issue.get("self"),
        comments=_extract_comments(fields),
        raw_meta={"jira_id": issue.get("id")},
        state_norm=state_norm,
        state_name=state_name,
        assignee=_dig2(fields, "assignee", "displayName"),
        reporter=_dig2(fields, "reporter", "displayName"),
        priority_name=_dig2(fields, "priority", "name"),
        issue_type=_dig2(fields, "issuetype", "name"),
        ticket_labels=list(fields.get("labels") or []),
        ticket_created_at=parse_harvester_dt(fields.get("created")),
        ticket_updated_at=parse_harvester_dt(fields.get("updated")),
        ticket_closed_at=parse_harvester_dt(fields.get("resolutiondate")),
    )


# ---------------------------------------------------------------------------
# Client protocol + real REST implementation
# ---------------------------------------------------------------------------


class JiraRateLimitError(RuntimeError):
    """Raised when JIRA returns HTTP 429 after all retries are exhausted."""


class JiraClient(Protocol):
    """The surface `sync_ticket` / `sync_recent` depend on.

    Implemented for real by `JiraRestClient` and as a canned-response fake
    in unit tests.  `fetch_recent` is a generator so the caller can process
    tickets as they arrive (interleaved with per-page API fetches).
    """

    def fetch_ticket(self, issue_key: str) -> HarvestedTicket | None:
        """Fetch one ticket by issue key (e.g. 'PROJ-123'); None if not found."""
        ...

    def fetch_recent(
        self, since: datetime, *, next_page_token: str | None = None
    ) -> Iterator[HarvestedTicket]:
        """Yield all tickets updated at/after `since`, resuming from cursor if given."""
        ...

    def fetch_pages(
        self, since: datetime, *, next_page_token: str | None = None
    ) -> Iterator[tuple[list[HarvestedTicket], str | None]]:
        """Yield (tickets, next_cursor) per page; next_cursor is None on the last page."""
        ...


class JiraRestClient:
    """Real `JiraClient` backed by JIRA Cloud's REST API v3 over httpx.

    Authenticates via HTTP Basic auth (email + API token).
    Rate-limits to `JIRA_MAX_RPS` req/sec via `RateLimiter`.
    Retries on HTTP 429 with exponential backoff; raises `JiraRateLimitError`
    after `max_retries` attempts.

    `fetch_recent` is a **generator** — it yields tickets from the current
    page, then fetches the next page when the caller resumes the generator.
    The embedding work for each ticket creates a natural pause between pages.

    Unit tests do NOT construct this — they pass a FakeJiraClient.
    """

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        project_keys: list[str] | None = None,
        rate_limiter: RateLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        credentials = f"{email}:{api_token}".encode("utf-8")
        auth_header = "Basic " + base64.b64encode(credentials).decode("ascii")

        self._project_keys: list[str] = project_keys or []
        self._rate_limiter = rate_limiter or RateLimiter(
            max_calls=JIRA_MAX_RPS,
            period_s=JIRA_RATE_PERIOD_S,
        )
        self._max_retries = max_retries
        self._sleep = sleep
        # Auth headers are always applied here regardless of whether a custom
        # transport (e.g. MockTransport in tests) is injected.  This keeps auth
        # correctness testable: pass transport=httpx.MockTransport(handler) and
        # the handler receives the real Authorization header.
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Rate-limited HTTP request; retries on 429; raises on other HTTP errors."""
        attempt = 0
        while True:
            self._rate_limiter.acquire()
            resp = self._http.request(method, path, **kwargs)
            if resp.status_code == 429:
                attempt += 1
                if attempt >= self._max_retries:
                    raise JiraRateLimitError(
                        f"JIRA rate limited (HTTP 429) after {self._max_retries} retries"
                    )
                self._sleep(2 ** (attempt - 1))
                continue
            resp.raise_for_status()
            return resp.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json=body)

    def fetch_ticket(self, issue_key: str) -> HarvestedTicket | None:
        try:
            payload = self._get(
                f"/rest/api/3/issue/{issue_key}",
                # GET endpoint takes a comma-separated string, not an array.
                {"fields": ",".join(_ISSUE_FIELDS)},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return _issue_to_harvested(payload)

    def fetch_pages(
        self, since: datetime, *, next_page_token: str | None = None
    ) -> Iterator[tuple[list[HarvestedTicket], str | None]]:
        """Yield (tickets_for_page, next_cursor) per page.

        Uses POST /rest/api/3/search/jql with cursor-based pagination
        (Atlassian removed GET /rest/api/3/search in 2026, changelog CHANGE-2046).
        next_cursor is None on the last page.

        Generator: fetches the next page only after the caller has consumed
        the current page, interleaving HTTP calls with processing work.
        """
        since_utc = since.astimezone(timezone.utc) if since.tzinfo else since.replace(tzinfo=timezone.utc)
        jql = f'updated >= "{since_utc.strftime("%Y-%m-%d %H:%M")} +0000"'
        if self._project_keys:
            projects = ", ".join(f'"{k}"' for k in self._project_keys)
            jql = f"project IN ({projects}) AND " + jql

        while True:
            body: dict = {
                "jql": jql,
                "maxResults": JIRA_BATCH_SIZE,
                "fields": _ISSUE_FIELDS,
            }
            if next_page_token is not None:
                body["nextPageToken"] = next_page_token
            page = self._post("/rest/api/3/search/jql", body)
            issues = page.get("issues", [])
            tickets = [_issue_to_harvested(issue) for issue in issues]
            next_page_token = page.get("nextPageToken")
            yield tickets, next_page_token
            # `not issues` guards against a non-conforming server that returns
            # an empty page with a cursor; `next_page_token is None` is the normal
            # last-page signal.
            if not issues or next_page_token is None:
                break

    def fetch_recent(
        self, since: datetime, *, next_page_token: str | None = None
    ) -> Iterator[HarvestedTicket]:
        """Yield all tickets updated at/after `since`, resuming from cursor if given."""
        for tickets, _ in self.fetch_pages(since, next_page_token=next_page_token):
            yield from tickets


# ---------------------------------------------------------------------------
# Sync orchestration (injection-driven; unit-tested with fakes)
# ---------------------------------------------------------------------------


def _write_checkpoint(
    path: Path, since: datetime, next_page_token: str | None, project_keys: list[str]
) -> None:
    """Atomically write a checkpoint (write tmp + rename, crash-safe).

    `next_page_token` is the cursor returned by JIRA for the NEXT page to fetch.
    None means all pages have been fetched (stored so mismatched checkpoints fail
    cleanly rather than silently resuming at the wrong offset).
    """
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"since": since.isoformat(), "next_page_token": next_page_token, "project_keys": project_keys})
    )
    tmp.rename(path)


def sync_ticket(
    identifier: str,
    *,
    client: JiraClient,
    conn: psycopg.Connection,
    embedder: Embedder,
    token_counter: Callable[[str], int] = _DEFAULT_TOKEN_COUNTER,
) -> int:
    """Full re-fetch + replace for one JIRA ticket. Returns rows written.

    Returns 0 if the ticket is not found upstream — deleted or inaccessible
    tickets are not an error; the harvester simply has nothing to index.
    """
    ticket = client.fetch_ticket(identifier)
    if ticket is None:
        return 0
    return ingest_ticket(ticket, conn=conn, embedder=embedder, token_counter=token_counter)


def sync_recent(
    since: datetime,
    *,
    client: JiraClient,
    conn: psycopg.Connection,
    embedder: Embedder,
    token_counter: Callable[[str], int] = _DEFAULT_TOKEN_COUNTER,
    checkpoint_path: Path | None = None,
    project_keys: list[str] | None = None,
) -> int:
    """Batch catch-up: re-index every ticket updated at/after `since`.

    Returns the total chunk rows written across all tickets.

    `checkpoint_path` enables crash-safe resume. After each page is committed,
    a checkpoint file is written atomically recording the cursor for the next
    page. On re-run with the same `since` and `project_keys`, the cursor is
    read and `fetch_pages` resumes from that page. The checkpoint is deleted on
    clean completion.

    If no checkpoint exists, or the checkpoint's `since` or `project_keys`
    don't match the current run, processing starts from the beginning.
    Old-format checkpoints (with `start_at` but no `next_page_token`) are
    discarded and the run restarts from the beginning.
    """
    cp: Path | None = Path(checkpoint_path) if checkpoint_path is not None else None
    effective_keys: list[str] = project_keys or []

    # Resolve resume cursor from an existing checkpoint.
    initial_cursor: str | None = None
    if cp is not None and cp.exists():
        try:
            saved = json.loads(cp.read_text())
            if (
                saved.get("since") == since.isoformat()
                and saved.get("project_keys") == effective_keys
                and "next_page_token" in saved  # reject old start_at-format checkpoints
            ):
                initial_cursor = saved.get("next_page_token")  # may be None (start fresh)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass  # corrupt / unreadable checkpoint — start fresh

    total = 0
    for page_tickets, next_cursor in client.fetch_pages(since, next_page_token=initial_cursor):
        for ticket in page_tickets:
            total += ingest_ticket(ticket, conn=conn, embedder=embedder, token_counter=token_counter)
        if cp is not None:
            _write_checkpoint(cp, since, next_cursor, effective_keys)

    # Clean completion — remove checkpoint so next run starts from scratch.
    if cp is not None:
        cp.unlink(missing_ok=True)

    return total


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def resolve_jira_credentials(
    config_path: str = HARVESTER_CONFIG_PATH,
) -> tuple[str | None, str | None, str | None]:
    """Resolve (email, api_token, base_url) — env vars first, then .harvester.toml.

    Returns a 3-tuple; any element is None if not found from either source.
    """
    email = os.environ.get(JIRA_EMAIL_ENV)
    token = os.environ.get(JIRA_API_TOKEN_ENV)
    base_url = os.environ.get(JIRA_BASE_URL_ENV)

    if email and token and base_url:
        return email, token, base_url

    jira_conf = (load_harvester_conf(config_path).get("jira") or {})
    return (
        email or jira_conf.get("email") or None,
        token or jira_conf.get("api_token") or None,
        base_url or jira_conf.get("base_url") or None,
    )


def _resolve_project_keys(
    config_path: str | None = None,
    *,
    cwd: str | None = None,
) -> list[str]:
    """Resolve the JIRA project filter.  Priority (first match wins):

    1. ``JIRA_PROJECT_KEYS`` env var (comma-separated, e.g. ``"PLTF,FOO"``).
    2. ``prefix`` from ``.project-conf.toml`` in *cwd* (auto-derive from the
       project the caller is working in).
    3. ``project_keys`` from ``.harvester.toml`` ``[jira]`` section.
    4. Empty list — harvest all projects with no project filter.

    ``cwd`` is injected by unit tests; production callers leave it ``None``
    so the current process working directory is used.
    """
    def split_csv(s: str | list) -> list[str]:
        items = s.split(",") if isinstance(s, str) else s
        return [k.strip() for k in items if k.strip()]

    env_val = os.environ.get("JIRA_PROJECT_KEYS", "")
    if env_val:
        return split_csv(env_val)
    prefix = read_project_conf_prefix(cwd)
    if prefix:
        return [prefix]
    keys = (load_harvester_conf(config_path).get("jira") or {}).get("project_keys") or []
    if not isinstance(keys, (str, list)):
        raise ValueError(
            f"[jira] project_keys in .harvester.toml must be a string or list, "
            f"got {type(keys).__name__!r} ({keys!r})"
        )
    return split_csv(keys)


def _build_real_client(project_keys: list[str] | None = None) -> JiraRestClient:
    email, token, base_url = resolve_jira_credentials()
    resolved_keys = project_keys if project_keys is not None else _resolve_project_keys()
    missing = [
        name
        for name, val in [
            (JIRA_EMAIL_ENV, email),
            (JIRA_API_TOKEN_ENV, token),
            (JIRA_BASE_URL_ENV, base_url),
        ]
        if not val
    ]
    if missing:
        raise SystemExit(
            "Missing JIRA credentials: " + ", ".join(missing) + "\n"
            "Set them as environment variables or in .harvester.toml [jira]:\n"
            "  [jira]\n"
            '  email     = "you@example.com"\n'
            '  api_token = "your-api-token"   # JIRA Cloud → Account settings → API tokens\n'
            '  base_url  = "https://yourorg.atlassian.net"\n'
            "See design/ticket-rag.md § Harvester credentials for details."
        )
    return JiraRestClient(
        base_url=base_url, email=email, api_token=token, project_keys=resolved_keys
    )


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
        """JIRA harvester for the ticket-rag service."""

    @cli.command("sync-ticket")
    @click.argument("issue_key")
    def sync_ticket_cmd(issue_key: str) -> None:
        """Re-index a single JIRA ticket, e.g. `sync-ticket PROJ-123`."""
        from rag_service.embed import get_embedder

        client = _build_real_client()
        conn = open_conn()
        try:
            n = sync_ticket(
                issue_key, client=client, conn=conn, embedder=get_embedder()
            )
        finally:
            conn.close()
        click.echo(f"{issue_key}: wrote {n} chunk row(s)")

    @cli.command("sync-recent")
    @click.argument("since")
    @click.option(
        "--project",
        "project_keys",
        multiple=True,
        help="Restrict to this JIRA project key. May be repeated: --project PLTF --project FOO. "
        "Overrides JIRA_PROJECT_KEYS env var and .harvester.toml project_keys.",
    )
    @click.option(
        "--checkpoint",
        "checkpoint_path",
        default=None,
        type=click.Path(path_type=Path),
        help="Path to checkpoint file for crash-safe resume. "
        "If the file exists from a prior run, processing resumes from where it left off.",
    )
    def sync_recent_cmd(
        since: str, project_keys: tuple[str, ...], checkpoint_path: Path | None
    ) -> None:
        """Re-index every JIRA ticket updated at/after an ISO-8601 timestamp.

        Example: sync-recent 2024-01-01 --project PLTF --checkpoint /tmp/jira-sync.json
        """
        from rag_service.embed import get_embedder

        since_dt = parse_harvester_dt(since)
        # Normalise to UTC-aware so checkpoint's since.isoformat() is stable
        # across re-runs regardless of whether the user passes "2024-01-01" or
        # "2024-01-01T00:00:00+00:00".  Without this, a date-only input stores
        # "2024-01-01T00:00:00" in the checkpoint while a TZ-aware re-run stores
        # "2024-01-01T00:00:00+00:00" — mismatch silently discards the checkpoint.
        if since_dt is not None and since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
        # Filter empty tokens so --project "" doesn't produce a spurious empty key.
        # Fall back to config/env resolution when no --project flags were given.
        cli_keys = [k for k in project_keys if k]
        effective_keys = cli_keys if cli_keys else _resolve_project_keys()
        client = _build_real_client(project_keys=effective_keys or None)
        conn = open_conn()
        try:
            n = sync_recent(
                since_dt,
                client=client,
                conn=conn,
                embedder=get_embedder(),
                checkpoint_path=checkpoint_path,
                project_keys=effective_keys,
            )
        finally:
            conn.close()
        click.echo(f"since {since}: wrote {n} chunk row(s)")

    if __name__ == "__main__":  # pragma: no cover
        cli()
