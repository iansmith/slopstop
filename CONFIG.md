# CONFIG.md — slopstop configuration reference

This file documents every configuration option across all slopstop config files. For installation walkthroughs, see `README.md`. For first-time setup, see `design/cold-start.md`.

---

## Configuration files at a glance

| File | Scope | Committed? | Purpose |
|---|---|---|---|
| `.project-conf.toml` | Per project | ✅ Yes | Ticket system, workflow shape, PR review, code graph, hooks, autonomous mode |
| `~/.slopstop/config.toml` | Per machine (user) | ❌ No | SCIP indexer tool paths, RAG service URL |
| `~/.slopstop/github_token` | Per machine | ❌ No | GitHub personal access token (harvesters, cron) |
| `~/.slopstop/linear_token` | Per machine | ❌ No | Linear API key (harvesters, cron) |
| `~/.slopstop/jira_api_token` | Per machine | ❌ No | JIRA API token |
| `~/.slopstop/jira_email` | Per machine | ❌ No | JIRA account email |
| `~/.slopstop/jira_base_url` | Per machine | ❌ No | JIRA instance URL |
| `.harvester.toml` | Per project | ❌ No | Harvester credentials (legacy; prefer token files) |
| `.mcp.json` | Per project | ✅ Yes | MCP server declarations (slopstop-rag, etc.) |

---

## `.project-conf.toml` — per-project settings

One file at the repo root. Committed to git — shared with anyone cloning the project.

### Top-level required keys

```toml
system = "github"          # "github" | "linear" | "jira"
key    = "owner/repo"      # GitHub: "owner/repo" slug
                           # Linear: team key (e.g. "MAZ")
                           # JIRA: project key (e.g. "PLTF")
prefix = "BILL"            # Ticket prefix — BILL-NN; usually same as key for Linear/JIRA
```

All three are required. Every slopstop skill reads these first and refuses with a clear error if any is missing.

**`system`** determines which ticket backend is used (GitHub Issues label-based workflow, Linear native state machine, or JIRA transitions). Authoritative for all skills — never inferred from MCP availability.

**`key`** is how each skill constructs API calls. For GitHub, the `owner/repo` form is split on `/` to get `$OWNER` and `$REPO`. For Linear/JIRA, it is the team/project key used directly in API calls.

**`prefix`** is the ticket-number prefix (e.g. `BILL` → tickets `BILL-1`, `BILL-2`, …). Skills only operate on tickets matching `^prefix-\d+$` — a session in a `BILL` project will never accidentally touch a `MAZ-*` ticket. For GitHub Issues, `prefix` and the GitHub issue number must agree: `BILL-65` always means GitHub issue `#65`. Use `/slopstop:create-gh` to create issues that preserve this alignment.

---

### `[status_labels]` — GitHub Issues workflow shape

**GitHub only.** Ignored for Linear and JIRA (which use their native state machines).

```toml
[status_labels]
in_progress = "status:in-progress"   # Required — label applied when a ticket starts
# in_review  = "status:in-review"   # Optional — uncomment to enable 4-state workflow
```

| Key | Required | Default | Description |
|---|---|---|---|
| `in_progress` | ✅ Yes (GitHub only) | — | Label name applied when `/slopstop:start` transitions a ticket to In Progress. Must exist on the repo. |
| `in_review` | ❌ No | absent | If set, enables 4-state workflow (`In Progress → In Review → Done`). `/slopstop:merge` swaps labels instead of closing the issue. Omit for 3-state (`In Progress → Done`). |

Create the labels before your first ticket:

```bash
gh label create "status:in-progress" --color "0075ca" --description "Actively being worked on"
gh label create "status:in-review"   --color "e4e669" --description "In review / QA"   # 4-state only
```

---

### `[pr_review]` — PR review backend

Configures what `/slopstop:pr` does after opening the pull request. Omit the entire block to use CodeRabbit (if installed on the repo) with no extra config.

```toml
[pr_review]
backend = "claude"    # "coderabbit" (default) | "claude"
effort  = "high"      # low | medium | high | max | ultra  (Claude only; default: "high")
fix     = false       # true: auto-commit fixable findings after code-review  (Claude only; default: false)
```

