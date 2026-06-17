# rag-service

Python + FastAPI service that indexes tickets, code, and commits into a local Postgres instance so the slopstop plugin can answer questions like "what tickets are related to this symbol?" and "which functions did BILL-42 touch?".

The service runs inside a single container that ships Postgres 18 + pgvector (dense vector search) + Apache AGE (Cypher property-graph queries) + two BGE models baked in. Everything listens on `127.0.0.1` only — trust auth, no TLS, no auth layer. It is intentionally single-user and localhost-only.

## Layout

```
rag-service/
├── rag_service/
│   ├── main.py              — FastAPI app, endpoint definitions
│   ├── models.py            — Pydantic request/response models
│   ├── db.py                — Postgres connection, schema helpers
│   ├── embed.py             — bge-m3 embedding wrapper
│   ├── rerank.py            — bge-reranker-v2-m3 cross-encoder
│   ├── search.py            — dense kNN + optional rerank pipeline
│   ├── query_preprocessor.py — query normalization before embedding
│   ├── harvesters/
│   │   ├── _common.py       — HarvestedTicket, ChunkRow, ingestion spine
│   │   ├── linear.py        — Linear GraphQL harvester
│   │   ├── jira.py          — JIRA Cloud REST v3 harvester
│   │   └── github.py        — GitHub GraphQL v4 harvester
│   └── code_graph/
│       ├── schema.py        — vertex/edge label + property constants
│       ├── ingest.py        — SCIP index → AGE Cypher MERGE statements
│       ├── query.py         — callers / blast-radius / ticket-code Cypher builders
│       └── commit_ingest.py — commit provenance → TOUCHES edges
├── scripts/
│   ├── harvest_range.py     — bulk-harvest a ticket range (e.g. LOU-1..100)
│   ├── ingest_commits.py    — mine git log and POST to /code-graph/ingest-commits
│   └── dump_tickets.py      — fetch tickets to stdout JSON (no ingestion, for analysis)
├── tests/                   — pytest unit tests (no Docker, no model weights)
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

## Quick start

```bash
make rag-build       # build slopstop-rag:latest (~5.7 GB, models baked in)
make rag-dev-start   # start persistent dev container (port 7777, pgdata/ on disk)
curl http://127.0.0.1:7777/healthz   # → {"postgres":"ok","schema":"ok"}

make rag-dev-stop    # stop (data in pgdata/ survives)
make rag-dev-status  # check container state
```

The first build is slow — it compiles Apache AGE and downloads the BGE models. Subsequent builds reuse the layer cache.

## API

Base URL: `http://127.0.0.1:7777`

### Ticket search

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Liveness + readiness probe. Returns `{"postgres":"ok","schema":"ok"}` (200) or degraded state (503). |
| `POST` | `/search` | Dense kNN retrieval over `ticket_chunks` with optional cross-encoder rerank. |
| `POST` | `/search_note` | Record a query string to `pgdata/search_notes/` for offline debugging (no retrieval). |

**POST /search** request body:

```json
{
  "project": "LOU",
  "query": "authentication token expiry",
  "k": 10,
  "rerank": true,
  "filters": {
    "source": ["linear", "jira"],
    "kind": ["description", "comment"],
    "state_norm": "open",
    "updated_after": "2025-01-01"
  }
}
```

`filters` fields: `source` (linear/jira/github), `provenance` (upstream/local), `kind` (description/comment/local-finding/docstring/commit_message), `ticket_id`, `project`, `assignee`, `state_norm` (open/in_progress/done/canceled), `priority_max` (0–4), `labels`, `created_after`, `updated_after`.

### Code graph

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/code-graph/ingest` | Ingest a SCIP JSON index into the AGE knowledge graph. |
| `GET` | `/code-graph/repo/{repo_id}` | Return `last_indexed_sha` for a repository. |
| `POST` | `/code-graph/context` | Return ticket IDs linked to a list of SCIP monikers via TOUCHES edges. |
| `POST` | `/code-graph/callers` | Direct callers of a moniker (CALLS edge). |
| `POST` | `/code-graph/implementors` | Functions/types implementing an interface (IMPLEMENTS edge). |
| `POST` | `/code-graph/blast-radius` | Transitive callers up to N hops (CALLS\*1..depth). |
| `POST` | `/code-graph/ticket-code` | Functions touched by commits referencing a ticket ID. |
| `POST` | `/code-graph/ingest-commits` | Ingest commit provenance (TOUCHES edges from git diffs). |

## Harvesters

All three harvesters normalize into a common `HarvestedTicket` shape and feed through the same chunking + embedding + DB pipeline in `harvesters/_common.py`.

### Linear

```bash
# Harvest one ticket
python3 -m rag_service.harvesters.linear sync-ticket LOU-42

