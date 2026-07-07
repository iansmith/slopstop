# CONFIG.md — slopstop configuration reference

This file documents every configuration option across all slopstop config files. For installation walkthroughs, see `README.md`. For first-time setup, see `design/cold-start.md`.

---

## Configuration files at a glance

| File | Scope | Committed? | Purpose |
|---|---|---|---|
| `.project-conf.toml` | Per project | ✅ Yes | Ticket system, workflow shape, PR review, code graph, autonomous mode |
| `~/.slopstop/config.toml` | Per machine (user) | ❌ No | SCIP indexer tool paths |
| `~/.slopstop/github_token` | Per machine | ❌ No | GitHub personal access token (harvesters, cron) |
| `~/.slopstop/linear_token` | Per machine | ❌ No | Linear API key (harvesters, cron) |
| `~/.slopstop/jira_api_token` | Per machine | ❌ No | JIRA API token |
| `~/.slopstop/jira_email` | Per machine | ❌ No | JIRA account email |
| `~/.slopstop/jira_base_url` | Per machine | ❌ No | JIRA instance URL |
| `.harvester.toml` | Per project | ❌ No | Harvester credentials (gitignored) |
| `.mcp.json` | Per project | ✅ Yes | MCP server declarations |

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

### Top-level optional keys — remotes

```toml
pr-remote     = "origin"   # remote to push feature branches to when opening a PR
origin-remote = "origin"   # canonical remote: PR target + :merge source of truth
```

Both keys are optional and default to `"origin"` when absent, so existing configs work unchanged.

| Key | Default | Description |
|---|---|---|
| `pr-remote` | `"origin"` | Remote that `:pr` and `:start` push feature branches to. Set to your personal fork name (e.g. `"mine"`) when working on a project where you push to a fork and open PRs against the upstream. |
| `origin-remote` | `"origin"` | The canonical/blessed remote. `:start` uses it as the base for new branches (`$ORIGIN_REMOTE/$DEFAULT_BRANCH`). `:merge` fetches and pulls from it, and the multi-remote propagation loop skips it (it already has the merge). `:pr` derives the PR target repo from it. |

**Typical fork workflow:**

```toml
pr-remote     = "mine"      # git remote pointing at your personal fork
origin-remote = "upstream"  # git remote pointing at the canonical upstream
```

With this config, `:pr` pushes to `mine` before opening the PR, and the PR is opened against the canonical repo. `:merge` cleans up by fetching from the configured `origin-remote` (`upstream` here) and propagating the merged base branch to any other remotes — including `mine`, keeping the fork in sync.

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
module_root = "."               # repo-root-relative path where the indexer runs
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
| `cc_warn_threshold` | `10` | `:pr` | 🟡 CC-elevated boundary for the CC gate (Step 0c). Functions with `cc_warn_threshold < CC ≤ cc_reject_threshold` are flagged 🟡. |
| `cc_reject_threshold` | `15` | `:pr` | 🔴 hard-gate threshold for the CC gate. Functions with CC > this value are violations. |
| `file_nloc_warn_threshold` | `400` | `:pr` | 🟡 file-size warning in the CC gate. Files whose lizard NLOC sum exceeds this threshold are flagged 🟡. Set `0` to disable. |

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

---

## `.harvester.toml` — credentials (gitignored)

Copy `.harvester.toml.example` and fill in values for your ticket system:

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

Committed to the project root. Claude Code picks it up at session start and launches the declared servers. For most slopstop projects, the file is empty:

```json
{
  "mcpServers": {}
}
```

MCPs required by the skills (Linear, GitHub, JIRA) are installed as plugins via `/plugin install`, not declared in `.mcp.json`. See `design/cold-start.md §3` for the install commands.

If your project needs project-specific MCP servers (e.g. a custom internal tool), declare them here as additional entries under `mcpServers`.
