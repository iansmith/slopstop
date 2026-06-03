# slopstop — cold start guide

**Audience:** A developer setting up slopstop from scratch on a new machine or a new project.

**What you get:** Ticket-anchored development with Claude Code — plan → code → PR → merge, driven by Linear, JIRA, or GitHub Issues, with a local semantic-search RAG service over your ticket corpus and (in progress) a code knowledge graph.

---

## Table of contents

1. [System prerequisites](#1-system-prerequisites)
2. [Docker and the rag container](#2-docker-and-the-rag-container)
3. [Installing slopstop itself](#3-installing-slopstop-itself)
4. [MCP servers required](#4-mcp-servers-required)
5. [Config files — what lives where](#5-config-files--what-lives-where)
6. [Per-project tool paths (SCIP / code graph)](#6-per-project-tool-paths-scip--code-graph)
7. [Initializing a new project](#7-initializing-a-new-project)
8. [Known gaps and migration items](#8-known-gaps-and-migration-items)

---

## 1. System prerequisites

These must be installed on your host machine before anything else.

| Tool | Why | Min version | Notes |
|---|---|---|---|
| **Docker Desktop** (or Docker Engine) | The entire rag service — Postgres 18, pgvector, Apache AGE, bge-m3 encoder, reranker — runs in a single container | 24+ | macOS: Docker Desktop ≥ 4.30; Linux: Docker Engine ≥ 24 |
| **Git** | Everything | 2.38+ | `git worktree` support required |
| **Claude Code CLI** | The host environment slopstop runs inside | latest | `npm install -g @anthropic-ai/claude-code` |
| **`gh` CLI** (GitHub only, see §8) | Issue/PR management *(current dependency; being migrated to MCP)* | 2.40+ | `brew install gh` / `apt install gh`; authenticate: `gh auth login` |

**Optional, install only for the features you use:**

| Tool | Why | Install |
|---|---|---|
| **Go 1.21+** | `scip-go` indexer for Go repos (code graph) | https://go.dev/dl/ |
| **Node.js 18+ / npm** | `scip-typescript` + `scip-python` indexers | https://nodejs.org or via nvm/mise |
| **Python 3.11+** | Running the rag-service outside Docker (tests, dev) | https://python.org or pyenv |

> **nvm users:** nvm manages Node via shell functions, not binaries. When configuring tool paths (§6), use the full resolved path to the binary (e.g. `~/.nvm/versions/node/v20/bin/scip-typescript`), not `nvm exec`.

---

## 2. Docker and the rag container

The rag container is the biggest prerequisite. It bundles:

- **Postgres 18** with **pgvector 0.8.2** (semantic search) and **Apache AGE 1.7.0** (code graph)
- **bge-m3** encoder (~3 GB) and **bge-reranker-v2-m3** reranker (~1.5 GB), baked in at build time
- **FastAPI** app exposing `/healthz`, `/search`, and (in progress) `/code-graph/ingest`

### One-time: fetch the model weights

The weights are too large to download inside the Docker build (Docker Desktop's VM NAT stalls the HuggingFace Xet protocol). Fetch them on the host first:

```bash
cd ~/slopstop    # or wherever you cloned the repo
bash docker/postgres-pgvector/fetch-models.sh
```

This downloads ~4.5 GB into `docker/postgres-pgvector/models/`. The directory is gitignored. **This step is required before the first build.**

### Build the image

```bash
make rag-build
# Tags as slopstop-rag:<git-sha> and slopstop-rag:latest
# Expect ~6 GB image; ~12 GB peak disk during build; ~3 minutes on M-series Mac
```

### Run the container

```bash
docker run -d \
  --name slopstop-rag \
  -v "$PWD/pgdata:/var/lib/postgresql" \
  -p 127.0.0.1:5432:5432 \
  -p 127.0.0.1:7777:7777 \
  slopstop-rag:latest
```

Or via the Makefile shorthand: `make rag-dev-start`

The container exposes **only on `127.0.0.1`** (localhost). Do not publish on `0.0.0.0` — trust auth is on.

### Verify it's running

```bash
docker exec slopstop-rag python3 -c \
  "import urllib.request, json; r=urllib.request.urlopen('http://127.0.0.1:7777/healthz'); print(json.loads(r.read()))"
# Expect: {"postgres": "ok", "schema": "ok"}
```

### Data directory

The container mounts `pgdata/` from the repo root. The first run initializes a Postgres cluster under `pgdata/18/docker/`. Subsequent runs reuse the cluster and re-apply schema idempotently. Wipe `pgdata/18/` to reset to a clean database.

---

## 3. Installing slopstop itself

### Claude Code (CLI) — recommended

```bash
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Skills are then available as `/slopstop:start`, `/slopstop:plan`, `/slopstop:pr`, etc.

### Claude Desktop (no `/plugin` support yet)

```bash
curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/master/install-for-claude-desktop.sh | bash
```

Skills install as `/slopstop-start`, `/slopstop-plan`, etc. (un-namespaced).

---

## 4. MCP servers required

Claude Code reads MCP server definitions from `.mcp.json` in the project root. slopstop ships one; others must be configured manually.

### 4a. slopstop-rag (ships with the repo)

Exposes `search_tickets` and `rag_health` tools to Claude Code. Already declared in `.mcp.json` at the slopstop repo root:

```json
{
  "mcpServers": {
    "slopstop-rag": {
      "type": "stdio",
      "command": "python3",
      "args": ["mcp-server/server.py"],
      "env": { "RAG_SERVICE_URL": "http://localhost:7777" }
    }
  }
}
```

No action needed if you cloned the repo. The rag container must be running for this server to be useful.

### 4b. GitHub MCP (for GitHub Issues projects)

**Current state:** The slopstop skills currently rely on the `gh` CLI for GitHub operations (see §8). The GitHub MCP is the intended future path.

To install the GitHub MCP plugin in Claude Code:

```bash
/plugin marketplace add claude-plugins-official
/plugin install github@claude-plugins-official
```

This provides `mcp__github__*` tools (issue read/write, PR management, etc.). When fully migrated, this will replace the `gh` CLI dependency.

**For now:** install `gh` AND the GitHub MCP. The skills use `gh`; the MCP is available for direct use in Claude conversations.

### 4c. Linear MCP (for Linear projects)

The Linear harvester uses the Linear API directly via a personal API key — no MCP required for harvesting. A Linear MCP server would be needed if slopstop skills call Linear ticket operations interactively. Currently not required.

### 4d. JIRA MCP (for JIRA projects)

Not yet implemented. See BILL-38 (JIRA harvester). When built, will require the Atlassian MCP server.

---

## 5. Config files — what lives where

### Committed (project-level, shared with the team)

**`.project-conf.toml`** — in the root of each project that uses slopstop:

```toml
# Required
system = "github"          # or "linear" or "jira"
key    = "owner/repo"      # GitHub: "owner/repo"; Linear: team key; JIRA: project key
prefix = "BILL"            # ticket prefix (BILL-NN, LOU-NN, etc.)

# GitHub Issues only: workflow shape
[status_labels]
in_progress = "status:in-progress"
# in_review = "status:in-review"   # uncomment for 4-state workflow

# Code graph (SCIP indexing, in progress — see BILL-53 umbrella)
[code-graph]
languages   = ["go"]                          # which indexers to run
module_root = "."                             # where go.mod / package.json lives
skip        = ["vendor/", "*.pb.go"]         # patterns to exclude

# Per-project tool overrides — only needed when a specific version is required
# Leave absent to use the global defaults in ~/.slopstop/config.toml
[code-graph.tools]
# scip_python = "/home/you/.nvm/versions/node/v18/bin/scip-python"
```

### Not committed (machine-local, gitignored)

**`.harvester.toml`** — API credentials for ticket harvesters. Copy from `.harvester.toml.example`:

```toml
[linear]
api_key = "lin_api_..."    # Read-only personal API key from Linear settings

# [jira]
# email     = "you@example.com"
# api_token = "..."
# base_url  = "https://your-site.atlassian.net"
```

**`~/.slopstop/config.toml`** — user-level defaults for tool paths (created by `slopstop-install-hooks` as a template; you fill in the values):

```toml
# Global fallback tool paths. Per-project overrides go in .project-conf.toml [code-graph.tools]

[tools]
# go install github.com/scip-code/scip-go/cmd/scip-go@latest
scip_go = ""

# npm install -g @sourcegraph/scip-typescript
scip_typescript = ""

# npm install -g @sourcegraph/scip-python
scip_python = ""

[rag]
url = "http://localhost:7777"
```

---

## 6. Per-project tool paths (SCIP / code graph)

SCIP indexers are installed separately on the host (not inside the Docker container — they need access to the repo filesystem and language toolchains). Tool paths are **per-project** because different projects routinely target different Python or Node versions.

### Resolution order

1. **`.project-conf.toml` `[code-graph.tools]`** — project override (committed; only use when a specific version is required)
2. **`~/.slopstop/config.toml` `[tools]`** — user's machine defaults
3. **Fail with an actionable error** pointing to the install command

### Installing the SCIP indexers

```bash
# Go repos
go install github.com/scip-code/scip-go/cmd/scip-go@latest
# → ~/go/bin/scip-go

# TypeScript / JavaScript repos
npm install -g @sourcegraph/scip-typescript
# → <node-bin-dir>/scip-typescript

# Python repos
npm install -g @sourcegraph/scip-python
# → <node-bin-dir>/scip-python
```

> **Note on the scip-code org:** The Go repos (`scip-go`, `scip`) migrated from `sourcegraph` → `scip-code` in early 2026. This is a confirmed repo transfer, not a fork. The npm packages remain under `@sourcegraph`.

### Setting up auto-indexing on merge (in progress — BILL-59)

Once BILL-59 ships, run:

```bash
slopstop-install-hooks ~/my-project ~/other-project
```

This validates your `~/.slopstop/config.toml` tool paths and installs a `post-merge` hook in each repo that calls `slopstop-ingest` whenever you `git pull` a merge.

### Multi-repo projects with `go.work` / `replace` directives

If your Go project has `replace` directives pointing to sibling repos (e.g. `replace mazarin/textshape => ../mazzy/mazarin/textshape`), the indexer must run from a sibling worktree — not a `/tmp` clone — so the relative path resolves. `slopstop-install-hooks` handles this automatically by creating a sibling worktree at `~/project-scip-wt`.

---

## 7. Initializing a new project

### Step 0: Prerequisites checklist

- [ ] Docker running, rag image built (`make rag-build`), container up
- [ ] Claude Code installed and authenticated
- [ ] `gh` CLI installed and authenticated (`gh auth login`) — for GitHub projects
- [ ] GitHub MCP installed (`/plugin install github@claude-plugins-official`) — optional but recommended
- [ ] slopstop plugin installed

### Step 1: Create `.project-conf.toml`

In the root of the project repo:

```bash
cat > .project-conf.toml << 'EOF'
system = "github"
key    = "owner/repo"
prefix = "MYPREFIX"

[status_labels]
in_progress = "status:in-progress"
EOF
```

Commit this file.

### Step 2: Create the GitHub status labels

slopstop's 3-state workflow requires an `in-progress` label. Create it:

```bash
gh label create "status:in-progress" --color "0075ca" --description "Actively being worked on"
# Optional 4-state:
gh label create "status:in-review" --color "e4e669" --description "In review / QA"
```

### Step 3: Add `.mcp.json`

Copy or adapt from the slopstop repo's `.mcp.json`. At minimum:

```json
{
  "mcpServers": {
    "slopstop-rag": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/slopstop/mcp-server/server.py"],
      "env": { "RAG_SERVICE_URL": "http://localhost:7777" }
    }
  }
}
```

Commit `.mcp.json`. Claude Code picks it up automatically at session start.

### Step 4: Seed the RAG corpus

The semantic search tools are only useful once the rag container has ticket data. Harvest tickets for your project (requires the rag container to be running):

```bash
# Linear projects:
export LINEAR_API_KEY="lin_api_..."
docker exec -e LINEAR_API_KEY slopstop-rag python3 -m scripts.sync_recent

# GitHub Issues projects:
# Harvester not yet implemented — see BILL-32 (GitHub harvester)
```

### Step 5: Start your first ticket

```bash
cd ~/my-project
/slopstop:start MYPREFIX-1
```

This creates `~/.claude/ticket-active/MYPREFIX-1/` with `task_plan.md` and `findings.md`, marks the ticket in-progress on GitHub, and sets the context for subsequent `/slopstop:*` commands.

### Step 6 (optional): Set up code graph indexing

Install the SCIP indexers (§6), fill in `~/.slopstop/config.toml`, add `[code-graph]` to `.project-conf.toml`, then:

```bash
slopstop-install-hooks ~/my-project
```

This is optional for the ticket workflow; required only for the code knowledge graph features (BILL-53 umbrella, in progress).

---

## 8. Known gaps and migration items

These are current limitations you should be aware of before going all-in.

### `gh` CLI dependency (high priority)

**Current state:** The slopstop skills (`/slopstop:pr`, `/slopstop:merge`, `/slopstop:start`, etc.) use the `gh` CLI extensively for GitHub operations — creating PRs, managing issues, posting comments.

**Why this is a problem:** The `gh` CLI is a heavyweight, auth-separate dependency. The Anthropic-provided GitHub MCP plugin (`mcp__github__*`) provides the same operations without a separate CLI install and uses Claude Code's authentication context.

**What to do today:** Install both — `gh` CLI for the skills to function, GitHub MCP for direct use.

**Migration path:** The skills are being migrated to call the GitHub MCP backend when available. Track in `design/github-backend-primitives.md`.

### GitHub Issues harvester not yet built (BILL-32)

The Linear harvester (`sync_ticket`, `sync_recent`) is complete. A GitHub Issues harvester — so that GitHub-Issues-based projects can have their ticket corpus in the rag service — is not yet implemented. Without it, `/search_tickets` returns nothing for GitHub projects.

### Code knowledge graph in progress (BILL-53)

The Apache AGE graph DB substrate is built (BILL-52, merged). The SCIP ingestion pipeline (BILL-55), commit provenance (BILL-56), hybrid retrieval (BILL-57), and query surface (BILL-58) are all in design. The `[code-graph]` section in `.project-conf.toml` is forward-looking — it has no effect yet.

### `slopstop-ingest` CLI not yet built (BILL-59)

The `post-merge` hook infrastructure described in §6 does not exist yet. The `slopstop-install-hooks` command, `slopstop-ingest` binary, and `~/.slopstop/config.toml` are all planned but unimplemented. Manual SCIP indexing (run `scip-go index` by hand, pipe to the ingest endpoint) is the only path today.

### Image size (~6 GB)

The rag image bundles full fp32 model weights. Shrinking toward the ~3 GB target (fp16 weights, multi-stage Python build) is tracked in BILL-26 and is out of scope for the current release.

---

## Quick reference

```
~/.slopstop/config.toml        user-local: tool paths (gitignored)
.project-conf.toml             per-project: system, prefix, labels, code-graph langs (committed)
.harvester.toml                per-project: API credentials (gitignored)
.harvester.toml.example        template for .harvester.toml (committed)
.mcp.json                      MCP server declarations (committed)
pgdata/                        Postgres data directory — gitignored, host-mounted into container
docker/postgres-pgvector/models/   bge-m3 + reranker weights — gitignored, baked into image at build
```

```
make rag-build                 build the rag image (after fetch-models.sh)
make rag-dev-start             start the container (with LINEAR_API_KEY passthrough)
make rag-dev-stop              stop the container
bash docker/postgres-pgvector/fetch-models.sh   download model weights (one-time)
```