| Key | Type | Default | Description |
|---|---|---|---|
| `backend` | string | `"coderabbit"` | Which review backend `:pr` uses. `"coderabbit"`: poll for CodeRabbit feedback (requires CodeRabbit installed on the repo). `"claude"`: invoke `/code-review` at the configured effort level. |
| `effort` | string | `"high"` | Effort level passed to `/code-review`. Claude backend only. One of `low` / `medium` / `high` / `max` / `ultra`. |
| `fix` | bool | `false` | If `true`, fixable findings from `/code-review` are auto-committed and pushed after the review completes. Claude backend only. **Conflict:** do not set both `fix = true` here AND `[autonomous] on_red_findings = "fix-and-retry"` — they double-apply fixes. |

When `[pr_review]` is absent AND CodeRabbit is not installed on the repo, no review step runs. Pass `--no-poll` to skip the review step explicitly.

---

### `[workflow]` — non-autonomous confirmation shortcuts

Reduces friction in interactive sessions without enabling full autonomous mode.

```toml
[workflow]
skip_confirm = true    # true | false (default: false)
```

| Key | Type | Default | Description |
|---|---|---|---|
| `skip_confirm` | bool | `false` | If `true`, skips the interactive confirmation prompts in `:merge`, `:archive`, and `:start` (when a branch-type heuristic suggestion is available). Auto-proceeds as `yes` and logs the plan. Has no effect when `[autonomous] enabled = true` (autonomous mode already skips confirmations). |

**When to use:** personal projects where you always say yes and the confirmation adds friction without value. Not recommended for team repos where multiple people might need to review what's about to happen.

---

### `[code-graph]` — SCIP code indexing

Controls which languages are indexed into the code knowledge graph on each `git merge`.

```toml
[code-graph]
languages   = ["python"]        # list of language names to index
module_root = "rag-service"     # repo-root-relative path where the indexer runs
skip        = ["tests/"]        # path prefixes / glob patterns to exclude

# Per-project tool overrides (optional — overrides ~/.slopstop/config.toml [tools])
# Only set when a specific version is required for this project.
# [code-graph.tools]
# scip_python = "/home/you/.nvm/versions/node/v20/bin/scip-python"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `languages` | list of strings | `[]` | Languages to index. Supported values: `"go"`, `"python"`, `"typescript"`, `"javascript"`. Each language maps to a SCIP indexer binary resolved from `[code-graph.tools]` or `~/.slopstop/config.toml [tools]`. |
| `module_root` | string | `"."` | Directory relative to the repo root where the SCIP indexer is invoked. Commit file paths (repo-root-relative) have this prefix stripped before matching against SCIP-indexed paths (which are module-root-relative). For a Go module at the root, use `"."`. For a Python package in a subdirectory, set it to that directory. |
| `skip` | list of strings | `[]` | Path prefixes or glob patterns excluded from indexing. Typical entries: `"tests/"`, `"vendor/"`, `"*.pb.go"`. |

**`[code-graph.tools]` sub-section:** Per-project overrides for indexer binary paths. Keys are `scip_go`, `scip_python`, `scip_typescript`, `scip` (the SCIP CLI converter). Leave absent to use the global defaults in `~/.slopstop/config.toml [tools]`. Only set these when a specific version is required — they are committed and shared with collaborators, so full paths are inappropriate here; use `~/.slopstop/config.toml` for machine-local paths.

---

### `[rag]` — RAG search tuning

```toml
[rag]
corpus_scope = "github"    # ticket system name — defaults to the value of `system`
```

| Key | Type | Default | Description |
|---|---|---|---|
| `corpus_scope` | string | value of `system` | Filters which ticket system's data `/slopstop:search` queries. Useful when the RAG service holds data from multiple systems and you want to search only one. Set explicitly if your `system` and the corpus name differ. |

The RAG service URL comes from `~/.slopstop/config.toml [rag].url` (machine-local), not from `.project-conf.toml`. The MCP server endpoint is configured in `.mcp.json`.

---

### `[hooks]` — scheduled operations

```toml
[hooks]
harvest_schedule    = "04:00"    # HH:MM or 5-field cron expression, or "" to disable
text_harvest_on_merge = false    # true | false (default: false)
```

| Key | Type | Default | Description |
|---|---|---|---|
| `harvest_schedule` | string | `""` | When non-empty, `slopstop-schedule-harvest` generates a crontab entry that runs the nightly ticket-text harvester at this time. Format: `"HH:MM"` (local time, normalised to `MM HH * * *`) or a full 5-field cron expression (used verbatim). Empty string or absent means disabled. |
| `text_harvest_on_merge` | bool | `false` | If `true`, `/slopstop:archive` triggers a ticket-text harvest for the archived ticket when finalising. Use when you want the ticket's final state captured in the corpus immediately after archiving. |

To generate a crontab entry from the current config:

```bash
slopstop-schedule-harvest             # from the project dir
slopstop-schedule-harvest ~/my-proj   # or pass the path
```

This script is **read-only** — it prints the entry but does not write to crontab or modify any file. See the [nightly harvest crontab section](#nightly-harvest--crontab-setup) below for what to do with the output.

---

### `[autonomous]` — non-interactive mode

Designed for benchmark harnesses (SlopCodeBench), overnight runs, and CI pipelines where no human is present. All interactive confirmation prompts are replaced by config-driven decisions. **Requires `enabled = true` to activate** — a partial block with some keys set but `enabled` absent or `false` has no effect.

```toml
[autonomous]
enabled = true

