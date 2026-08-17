# slopstop — setup guide

> **Claude Desktop users:** commands in this guide use the Claude Code form
> (`/slopstop:run`, `/slopstop:design`, etc.). If you installed via the Desktop
> installer, use the hyphenated form instead: `/slopstop-run`, `/slopstop-design`,
> and so on.

**If you want to see what slopstop actually does, you're in the wrong place.**
This file is setup/reference material — installing the plugin, wiring up MCP
servers, and laying out config — for someone who has already decided to use
slopstop and needs to configure it. It won't show you the workflow in action.
For that, go read **[QUICKSTART.md](QUICKSTART.md)** first: a 15-minute, hands-on
walkthrough of a real bug going from ticket to merged PR under one command. Come
back here once you're ready to set slopstop up on a project of your own.

**Audience:** A developer setting up slopstop on a new machine or a new project.

**What you get:** Ticket-anchored, tests-first development that runs
autonomously — `/slopstop:run` takes tickets from open to merged and archived,
against GitHub Issues, Linear, or JIRA.

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
| **Git** | Everything — branching, merging, diffs | 2.38+ |
| **Claude Code CLI** | The host slopstop runs inside | `npm install -g @anthropic-ai/claude-code` |
| **[lizard](https://github.com/terryyin/lizard)** | The complexity gate measures every function for [cyclomatic complexity](https://en.wikipedia.org/wiki/Cyclomatic_complexity) and stops the ticket when it exceeds the project's threshold | `pip install lizard` |
| **`gh` CLI** (GitHub projects) | Issue/PR operations; merging with branch deletion; reading bot comments | `brew install gh` / `apt install gh`, then `gh auth login` |

For a GitHub project you also want the **GitHub MCP** (see §3) — with it, `gh` is
optional for everything except the merge itself and reading review-bot comments.

---

## 2. Installing slopstop

### Claude Code (CLI) — recommended

```bash
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Six commands become available: `/slopstop:run`, `/slopstop:design`,
`/slopstop:tickets`, `/slopstop:grill`, `/slopstop:gh-init`, `/slopstop:doc-sync`.
(The eleven workers those orchestrators launch install alongside them, but you
never invoke one.)

### Claude Desktop (no `/plugin` support yet)

```bash
curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/master/install-for-claude-desktop.sh | bash
```

Skills install un-namespaced as `/slopstop-run`, `/slopstop-design`, etc.

---

## 3. MCP servers

slopstop talks to your ticket system through an MCP server. Install the one that
matches your `system`:

| `system` | MCP | Install |
|---|---|---|
| `github` | GitHub MCP (recommended; `gh` CLI is the fallback) | `/plugin install github@claude-plugins-official` |
| `linear` | Linear MCP | `/plugin install linear@claude-plugins-official` |
| `jira` | Atlassian MCP | `/plugin install atlassian@claude-plugins-official` |

For GitHub, `:run` prefers the MCP and falls back to `gh` automatically. One known
gap: the MCP's merge tool does not delete the remote branch, so with MCP-only (no
`gh`) slopstop will ask you to delete the merged branch from the GitHub UI.
Install `gh` to avoid that, and to read review-bot comments precisely
(`gh api repos/.../pulls/.../comments` — the MCP exposes no raw API proxy).

---

## 4. Config and layout — what lives where

### The one committed config: `.project-conf.toml`

In the root of each slopstop project. Shared with your team.

```toml
# Required — what this project is (top-level keys; keep them above any [table])
system = "github"          # github | linear | jira
key    = "owner/repo"      # GitHub: "owner/repo"; Linear: team key; JIRA: project key
prefix = "BILL"            # tickets are BILL-1, BILL-2, …

# No tracking_dir / archive_dir needed: a project-local .slopstop/ directory
# resolves both on its own (see "Layout" below). Set them only to override.

# GitHub only — how "in progress" is encoded (GitHub has no status field)
[status_labels]
in_progress = "status:in-progress"
# in_review = "status:in-review"    # uncomment for a 4-state workflow

# Whose review-bot comments :run reads once before merging (never waits for one)
[pr_review]
backend = "claude"         # coderabbit | claude | greptile

# After the merge, take the ticket to its terminal state (default true).
# false advances exactly one state and parks it — for work a machine cannot verify.
[workflow]
post_merge_done = true

# Bounds for the complexity-check worker (this table was [autonomous] until 2026-08-06)
[complexity]
cc_warn_threshold        = 5     # 🟡 elevated
cc_reject_threshold      = 10    # 🔴 stops the ticket
cc_exempt_pre_existing   = true  # exempt what the branch did not make worse
file_nloc_warn_threshold = 400   # 0 disables
```

**`:run` is the sole reader of this file.** It resolves every value and passes it
to each worker as an explicit argument; a worker given nothing blocks rather than
falling back to a default of its own. There is no `[autonomous]` table any more —
autonomy is one flag on the command (`--interactive`, declared but not yet
implemented), not config.

Every setting is documented in [CONFIG.md](CONFIG.md).

### Layout — three directories, and the one line that matters

slopstop uses three directories. The only thing to internalize is **which ones
git tracks**:

| Directory | Git | Lifespan | Holds |
|---|---|---|---|
| `design/` | **committed** | durable | design docs, decisions, invariants |
| `.slopstop/` | gitignored | per-ticket | tracking notes (`task_plan.md`, `findings.md`, `run.jsonl`), active + archived |
| `scratch/` | gitignored | per-run | transient `:design`/`:tickets` artifacts (PRDs, charters, `run.jsonl`) |

`design/` is the durable record you keep and commit. `.slopstop/` and `scratch/`
are the machine's short-term memory — gitignored, so nothing per-ticket or per-run
ever lands in a diff.

> **Create `.slopstop/` and both tracking paths resolve to it — no config needed.**
> Its presence alone means `.slopstop/ticket-active` and `.slopstop/ticket-archive`.
> This matters because the fallback, `~/.claude/`, is a protected path: an agent's
> `Write` tool refuses it *even with* a matching `--add-dir`, so it works for
> interactive use but breaks under `/slopstop:run` — which is why `:run` resolves
> the tracking dir once, itself, and no worker ever touches it. Add
> `.slopstop/` and `scratch/` to `.gitignore` in the same breath. (`:gh-init` does
> all of this for you.) Note the fix is a **directory**, not a key: `tracking_dir` is
> an override for when you want a path that isn't `.slopstop/`. Full ladder in
> [CONFIG.md](CONFIG.md).

---

## 5. Initializing a new project

> **Pick your workflow shape first.** After a merge, `:run` takes the ticket to
> its terminal state (or advances exactly one, with
> `[workflow] post_merge_done = false`). Two shapes are supported:
>
> | Shape | States | When |
> |---|---|---|
> | **3-state** | `Todo → In Progress → Done` | most GitHub/simple boards |
> | **4-state** | `Todo → In Progress → In Review → Done` | when a review/QA gate precedes close |
>
> **GitHub:** the shape is declared by `[status_labels]` (3-state = `in_progress`
> only; 4-state = add `in_review`).
>
> **Linear / JIRA:** slopstop uses the board's existing states, stepping through
> them (same-bucket first, then forward-progress). This is clean for 3–4 states.
> For a longer board (`Backlog → Todo → In Dev → Review → QA → Done`), simplify
> the board for this project.

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
EOF

# .slopstop/ is what resolves the tracking paths — create it and ignore it together.
mkdir -p .slopstop/ticket-active .slopstop/ticket-archive scratch
printf '.slopstop/\nscratch/\n' >> .gitignore
gh label create "status:in-progress" --color "0075ca" --description "Actively being worked on"
git add .project-conf.toml .gitignore && git commit -m "Add slopstop config"
```

### Step 2 — get tickets

If you're starting from an idea rather than a backlog, run the two design stages
first — each in its own session, since the boundary between them is artifact-only:

```
/slopstop:design <topic>       # → PRD + charter in scratch/runs/<run-id>/
/slopstop:tickets <run-id>     # → adversary-approved ticket tree in your tracker
```

`:tickets --retrofit <TICKET>` brings a single existing ticket up to the
five-section standard instead — useful when the backlog was written by someone who
never had to say what "done" meant.

### Step 3 — run them

```
/slopstop:run MYPREFIX-1 [MYPREFIX-2 ...]
```

That is the whole lifecycle — see [COMMANDS.md](COMMANDS.md) for what each command
does and when to reach for it. What matters for *setup* is where it puts things:
it seeds `.slopstop/ticket-active/MYPREFIX-1/` with `task_plan.md`, `findings.md`
and `run.jsonl`, and moves that directory to `.slopstop/ticket-archive/` when the
ticket lands.

It runs autonomously; a ticket that hits a gate it can't clear stops by itself and
leaves its branch alone, while the others carry on.

**Give it every ticket you want built, not one at a time.** It reads each ticket's
predicted file map and runs the non-colliding ones side by side.

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
comment anywhere in a file to exempt it.

This hook is independent of slopstop's own file-size signal, which is a 🟡 warning
from the `complexity-check` worker at `[complexity] file_nloc_warn_threshold`
(lizard NLOC, default 400). The hook blocks a commit; the worker warns on a diff.

---

## Quick reference

```
.project-conf.toml             per-project config: system, prefix, labels, tracking dirs (committed)
.mcp.json                      MCP server declarations, if any (committed)
design/                        durable, committed design docs
.slopstop/ticket-active/       per-ticket tracking notes + run.jsonl while in flight (gitignored)
.slopstop/ticket-archive/      tracking notes for finished tickets (gitignored)
scratch/runs/<run-id>/         transient :design/:tickets artifacts: prd.md, charter.md, run.jsonl (gitignored)
```