# Harvest everything updated in the last 7 days
python3 -m rag_service.harvesters.linear sync-recent "$(date -v-7d +%Y-%m-%d)"
```

Credential: `LINEAR_API_KEY` env var or `[linear] api_key` in `.harvester.toml`.

### JIRA

```bash
python3 -m rag_service.harvesters.jira sync-ticket PROJ-123
python3 -m rag_service.harvesters.jira sync-recent 2025-01-01 --project PLTF --checkpoint /tmp/jira.json
```

Credentials: `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_BASE_URL` env vars or `[jira]` in `.harvester.toml`. `--project` (repeatable) restricts the JQL to specific project keys; falls back to `JIRA_PROJECT_KEYS` env var or `[jira] project_keys` in the config file. The `--checkpoint` flag enables crash-safe resume.

JIRA ticket bodies are Atlassian Document Format (ADF); `adf_to_text()` converts them to plain text before chunking.

### GitHub

```bash
python3 -m rag_service.harvesters.github sync-ticket 42
python3 -m rag_service.harvesters.github sync-recent 2025-01-01
```

Credentials: `GITHUB_TOKEN` env var or `[github] token` + `[github] repo = "owner/repo"` in `.harvester.toml`.

### Bulk scripts

```bash
# Harvest LOU-1 through LOU-100 (builds client/conn/embedder once)
cd rag-service
python3 -m scripts.harvest_range LOU 1 100

# Mine git commits for BILL-* references and POST to the running container
python3 -m scripts.ingest_commits --repo iansmith/slopstop --prefix BILL \
  --since-sha abc1234 --rag-url http://127.0.0.1:7777
```

## Code graph

The code graph stores the symbol graph from SCIP language indexes in Apache AGE (a Cypher property-graph layer on top of Postgres). Once indexed, the plugin can answer questions like "who calls this function?" and "what tickets touched this code path?".

**Vertex types:** `Package`, `File`, `Type`, `Function`, `Field`, `External`, `Commit`, `Repo`

**Edge types:** `CONTAINS`, `DEFINES`, `CALLS`, `IMPLEMENTS`, `REFERENCES`, `TOUCHES` (commit → file/function, carries `change_type` and `hunks`)

Ingest a SCIP index (typically produced by the SCIP CLI or `scip-go`, `scip-typescript`, etc.):

```bash
# From the host — container must be running
scip index --output index.scip
scip convert --from index.scip --to index.json
curl -X POST http://127.0.0.1:7777/code-graph/ingest \
  -H "Content-Type: application/json" \
  -d @index.json
```

Ingest commit provenance separately (run on the host where git history lives):

```bash
python3 -m scripts.ingest_commits --repo owner/repo --prefix TICKET
```

## Configuration

Copy `.harvester.toml.example` to `.harvester.toml` (git-ignored) and fill in credentials:

```toml
[linear]
api_key = "lin_api_..."

[jira]
email       = "you@example.com"
api_token   = "ATATT..."
base_url    = "https://yourorg.atlassian.net"
project_keys = ["PLTF", "FOO"]   # optional project filter

[github]
token = "ghp_..."
repo  = "owner/repo"
```

Environment variables take precedence over the TOML file:

| Variable | Purpose |
|----------|---------|
| `RAG_SERVICE_PG_DSN` | Postgres DSN (default: `dbname=postgres user=postgres host=localhost connect_timeout=1`) |
| `RAG_SERVICE_BGE_M3_PATH` | bge-m3 model directory (default: `/models/bge-m3` in container) |
| `LINEAR_API_KEY` | Linear API key |
| `JIRA_EMAIL` / `JIRA_API_TOKEN` / `JIRA_BASE_URL` | JIRA Cloud auth |
| `JIRA_PROJECT_KEYS` | Comma-separated JIRA project key filter (e.g. `PLTF,FOO`) |
| `GITHUB_TOKEN` | GitHub personal access token |

## Testing

Unit tests run outside Docker — no postgres, no model weights, no network. All external dependencies are injected and overridden via `app.dependency_overrides`.

```bash
cd rag-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt -r requirements.txt
pip install -e .
.venv/bin/python3 -m pytest          # 430 tests, ~0.4s
```

Docker-level end-to-end smoke tests (`verify-bill17.sh`, etc.) are the integration gate and require a running container. They live at the repo root alongside their ticket numbers.

**Before writing any new code in this directory, read [`design/rag-service-testing.md`](../design/rag-service-testing.md).** It defines the three testing layers, the code-shape rules (pure Layer-1 functions, FastAPI Depends wiring, no globals), and the anti-patterns to avoid.

## Container details

| Component | Version |
|-----------|---------|
| Postgres | 18 |
| pgvector | 0.8.2 |
| Apache AGE | 1.7.0-rc0 |
| Python | 3.12 |
| bge-m3 / bge-reranker-v2-m3 | baked in at build time |
| Image size | ~5.7 GB (models ~4.5 GB) |
| Peak build disk | ~12–13 GB from scratch |

The image carries no baked-in cluster data. Postgres initializes on first start and writes into the host-mounted `pgdata/` directory at the repo root. Trust auth is enabled on `127.0.0.1` only — do not expose this container to untrusted networks.

## See also

- [`design/ticket-rag.md`](../design/ticket-rag.md) — full architecture and endpoint contracts
- [`design/rag-service-testing.md`](../design/rag-service-testing.md) — testing strategy and code-shape rules
- [`docker/postgres-pgvector/README.md`](../docker/postgres-pgvector/README.md) — Dockerfile walkthrough and build notes
- [BILL-28](https://github.com/iansmith/slopstop/issues/28) — application-layer umbrella ticket