# :start — skip branch-type selection prompt
branch_type = "feat"               # fix | feat | chore | docs | refactor | perf | test | ci | build | deploy | revert | <custom>

# :plan — what to do when Phase 0 tests already pass (ticket may be stale)
on_phase0_tests_pass = "continue"  # ask | continue | abort

# :plan — what to do when the plan recommends parallel agents
on_parallel_agents = "proceed"     # ask | proceed | serial | abort

# :plan — what to do when the adversary agent finds gap tests
on_test_gaps = "add-all"           # add-all | skip

# :pr — what to do when simplify modifies the working tree
on_simplify_changes = "accept"     # ask | accept | reject

# :pr — what to do when pre-commit tests fail
on_test_failure = "abort"          # ask | abort | commit-anyway

# :pr — what to do with 🔴 review findings (Claude backend only)
# NOTE: conflicts with [pr_review] fix = true — set fix = false when using fix-and-retry
on_red_findings = "fix-and-retry"  # ask | fix-and-retry | skip

# :pr — what to do when slop detection finds violations
on_slop_findings = "skip"          # ask | skip

# :merge — PR merge strategy
merge_strategy = "squash"          # squash | merge | rebase

# :merge — ticket target state after merge
merge_target_state = "auto"        # auto | done | skip

# :merge — chain into :archive immediately after a successful merge (terminal state only)
archive_immediately = true         # true | false

# All skills — emit pipeline.json to this dir after each command (for metric collection)
metrics_emit_path = "~/.claude/ticket-active"
```

#### Key reference

| Key | Default | Skill | Description |
|---|---|---|---|
| `enabled` | `false` | All | Master switch. Must be `true` for any other key in this section to take effect. |
| `branch_type` | (ask) | `:start` | Conventional Commits prefix used for branch names. Skips the interactive type-selection prompt. Must pass `git check-ref-format`. Falls back to interactive prompt if the value is invalid. |
| `on_phase0_tests_pass` | `"ask"` | `:plan` | What to do when Phase 0 red tests unexpectedly pass (possible stale ticket). `"continue"` proceeds, `"abort"` stops. |
| `on_parallel_agents` | `"ask"` | `:plan` | What to do when ≥2 work items are parallel-safe. `"proceed"` launches agents, `"serial"` runs them sequentially, `"abort"` stops. |
| `on_test_gaps` | `"ask"` | `:plan` | Whether to add adversary-found gap tests. `"add-all"` adds all findings without prompting. |
| `on_simplify_changes` | `"ask"` | `:pr` | What to do when the simplify pass modifies the working tree. `"accept"` incorporates changes. |
| `on_test_failure` | `"ask"` | `:pr` | What to do on pre-commit test failure. `"abort"` stops; `"commit-anyway"` notes the failure in the commit body and proceeds. |
| `on_red_findings` | `"ask"` | `:pr` | What to do with 🔴 code-review findings. `"fix-and-retry"` applies fixes and re-reviews (loop with convergence guard). Claude backend only. |
| `on_slop_findings` | `"ask"` | `:pr` | What to do with slop-detection violations. `"skip"` bypasses the check entirely. |
| `merge_strategy` | `"merge"` | `:merge` | PR merge strategy. Overrides the `--strategy` flag default. |
| `merge_target_state` | `"auto"` | `:merge` | Ticket state after merge. `"auto"` uses the advance-one-state algorithm. `"done"` forces terminal state. `"skip"` skips the ticket-system transition entirely. |
| `archive_immediately` | `false` | `:merge` | If `true` and the post-merge state is terminal, chains into `:archive` without prompting. If the state is intermediate, logs a skip message. |
| `metrics_emit_path` | absent | All | Directory to write `<TICKET>/pipeline.json` after each command completes. Used for benchmark metric collection. |

All keys default to the interactive `"ask"` path when absent — a partial `[autonomous]` block with only some keys filled in is safe.

---

## `~/.slopstop/config.toml` — user-level settings

Machine-local, gitignored. Created automatically as a template by `slopstop-install-hooks` on first run; you fill in the values.

```toml
[tools]
# go install github.com/sourcegraph/scip-go/cmd/scip-go@latest
scip_go = ""

