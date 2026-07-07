# slopstop — cold start guide

**Audience:** A developer setting up slopstop from scratch on a new machine or a new project.

**What you get:** Ticket-anchored development with Claude Code — plan → code → PR → merge, driven by Linear, JIRA, or GitHub Issues.

---

## Table of contents

1. [System prerequisites](#1-system-prerequisites)
2. [Installing slopstop](#2-installing-slopstop)
3. [MCP servers required](#3-mcp-servers-required)
4. [Config files — what lives where](#4-config-files--what-lives-where)
5. [Per-project tool paths (SCIP / code graph)](#5-per-project-tool-paths-scip--code-graph)
6. [Initializing a new project](#6-initializing-a-new-project)
7. [Known gaps and migration items](#7-known-gaps-and-migration-items)

---

## 1. System prerequisites

These must be installed on your host machine before anything else.

| Tool | Why | Min version | Notes |
|---|---|---|---|
| **Git** | Everything | 2.38+ | `git worktree` support required |
| **Claude Code CLI** | The host environment slopstop runs inside | latest | `npm install -g @anthropic-ai/claude-code` |
| **`gh` CLI** (GitHub only) | Issue/PR management | 2.40+ | `brew install gh` / `apt install gh`; authenticate: `gh auth login` |

**Optional, install only for the features you use:**

| Tool | Why | Install |
|---|---|---|
| **Go 1.21+** | `scip-go` indexer for Go repos (code graph) | https://go.dev/dl/ |
| **Node.js 18+ / npm** | `scip-typescript` + `scip-python` indexers | https://nodejs.org or via nvm/mise |

> **nvm users:** nvm manages Node via shell functions, not binaries. When configuring tool paths (§5), use the full resolved path to the binary (e.g. `~/.nvm/versions/node/v20/bin/scip-typescript`), not `nvm exec`.

---

## 2. Installing slopstop

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

## 3. MCP servers required

Claude Code reads MCP server definitions from `.mcp.json` in the project root. The MCP servers below are installed as plugins and don't go in `.mcp.json`.

### 3a. GitHub MCP (for GitHub Issues projects)

**Current state (BILL-60 complete):** The slopstop skills now prefer the GitHub MCP for all issue and PR operations. `gh` CLI is a fallback and is only strictly required for precise CodeRabbit feedback polling.

Install the GitHub MCP plugin in Claude Code:

```bash
/plugin marketplace add claude-plugins-official
/plugin install github@claude-plugins-official
```

This provides `mcp__plugin_github_github__*` tools (issue read/write, PR create/merge, etc.) and is the primary backend. See §7 for the one remaining `gh` gap (remote branch deletion after MCP merge).

### 3b. Linear MCP (for Linear projects)

```bash
/plugin marketplace add claude-plugins-official
/plugin install linear@claude-plugins-official
```

### 3c. JIRA MCP (for JIRA projects)

Not yet implemented. See BILL-38 (JIRA harvester). When built, will require the Atlassian MCP server:

```bash
/plugin install atlassian@claude-plugins-official
```

---

## 4. Config files — what lives where

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

Commit this file.

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
```

---

## 5. Per-project tool paths (SCIP / code graph)

SCIP indexers are installed separately on the host. Tool paths are **per-project** because different projects routinely target different Python or Node versions.

### Resolution order

1. **`.project-conf.toml` `[code-graph.tools]`** — project override (committed; only use when a specific version is required)
2. **`~/.slopstop/config.toml` `[tools]`** — user's machine defaults
3. **Fail with an actionable error** pointing to the install command

### Installing the SCIP indexers

```bash
# Go repos (also needed for scip print --json conversion)
go install github.com/scip-code/scip-go/cmd/scip-go@latest
go install github.com/scip-code/scip/cmd/scip@latest
# → ~/go/bin/scip-go, ~/go/bin/scip

# TypeScript / JavaScript repos
npm install -g @sourcegraph/scip-typescript
# → <node-bin-dir>/scip-typescript

# Python repos
npm install -g @sourcegraph/scip-python
# → <node-bin-dir>/scip-python
```

> **Note on the scip-code org:** The Go repos (`scip-go`, `scip`) migrated from `sourcegraph` → `scip-code` in early 2026. This is a confirmed repo transfer, not a fork. The npm packages remain under `@sourcegraph`.

### Setting up auto-indexing on merge (in design — BILL-59)

Once BILL-59 ships, run:

```bash
slopstop-install-hooks ~/my-project ~/other-project
```

This validates your `~/.slopstop/config.toml` tool paths and installs a `post-merge` hook in each repo that calls `slopstop-ingest` whenever you `git pull` a merge.

### Multi-repo projects with `go.work` / `replace` directives

If your Go project has `replace` directives pointing to sibling repos, the indexer must run from a sibling worktree — not a `/tmp` clone — so the relative path resolves. `slopstop-install-hooks` handles this automatically by creating a sibling worktree at `~/project-scip-wt`.

---

## 6. Initializing a new project

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

### Step 3: Start your first ticket

```bash
cd ~/my-project
/slopstop:start MYPREFIX-1
```

This creates `~/.claude/ticket-active/MYPREFIX-1/` with `task_plan.md` and `findings.md`, marks the ticket in-progress on GitHub, and sets the context for subsequent `/slopstop:*` commands.

### Step 4 (optional): Set up code graph indexing

Install the SCIP indexers (§5), fill in `~/.slopstop/config.toml`, add `[code-graph]` to `.project-conf.toml`, then:

```bash
slopstop-install-hooks ~/my-project
```

This is optional for the ticket workflow; required only for the code knowledge graph features (BILL-53 umbrella, in progress).

---

### Step 5 (optional): Set up file-size pre-commit gate

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

**Opt-out pragma:** add this anywhere in a file to suppress the check for it:

```
// SLOPSTOP PRAGMA no-line-count-limit
```

Works in any comment syntax as long as the exact string
`SLOPSTOP PRAGMA no-line-count-limit` appears on a line. The script and the
PR-time NLOC check both honour it.

---

## 7. Known gaps and migration items

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

### Code knowledge graph in progress (BILL-53)

The SCIP ingestion pipeline (BILL-55), commit provenance (BILL-56), hybrid retrieval (BILL-57), and query surface (BILL-58) are all in design. The `[code-graph]` section in `.project-conf.toml` is forward-looking — it has no effect yet.

### `slopstop-ingest` CLI not yet built (BILL-59)

The `post-merge` hook infrastructure described in §5 does not exist yet. The `slopstop-install-hooks` command, `slopstop-ingest` binary, and `~/.slopstop/config.toml` are all planned but unimplemented. Manual SCIP indexing (run `scip-go index` by hand, pipe to the ingest endpoint) is the only path today.

### Workflow shape — 3-state or 4-state (JIRA / Linear)

slopstop's `:merge` skill is designed around two ticket-state shapes: **3-state** (`Todo → In Progress → Done`) and **4-state** (`Todo → In Progress → In Review → Done`). For GitHub Issues this is explicit — declared via `[status_labels]`. For JIRA and Linear the skill uses an advance-one-state algorithm (same-bucket preference first, then forward-progress). This works transparently with 3 or 4 states.

With more than 4 states the behaviour is technically correct (advances by one each time) but may require multiple `:merge` invocations to reach Done. If your team's JIRA or Linear board has a longer workflow, simplify the project to 3 or 4 states before onboarding, or extend `skills/merge/SKILL.md`'s state-selection logic with a custom state map. See the §6 callout for the three options.

---

## Quick reference

```
~/.slopstop/config.toml        user-local: tool paths (gitignored)
.project-conf.toml             per-project: system, prefix, labels, code-graph langs (committed)
.harvester.toml                per-project: API credentials (gitignored)
.harvester.toml.example        template for .harvester.toml (committed)
.mcp.json                      MCP server declarations (committed)
```
