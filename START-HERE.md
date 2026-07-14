# slopstop — setup guide

**Audience:** A developer setting up slopstop on a new machine or a new project.

**What you get:** Ticket-anchored, tests-first development with Claude Code —
plan → test → code → review → merge, driven by GitHub Issues, Linear, or JIRA.

> **Just want to try it?** The [15-minute quickstart](QUICKSTART.md) walks a real
> bug from ticket to merged PR in a throwaway example repo. Come here when you're
> ready to set slopstop up on a project of your own.
>
> **Want to understand the machinery?**
> [HOW-IT-WORKS.md](https://github.com/iansmith/slopstop-example/blob/master/HOW-IT-WORKS.md)
> explains the building blocks one primitive at a time.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Installing slopstop](#2-installing-slopstop)
3. [MCP servers](#3-mcp-servers)
4. [Config and layout — what lives where](#4-config-and-layout--what-lives-where)
5. [Initializing a new project](#5-initializing-a-new-project)
6. [Optional: file-size pre-commit gate](#6-optional-file-size-pre-commit-gate)

---

## 1. Prerequisites

On your `PATH`:

| Tool | Why | Notes |
|---|---|---|
| **Git** | Everything (worktrees included) | 2.38+ |
| **Claude Code CLI** | The host slopstop runs inside | `npm install -g @anthropic-ai/claude-code` |
| **`gh` CLI** (GitHub projects) | Issue/PR operations; precise CodeRabbit polling | `brew install gh` / `apt install gh`, then `gh auth login` |

For a GitHub project you also want the **GitHub MCP** (see §3) — with it, `gh` is
optional for everything except CodeRabbit feedback polling.

---

## 2. Installing slopstop

### Claude Code (CLI) — recommended

```bash
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Skills become available as `/slopstop:start`, `/slopstop:plan`, `/slopstop:pr`, etc.

### Claude Desktop (no `/plugin` support yet)

```bash
curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/master/install-for-claude-desktop.sh | bash
```

Skills install un-namespaced as `/slopstop-start`, `/slopstop-plan`, etc.

---

## 3. MCP servers

slopstop talks to your ticket system through an MCP server. Install the one that
matches your `system`:

| `system` | MCP | Install |
|---|---|---|
| `github` | GitHub MCP (recommended; `gh` CLI is the fallback) | `/plugin install github@claude-plugins-official` |
| `linear` | Linear MCP | `/plugin install linear@claude-plugins-official` |
| `jira` | Atlassian MCP | `/plugin install atlassian@claude-plugins-official` |

For GitHub, the lifecycle skills (`:start`, `:pr`, `:merge`, `:archive`,
`:document`) prefer the MCP and fall back to `gh` automatically. One known gap:
the MCP's merge tool does not delete the remote branch, so with MCP-only (no `gh`)
slopstop will ask you to delete the merged branch from the GitHub UI. Install `gh`
to avoid that and to get precise CodeRabbit polling.

---

## 4. Config and layout — what lives where

### The one committed config: `.project-conf.toml`

In the root of each slopstop project. Shared with your team.

```toml
# Required — what this project is (top-level keys; keep them above any [table])
system = "github"          # github | linear | jira
key    = "owner/repo"      # GitHub: "owner/repo"; Linear: team key; JIRA: project key
prefix = "BILL"            # tickets are BILL-1, BILL-2, …

# Where slopstop keeps per-ticket working notes (see "Layout" below).
# Also top-level — in TOML a bare key after a [table] belongs to that table,
# so these must sit above [status_labels].
tracking_dir = ".slopstop/ticket-active"
archive_dir  = ".slopstop/ticket-archive"

# GitHub only — how "in progress" is encoded (GitHub has no status field)
[status_labels]
in_progress = "status:in-progress"
# in_review = "status:in-review"    # uncomment for a 4-state workflow

# PR review backend (omit to use CodeRabbit)
[pr_review]
backend = "claude"         # coderabbit | claude
effort  = "high"           # low | medium | high | max | ultra
```

Every setting is documented in [CONFIG.md](CONFIG.md).

### Layout — three directories, and the one line that matters

slopstop uses three directories. The only thing to internalize is **which ones
git tracks**:

| Directory | Git | Lifespan | Holds |
|---|---|---|---|
| `design/` | **committed** | durable | design docs, decisions, invariants |
| `.slopstop/` | gitignored | per-ticket | tracking notes (`task_plan.md`, `findings.md`, `progress.md`), active + archived |
| `scratch/` | gitignored | per-run | transient `:design`/`:run` artifacts (PRDs, charters, run state) |

`design/` is the durable record you keep and commit. `.slopstop/` and `scratch/`
are the machine's short-term memory — gitignored, so nothing per-ticket or per-run
ever lands in a diff.

> **Keep the tracking dirs project-local — do not point them inside `~/.claude/`.**
> That is a protected path: an agent's `Write` tool refuses it *even with* a
> matching `--add-dir`. The historical defaults (`~/.claude/ticket-active`,
> `~/.claude/ticket-archive`) work for interactive use but silently break the
> headless agents `/slopstop:run` launches — an agent that can't write its tracking
> dir invents a local one and drifts. Set both keys to a `.slopstop/` path and add
> `.slopstop/` and `scratch/` to `.gitignore`. (`:gh-init` does this for you.)

---

## 5. Initializing a new project

> **Pick your workflow shape first.** `:merge` advances a ticket by exactly one
> state and supports two shapes:
>
> | Shape | States | When |
> |---|---|---|
> | **3-state** | `Todo → In Progress → Done` | most GitHub/simple boards |
> | **4-state** | `Todo → In Progress → In Review → Done` | when a review/QA gate precedes close |
>
> **GitHub:** the shape is declared by `[status_labels]` (3-state = `in_progress`
> only; 4-state = add `in_review`).
>
> **Linear / JIRA:** slopstop advances by one step using the board's existing
> states (same-bucket first, then forward-progress). This is clean for 3–4 states.
> For a longer board (`Backlog → Todo → In Dev → Review → QA → Done`), either
> simplify the board for this project, or accept that reaching Done takes several
> `:merge` calls.

### Step 1 — the fast path: `/slopstop:gh-init`

For a GitHub project, launch Claude Code in the repo root and run:

```
/slopstop:gh-init
```

It creates the `status:in-progress` label and writes a `.project-conf.toml` (and
gitignores `.slopstop/` + `scratch/`). Idempotent — safe to re-run. Then edit
`key`/`prefix` to taste and commit the file.

### Step 1 (manual alternative)

```bash
cat > .project-conf.toml << 'EOF'
system = "github"
key    = "owner/repo"
prefix = "MYPREFIX"

[status_labels]
in_progress = "status:in-progress"

tracking_dir = ".slopstop/ticket-active"
archive_dir  = ".slopstop/ticket-archive"
EOF

printf '.slopstop/\nscratch/\n' >> .gitignore
gh label create "status:in-progress" --color "0075ca" --description "Actively being worked on"
git add .project-conf.toml .gitignore && git commit -m "Add slopstop config"
```

### Step 2 — start your first ticket

```
/slopstop:start MYPREFIX-1
```

This marks the ticket in-progress, creates a `<type>/MYPREFIX-1` branch, and seeds
`.slopstop/ticket-active/MYPREFIX-1/` with `task_plan.md`, `findings.md`, and
`progress.md`. From there, follow the loop: `:plan` → implement → `:pr` → `:merge`.

---

## 6. Optional: file-size pre-commit gate

Refuse commits that add files over 1500 lines (via `wc -l`, comments and blanks
included); warn (non-blocking) between 1000–1500.

**Git hook** (applies to every `git commit` in the repo):

```bash
ln -sf ../../bin/pre-commit-file-size.sh .git/hooks/pre-commit
```

**Claude Code PreToolUse hook** (also blocks oversized files when Claude Code
commits on your behalf) — add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "bin/pre-commit-file-size.sh" } ] }
    ]
  }
}
```

**Opt-out pragma:** put the exact string `SLOPSTOP PRAGMA no-line-count-limit` in a
comment anywhere in a file to exempt it. Both the git hook and the `:pr`-time check
honor it.

---

## Quick reference

```
.project-conf.toml             per-project config: system, prefix, labels, tracking dirs (committed)
.mcp.json                      MCP server declarations, if any (committed)
design/                        durable, committed design docs
.slopstop/ticket-active/       per-ticket tracking notes while in flight (gitignored)
.slopstop/ticket-archive/      tracking notes for finished tickets (gitignored)
scratch/                       transient :design/:run artifacts (gitignored)
```