# npm install -g @sourcegraph/scip-typescript
scip_typescript = ""

# npm install -g @sourcegraph/scip-python
scip_python = ""

# go install github.com/sourcegraph/scip/cmd/scip@latest  (used for JSON conversion)
scip = ""

[rag]
url = "http://localhost:7777"
```

### `[tools]` — SCIP indexer paths

| Key | Install command | Description |
|---|---|---|
| `scip_go` | `go install github.com/sourcegraph/scip-go/cmd/scip-go@latest` | SCIP indexer for Go repos. Binary lands in `~/go/bin/scip-go`. |
| `scip_python` | `npm install -g @sourcegraph/scip-python` | SCIP indexer for Python repos. |
| `scip_typescript` | `npm install -g @sourcegraph/scip-typescript` | SCIP indexer for TypeScript/JavaScript repos. |
| `scip` | `go install github.com/sourcegraph/scip/cmd/scip@latest` | SCIP CLI — converts SCIP output to JSON for ingestion. |

**nvm/asdf/mise users:** do not use `nvm exec` — supply the full resolved path to the binary, e.g. `~/.nvm/versions/node/v20.19.3/bin/scip-python`. Shell function wrappers are not executable paths and will fail validation.

Tool paths can be overridden per-project via `[code-graph.tools]` in `.project-conf.toml`. Resolution order: project override → user default → error with install hint.

### `[rag]` — RAG service URL

| Key | Default | Description |
|---|---|---|
| `url` | `"http://localhost:7777"` | URL of the running `slopstop-rag` container. Used by `slopstop-ingest`. The MCP server gets its URL from `.mcp.json`'s `RAG_SERVICE_URL` env var (a separate config path). Change this if you run the container on a non-default port. |

---

## Token files for harvesters

Credentials for the nightly harvest cron jobs. Stored as plain text files, one value per file. **Never committed.** Permissions should be `600`.

| File | System | Value | Create with |
|---|---|---|---|
| `~/.slopstop/github_token` | GitHub | Personal access token (`ghp_…`) | `echo "ghp_..." > ~/.slopstop/github_token && chmod 600 ~/.slopstop/github_token` |
| `~/.slopstop/linear_token` | Linear | API key (`lin_api_…`) | `echo "lin_api_..." > ~/.slopstop/linear_token && chmod 600 ~/.slopstop/linear_token` |
| `~/.slopstop/jira_api_token` | JIRA | JIRA API token | `echo "..." > ~/.slopstop/jira_api_token && chmod 600 ~/.slopstop/jira_api_token` |
| `~/.slopstop/jira_email` | JIRA | Atlassian account email | `echo "you@example.com" > ~/.slopstop/jira_email` |
| `~/.slopstop/jira_base_url` | JIRA | JIRA instance URL | `echo "https://yourorg.atlassian.net" > ~/.slopstop/jira_base_url` |

The cron entry generated by `slopstop-schedule-harvest` reads these files at runtime using `cat ~/.slopstop/<file>`. The actual secret value never appears in the crontab entry — only the `cat` expression does.

---

## Nightly harvest — crontab setup

The `slopstop-schedule-harvest` script reads `[hooks].harvest_schedule` from `.project-conf.toml` and prints a correctly formatted crontab entry. Run it once per project to get the entry to paste:

```bash
cd ~/my-project
slopstop-schedule-harvest
```

Install the printed entry:

```bash
crontab -e                              # open your crontab in $EDITOR

