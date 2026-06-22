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
| **Python 3.12+** | Running the rag-service outside Docker (tests, dev); host-side scripts (commit provenance ingest, BILL-56+) | https://python.org or pyenv — the `rag-service/.venv` is pinned to 3.12; earlier versions will fail |

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

**Current state (BILL-60 complete):** The slopstop skills now prefer the GitHub MCP for all issue and PR operations. `gh` CLI is a fallback and is only strictly required for precise CodeRabbit feedback polling.

Install the GitHub MCP plugin in Claude Code:

```bash
/plugin marketplace add claude-plugins-official
/plugin install github@claude-plugins-official
```

This provides `mcp__plugin_github_github__*` tools (issue read/write, PR create/merge, etc.) and is the primary backend. See §8 for the one remaining `gh` gap (remote branch deletion after MCP merge).

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

> **Workflow shape — plan this before you start.** slopstop's `:merge` skill advances tickets by exactly one state and is designed around two supported shapes:
>
> | Shape | States | When to use |
> |---|---|---|
> | **3-state** | `Todo → In Progress → Done` | Most GitHub Issues projects; simple JIRA/Linear boards |
> | **4-state** | `Todo → In Progress → In Review → Done` | When you have a separate review or QA gate before closing |
>
> **GitHub Issues:** the workflow shape is declared in `[status_labels]` (see Steps 1–2 below). No ticket-system configuration needed beyond the labels.
>
> **Linear / JIRA:** slopstop uses the board's existing states and advances by one step using a preference algorithm (same-bucket first, then forward-progress). This works cleanly when the board has 3 or 4 states. If your board has more — e.g. `Backlog → Todo → In Dev → Dev Review → QA → Staging → Done` — you have three options:
>
> 1. **Simplify the board** for this project: configure a 3- or 4-state workflow in JIRA/Linear (recommended). Other projects on the same board are unaffected.
> 2. **Accept multi-step merges:** run `/slopstop:merge` once per state advance and handle intervening review/QA work between invocations. Tickets still move correctly — just not in a single command.
> 3. **Extend the skill:** the advance-one logic lives in `skills/merge/SKILL.md` (the Linear and JIRA state-selection sections). Fork or modify to encode a custom state map.
>
> The GitHub Issues workflow is always exactly 3 or 4 states (binary OPEN/CLOSED + optional `in_review` label), so this tradeoff only applies to JIRA and Linear.

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

### Step 7 (optional): Set up file-size pre-commit gate

Refuse commits that include files over 1500 lines (total lines via `wc -l`,
including comments and blanks); warn (non-blocking) for files between
1000–1500 lines.

**Git hook registration** (applies to every `git commit` in this repo):

```bash
ln -sf ../../bin/pre-commit-file-size.sh .git/hooks/pre-commit
```

**Claude Code PreToolUse hook registration** (also blocks oversized files when
Claude Code runs `git commit` on your behalf):

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bin/pre-commit-file-size.sh"
          }
        ]
      }
    ]
  }
}
```

**Day-1 advisory:** `rag-service/rag_service/harvesters/_common.py` is
currently 1139 lines and will produce a WARNING message the first time it is
staged. This is expected and non-blocking (the script exits 0, so the commit
proceeds). The warning is a signal that the file should be split when the
opportunity arises, not a hard stop.

**Opt-out pragma:** add this anywhere in a file to suppress the check for it:

```
// SLOPSTOP PRAGMA no-line-count-limit
```

Works in any comment syntax as long as the exact string
`SLOPSTOP PRAGMA no-line-count-limit` appears on a line. The script and the
PR-time NLOC check both honour it.

---

## 8. Known gaps and migration items

These are current limitations you should be aware of before going all-in.

### `gh` CLI dependency (migration in progress — BILL-60)

**Current state (as of BILL-60):** The lifecycle skills (`:start`, `:merge`, `:archive`, `:document`) now use the GitHub MCP as the preferred backend for issue and PR operations, with `gh` CLI as a fallback. The PR skills (`:pr`, `:merge`) detect the MCP at runtime and use it when available.

**What remains:** `gh api` is still the preferred path for CodeRabbit feedback polling (Step 6 of `:pr`) because the MCP does not expose a raw API proxy. When `gh` is absent, `:pr` falls back to MCP-based comment polling, which is functional but less precise. See `design/github-backend-primitives.md` §CodeRabbit polling for details.

**What to do today:** Install the GitHub MCP — `gh` is now optional for all operations except CodeRabbit polling:

```bash
/plugin install github@claude-plugins-official
```

`gh` CLI is still recommended if you want precise CodeRabbit feedback polling:

```bash
brew install gh && gh auth login
```

**One remaining gap:** `merge_pull_request` (the MCP tool) does not auto-delete the remote branch on merge the way `gh pr merge --delete-branch` does. When using MCP-only (no `gh`), slopstop will warn and ask you to delete the remote branch manually from the GitHub UI. This will be resolved when the upstream MCP adds a `deleteBranch` parameter.

### GitHub Issues harvester not yet built (BILL-32)

The Linear harvester (`sync_ticket`, `sync_recent`) is complete. A GitHub Issues harvester — so that GitHub-Issues-based projects can have their ticket corpus in the rag service — is not yet implemented. Without it, `/search_tickets` returns nothing for GitHub projects.

### Code knowledge graph in progress (BILL-53)

The Apache AGE graph DB substrate is built (BILL-52, merged). The SCIP ingestion pipeline (BILL-55), commit provenance (BILL-56), hybrid retrieval (BILL-57), and query surface (BILL-58) are all in design. The `[code-graph]` section in `.project-conf.toml` is forward-looking — it has no effect yet.

### `slopstop-ingest` CLI not yet built (BILL-59)

The `post-merge` hook infrastructure described in §6 does not exist yet. The `slopstop-install-hooks` command, `slopstop-ingest` binary, and `~/.slopstop/config.toml` are all planned but unimplemented. Manual SCIP indexing (run `scip-go index` by hand, pipe to the ingest endpoint) is the only path today.

### Workflow shape — 3-state or 4-state (JIRA / Linear)

slopstop's `:merge` skill is designed around two ticket-state shapes: **3-state** (`Todo → In Progress → Done`) and **4-state** (`Todo → In Progress → In Review → Done`). For GitHub Issues this is explicit — declared via `[status_labels]`. For JIRA and Linear the skill uses an advance-one-state algorithm (same-bucket preference first, then forward-progress). This works transparently with 3 or 4 states.

With more than 4 states the behaviour is technically correct (advances by one each time) but may require multiple `:merge` invocations to reach Done. If your team's JIRA or Linear board has a longer workflow, simplify the project to 3 or 4 states before onboarding, or extend `skills/merge/SKILL.md`'s state-selection logic with a custom state map. See the §7 callout for the three options.

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