# or append non-interactively (preserves existing entries):
(crontab -l 2>/dev/null; slopstop-schedule-harvest) | crontab -
```

### What PATH cron uses and how to change it

Cron does **not** inherit your shell's `$PATH`. It uses a fixed minimal PATH:

- **Linux:** `/usr/bin:/bin`
- **macOS:** `/usr/bin:/bin:/usr/sbin:/sbin`

Docker (typically in `/usr/local/bin` or `/opt/homebrew/bin`) and Homebrew Python (in `/opt/homebrew/bin`) are **not** on cron's PATH. Running a cron entry with bare `docker` or `python3` will silently fail.

`slopstop-schedule-harvest` resolves full paths to both binaries at generation time using `command -v` and embeds them directly in the entry. **This is why you must re-run `slopstop-schedule-harvest` if you reinstall docker or python3 or move to a new machine.**

If you prefer to set `PATH` at the top of your crontab instead:

```
# Add this line at the very top of your crontab, before any entries:
PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin
```

With this, you can use bare `docker` and `python3` in all cron entries. The script will show the exact `PATH=` line to use (deduplicating directories shared by both binaries).

### Why docker and python3 need full paths

The cron entry uses **two separate Python instances**:

1. **Host `python3`** (full path embedded) — runs on the host machine before calling `docker exec`. Used only to compute yesterday's ISO date: `python3 -c "from datetime import date,timedelta; print(date.today()-timedelta(days=1))"`. Needs a full path because cron's PATH won't find a non-system python3.

2. **Container `python3`** (bare name, intentionally) — runs inside the `slopstop-rag` container via `docker exec`, executing `python3 -m rag_service.harvesters.<system> sync-recent --since "$SINCE"`. This python3 is managed by the container's own Dockerfile and PATH — the container's `python3` is always correct, no full path needed.

These are distinct and intentionally handled differently. Do not replace the container's bare `python3` with a host path.

### Where logs go

By default cron mails stdout+stderr to the local user via sendmail. On most developer machines sendmail is not configured, so **all output is silently discarded** — errors and success messages disappear with no indication.

The generated cron entry redirects to `~/.slopstop/harvest.log`:

```
>> ${HOME}/.slopstop/harvest.log 2>&1
```

This file is appended on every run. To rotate manually:

```bash
# Keep only the last 500 lines:
tail -n 500 ~/.slopstop/harvest.log > /tmp/h.log && mv /tmp/h.log ~/.slopstop/harvest.log
```

To disable logging (silent): change the redirect to `> /dev/null 2>&1`. To log to a system directory: `>> /var/log/slopstop-harvest.log 2>&1` (may require sudo). Edit the end of the cron command before pasting.

### Container environment for `docker exec` harvesters

`docker exec` inherits the container's **existing environment** — the env vars set when the container was started with `docker run`. You do not need to pass `RAG_SERVICE_PG_DSN`, the embedder model path, or other service configuration via `-e` flags; those are already in the container's environment.

The only env vars the harvester cron entry passes explicitly are the credentials (read from token files at runtime):

- **GitHub/Linear:** one var (`GITHUB_TOKEN` or `LINEAR_API_KEY`) via `-e "VAR=$VAR"`
- **JIRA:** three vars (`JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_BASE_URL`) via `-e` for each

Key container environment variables (set at `docker run` time or via Makefile):

| Variable | Default | Description |
|---|---|---|
| `RAG_SERVICE_PG_DSN` | `dbname=postgres user=postgres host=localhost connect_timeout=1` | Postgres DSN. The default is correct inside the container (postgres and the FastAPI app share the same container). Only override if you run a separate postgres. |
| `RAG_SERVICE_BGE_M3_PATH` | `/models/bge-m3` | Path inside the container to the bge-m3 embedder weights. The model is baked into the image at build time — do not change unless you rebuild. |

**Model cold-load note:** each `docker exec` invocation creates a new process inside the container. The bge-m3 embedder (~500 MB) loads fresh on every invocation — expect several seconds of startup before harvesting begins. This is acceptable for a nightly schedule. If you need faster repeated harvesting, use the harvester's HTTP API directly instead of `docker exec`.

### Crontab file location

User crontabs are managed via `crontab -e` / `crontab -l` — never edit the underlying file directly, as its format is system-dependent.

- **Linux (Debian/Ubuntu):** `/var/spool/cron/crontabs/<username>`
- **Linux (RHEL/Fedora):** `/var/spool/cron/<username>`
- **macOS (pre-Ventura):** `/usr/lib/cron/tabs/<username>`
- **macOS (Ventura+):** `/var/at/tabs/<username>`

On macOS, `cron` works but `launchd` is the native scheduler. A launchd plist in `~/Library/LaunchAgents/` survives sleep/wake and runs missed jobs on wake. For a dev machine where occasional misses are fine, crontab is simpler to set up.

---

## `.harvester.toml` — credentials (legacy, gitignored)

An earlier credential format. Copy `.harvester.toml.example` and fill in values. The token-file approach above (`~/.slopstop/<name>`) is preferred for new setups because it is machine-local and works cleanly with `slopstop-schedule-harvest`.

```toml
[linear]
api_key = "lin_api_..."

# [jira]
# email     = "you@example.com"
# api_token = "..."
# base_url  = "https://your-site.atlassian.net"
```

---

## Claude Code settings hierarchy and scope

### Settings load order

Claude Code applies settings from multiple sources in priority order (highest wins):

1. **Managed** — set by the organization/account administrator
2. **Command-line flags** — passed at startup
3. **Local** — `.claude/settings.local.json` in the project root (gitignored)
4. **Project** — `.claude/settings.json` in the project root (committed)
5. **User** — `~/.claude/settings.json` (machine-local)

This applies to all settings: permissions, tool configurations, environment variables, etc.

### Controlling which settings sources load: `--setting-sources`

Claude Code accepts a `--setting-sources` flag that takes a comma-separated list of settings scopes to load. Use this when you want to restrict or expand which layers of settings and skills are active for a session.

```bash
claude --setting-sources user                   # user settings only (~/.claude/)
claude --setting-sources project                # project settings only (.claude/ in cwd)
claude --setting-sources user,project           # both (the normal default)
claude --setting-sources project,local          # project + machine-local overrides, no user
```

Available source names mirror the settings hierarchy: `managed`, `user`, `project`, `local`. Combine as many as needed with commas; order does not change the priority (the hierarchy above still applies within the loaded set).

**Why this matters for users with extra skills:** if you have personal skills in `~/.claude/commands/` (user-level) and want to run a project session with *only* the project's plugin skills loaded — no personal extras — start Claude with:

```bash
claude --setting-sources project
```

Conversely, to use your user-level skills without any project config influencing the session:

```bash
claude --setting-sources user
```

### Skills (slash commands) scope

Skills are loaded from multiple locations:

- **User-level:** `~/.claude/commands/` — available in every project on this machine
- **Project-level:** `.claude/commands/` in the project root — available only in this project
- **Plugin-installed:** managed by `/plugin` install/uninstall; namespaced (e.g. `/slopstop:start`)

By default all sources load. `--setting-sources` controls which subset loads for a given session.

**`.claude/settings.local.json`** (per-machine project override): a gitignored file at the project root. Loaded as the `local` source — highest priority among committed/local layers. Useful for per-machine opt-outs that should not affect collaborators.

### Plugin vs Desktop install

| Install method | Command namespace | Commands file |
|---|---|---|
| `claude` CLI + `/plugin install` | `/slopstop:start`, `/slopstop:pr`, … | Managed by plugin system |
| `install-for-claude-desktop.sh` | `/slopstop-start`, `/slopstop-pr`, … | `~/.claude/commands/slopstop-*.md` |

The Desktop install drops files into `~/.claude/commands/` as user-level commands (un-namespaced). If you have both a plugin install and a Desktop install, you get duplicate commands — uninstall one:

```bash
# Remove Desktop install:
rm ~/.claude/commands/slopstop-{start,plan,update,document,archive,pr,merge,doc-sync,create-gh}.md
```

---

## `.mcp.json` — MCP server declarations

Committed to the project root. Claude Code picks it up at session start and launches the declared servers.

```json
{
  "mcpServers": {
    "slopstop-rag": {
      "type": "stdio",
      "command": "python3",
      "args": ["/absolute/path/to/slopstop/mcp-server/server.py"],
      "env": {
        "RAG_SERVICE_URL": "http://localhost:7777"
      }
    }
  }
}
```

The slopstop repo ships its own `.mcp.json` pointing at `mcp-server/server.py` via a relative path — works when your project is the slopstop repo itself. For other projects, use the absolute path to wherever you cloned slopstop.

`RAG_SERVICE_URL` must match the port the `slopstop-rag` container is bound to. Change it here if you run the container on a non-default port (e.g. `-p 127.0.0.1:7778:7777`).

Other MCPs required by the skills (Linear, GitHub, JIRA) are installed as plugins via `/plugin install`, not declared in `.mcp.json`. See `design/cold-start.md §4` for the install commands.
