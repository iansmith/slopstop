# Changelog

All notable changes to this plugin will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.0] — 2026-07-17

### Added

- **`/slopstop:pr` links every PR-mutating review back to the ticket (Step 7f).** CodeRabbit, Greptile, and Claude (`--comment`, the default) all post comments directly onto the PR — none of them is terminal-only — so `:pr` now posts a comment on the originating ticket (JIRA/Linear/GitHub) pointing at the PR and summarizing the review outcome, once the review actually ran. Skipped only on `--no-poll`. Never blocks PR completion on failure.
- **`gh-init`/`focus` added to Desktop install `SKILLS` arrays (BILL-304).** Both commands existed under `skills/` but were missing from `install-for-claude-desktop.sh` and `install-for-claude-desktop-local.sh`, so Desktop users never got them.
- **Reference-copy propagation tooling for the universal CLAUDE.md block.** The universal §1–10 rules are now delimited by `<!-- BEGIN/END UNIVERSAL SECTION -->` markers with a mechanical propagation script (`.claude/rules/repo-conventions.md`) that copies the marked block from `ticket-plugin` (the reference copy) to the five mirrored projects and asserts they match. Replaces error-prone hand-copying — an earlier loose-regex attempt at this silently duplicated content into a mirror instead of replacing it.

### Changed

- **`:merge` autonomous-mode gating now matches `:start`.** Previously required the `--autonomous` CLI flag; now also honors `[autonomous] enabled = true` in `.project-conf.toml`, consistent with every other autonomous-aware skill.
- **CONFIG.md's `[pr_review]` docs brought in line with the code.** The `backend` table and inline TOML comment now document `"greptile"` as a valid value (the code already dispatched on it) and add the previously-undocumented `coderabbit_fix` / `greptile_fix` keys.

## [3.2.0] — 2026-07-16

Router tag-based attribution, the `:focus` command, and onboarding polish.

### Added

- **`/slopstop:focus` — lightweight mid-session re-tag (BILL-295).** Re-points attribution (run-id, ticket) without a branch or ticket-system transition. Useful when shifting focus within a session.
- **Router `/tag` endpoint (BILL-292, BILL-293, BILL-294).** Per-ticket metering attribution via an in-memory tag map. `:start` POSTs to `/tag` when `[fleet.router] enabled = true`, associating the run-id with the active ticket. The `/spend` endpoint now breaks down costs by tag. Integration tests cover the full tag lifecycle.
- **Router `/spend` HTML format (BILL-274).** `Accept: text/html` or `?format=html` returns a styled spend report for browser consumption.
- **Tier-derived fleet and escalation model defaults (BILL-271).** Fleet agent and escalation models are now derived from the `[tiers]` ladder instead of being hardcoded, so a single `[tiers]` edit propagates everywhere.
- **`router/ornith-dev.toml`.** Dev-fleet supervisor config for the ornith MLX model + litellm proxy + slopstop-router stack.

### Changed

- **QUICKSTART.md clarified for first-time readers.** Explains the `plugin@marketplace` install syntax; notes the `--top 3` off-by-one in the demo output; switches the §5 paste block from a blockquote to a code block; tells readers to pick one language for all four tickets.
- **QUICKSTART/START-HERE modernized (BILL-289).** Project-local `.slopstop/` tracking is now the default narrative throughout; references to `~/.claude/ticket-active/` removed from the onboarding path.
- **Router README documents `/tag` (BILL-291).** Covers the header→map→untagged precedence for attribution.

### Fixed

- **Router `prices.toml`: add Haiku 4.5 snapshot entry.** The dated `claude-haiku-4-5-20251001` model ID was unpriced, falling into the unknown-model bucket.
- **`:merge` tamper gate (BILL-278).** The frozen-red-test tamper check was not running in some paths; Gate 0 fall-through fixed. Baseline tests are now mechanically verified as red before the fix commit.
- **`archive_immediately` doc examples (BILL-278).** Examples now match the documented default value.

## [3.1.1] — 2026-07-13

### Fixed

- **Router pricing: revert 1.3x dense-tokenizer markup.** The API already reports inflated token counts for dense-tokenizer models (Sonnet 5, Opus 4.8, Fable 5), so the per-token prices in `prices.toml` were double-counting. Reverted to Anthropic list prices for invoice-accurate metering.
- **Add `claude-opus-4-6` to `prices.toml`.** Needed by sophie's `[tiers.large]` config. Same $5/$25 pricing as Opus 4.8.
- **Update Go tests for corrected prices.** `TestRatePreservationTransferred`, `TestRealPricesTomlTierMapping`, and `TestEmbeddedManifestLoadsWhenPricesAbsent` now assert list prices and cover the new Opus 4.6 entry.

### Added

- **Plugin install line in G1/G2 reports.** `:design` and `:tickets` gate reports now include a `Plugin:` line showing how to load slopstop in the next session.

## [3.1.0] — 2026-07-13

The router and the version-aware tier system. The metering proxy (`router/`) graduates from a standalone experiment to a shipped component, and `[tiers]` gains a table form that lets you pin model versions — e.g. `huge = opus 4.8`, `large = opus 4.6` — so the tier gate can distinguish models within the same family.

### Added

- **Router: transparent metering proxy (BILL-202 → BILL-211, BILL-230 → BILL-232, BILL-249).** `router/` is a Go module (`github.com/iansmith/slopstop/router`) that sits between Claude Code sessions and `api.anthropic.com`, meters every request by extracting `usage` blocks from responses, and serves a `/spend` endpoint with aggregates by prefix, run, ticket, tier, and model. Handles gzipped responses (BILL-201 live gate fix), unknown models (unpriced bucket), and SSE streaming. Budget-relative display: each `/spend` response includes `total_usd_display` and per-model `usd_display` showing `"$X.YY (estimated A.AA% of $1100)"` against a `MonthlyBudgetUSD` constant.
- **`verify.sh` acceptance test (BILL-211).** Builds the router binary, starts it on a free loopback port, runs a real `claude -p` agent session through it, and asserts `/spend` shows nonzero metered traffic. Supports both API-key and subscription (`/login`) auth.
- **`[stage_tiers]` two-hop resolution (BILL-239, BILL-240).** Stage→tier and tier→model are now separate config layers. Re-tiering a stage (e.g. `:tickets` from medium to large) is a one-line `[stage_tiers]` edit, no skill rewrite.
- **Four-tier relabel (BILL-238).** `big`→`huge`/`large` — the process is now `huge > large > medium > small` throughout skills, config, and docs.
- **`go-edit` MCP server for fleet agents (vendored, `tools/mcp-go-edit/`).** Whitespace-tolerant `.go`-only Edit with atomic `gofmt`.

### Changed

- **`[tiers]` table form with version pinning (BILL-254 → BILL-259).** Each tier is now a TOML sub-table (`[tiers.huge]`) with `provider`, `model`, and optional `version` fields. The tier gate matches on model family and, when pinned, a dotted-prefix version match (`version = "4.8"` matches `claude-opus-4-8`; omitted version matches any). The old string form (`huge = "fable"`) is rejected with a migration message. All stage skills (`:design`, `:tickets`, `:run`) updated.
- **Router manifest and prices (BILL-254, BILL-255).** `manifest.json` schema with provider/auth/model validation; `prices.toml` with real Anthropic effective rates; `-prices` flag for override; embedded manifest with `-route` flag for provider-auth routing skeleton (BILL-256).
- **`$PREFIX` binding fix (BILL-216).** Ten skills were parsing `$PREFIX` from `key` (e.g. `iansmith/slopstop` → `iansmith`) instead of the `prefix` field. Fixed across all affected skills.
- **Custom headers newline quoting (BILL-210).** Three skills had broken `$'...\n...'` quoting in `ANTHROPIC_CUSTOM_HEADERS` examples.

### Fixed

- **Gzipped response metering (BILL-201).** The live D9 gate discovered the router was parsing gzip bytes as JSON, yielding zero tokens. Added `DecompressBody` to decode a private copy before usage extraction; client bytes are never touched.
- **`verify.sh` auth mode (BILL-211).** Originally hard-required `ANTHROPIC_API_KEY`; now works with subscription `/login` auth (the Desktop app path). Curl smoke is optional; the `claude -p` agent session is the real check.

## [3.0.0] — 2026-07-10

The v3 three-tier agent process, and the fixes that made its fleet actually run. Everything under "Added — the v3 process" landed on `master` after the `v2.5.0` tag and had never been released — anyone installing `slopstop@2.5.0` from the marketplace received a build in which `/slopstop:plan --ticket-driven` silently dropped its flag. This release ships it.

**On the major bump.** Strictly by the semver rule in `.claude/rules/repo-conventions.md` — "major for breaking changes (e.g., renamed plugin, changed install command shape)" — this would be a minor: no command was renamed and no install shape changed. `3.0.0` is a deliberate maintainer call marking the v3 process as the shipped product, and the recommended project layout moves with it (`.slopstop/` replaces the `~/.claude/` tracking defaults). Existing configs keep working; the old defaults still resolve.

### Added — the v3 process

- **`:design`, `:tickets`, `:run` (BILL-162 tree).** Stage 1 turns a grilled brain-dump into a PRD + feature charter and stops at gate G1. Stage 2 cuts an adversary-approved ticket tree and stops at G2. Stage 3 orchestrates a fleet of one-worktree-per-leaf agents with autonomous monitoring, adversarial handoff verification, and serial dependency-ordered integration, stopping at G-final.
- **`--ticket-driven` profile for `:plan`.** Checklist execution against a five-section leaf ticket: the file map is the territory, red tests are transcribed from the ticket's Test expectations, and a wrong ticket triggers a `TICKET UNDERSPECIFIED` halt instead of improvisation.
- **`[tiers]`, `[fleet.agents]`, `[fleet.monitoring]`, `[fleet.budget]`, `[fleet.router]` config tables.**

### Added

- **`archive_dir` top-level config key (BILL-181).** Where `:archive` moves a ticket's tracking dir at end of life. Resolves by the same rules as `tracking_dir` — relative from the main worktree root, absolute as-is — and defaults to `~/.claude/ticket-archive`. Previously the archive destination was hardcoded in `:archive`, `:document`, `:update-ticket`, and `:create-gh`, so a project-local tracking dir could not have a matching project-local archive.

### Fixed

- **The fleet agent brief was inert in a headless session (BILL-181).** `run-agent-brief.md` listed the agent's steps as bare `/slopstop:start …` slash text. A headless `claude -p` session has no `SlashCommand` tool, so those lines dispatched nothing. Observed at the default fleet tier (`haiku`): one agent replied `Waiting for /slopstop-start to complete…` and exited having done nothing; another skipped `:start` and `:plan` entirely and began writing code with no ticket transition, no tracking dir, and no red tests. The template now names each step as an explicit `Skill(skill="…")` tool call, declares that printing a step name is a failure, and forbids ending the turn between steps. Using the bare skill name also makes the brief namespace-agnostic (`slopstop:` vs `slopstop-`).
- **Fleet agents could not read their own tickets.** `:run`'s launch recipe used `--permission-mode acceptEdits`, which auto-approves file edits only — not `Bash`. Every ticket-system interaction the base process depends on (read, transition, comment, push) was denied. The recipe now uses `--permission-mode auto` plus a scoped `--allowedTools` grant, in preference to a blanket `bypassPermissions`.
- **A `tracking_dir` under `~/.claude/` silently fails for fleet agents.** `~/.claude` is a protected path: an agent's `Write` tool refuses it *even when* the session is launched with a matching `--add-dir`. Since a relative `tracking_dir` resolves from the main worktree root, it always lies outside an agent's worktree, so `:run` now passes `--add-dir <resolved tracking dir>` and CONFIG.md documents the protected-path trap. An agent denied its tracking dir was observed inventing a local `.local-tracking/` and carrying on.
- **`:run`'s launch recipe understated CLI support.** It prescribed `ANTHROPIC_MODEL=` and called effort advisory "where the CLI supports it". The CLI takes both `--model` and `--effort`, so launch effort is enforced. `design/slopstop-process.md` §1's caveat now says so, while keeping the true part: an adversary running `--inline` inherits its parent's launch effort.
- **The installers shipped `references/` verbatim, skipping the namespace rewrite.** Both `install-for-claude-desktop.sh` and its `-local` twin rewrote `slopstop:<name>` → `slopstop-<name>` in each `SKILL.md` but `cp`/`curl`'d the reference files unchanged. Harmless while references only *mentioned* command names in prose — but `run-agent-brief.md` now instructs a fleet agent to call `Skill(skill="slopstop:start")`, and in a commands install only `slopstop-start` resolves. References now go through the same `sed`. The brief additionally tells the agent to trust its own available-skills list over the brief's spelling.

### Changed

- **Merge policy is now stated, not implied.** `:merge` already defaulted to a real merge commit, but `CONFIG.md`, `README.md`, and `.project-conf.toml.example` all showed `merge_strategy = "squash"` in their examples. A squash collapses a branch's commits into one, so `git bisect` can no longer land inside the branch and reports an entire feature as the first bad commit. All examples now show `"merge"`, with the reasoning written down; `squash` and `rebase` remain available per-PR via `--strategy`.
- **`.slopstop/` is the recommended tracking layout**, replacing `scratch/tickets`: `.slopstop/ticket-active/` and `.slopstop/ticket-archive/`. Gitignore it.

## [2.5.0] — 2026-07-07

### Added

- **`QUICKSTART.md` and `slopstop-example` template repo (BILL-143).** A 15-minute hands-on quickstart guide walks a new user from zero to a merged PR on a real (broken) word-frequency CLI. Uses `github.com/iansmith/slopstop-example` as a GitHub template repo with three bugs baked in — covering `:start`, `:plan`, `:pr`, and `:merge` end to end. `docs/invite.md` added as a ready-to-paste invite message for sharing the quickstart link.

### Changed

- **RAG/Docker system fully removed (BILL-136, BILL-141).** slopstop is now skills-only — no Python service, no Docker image, no MCP server, no pgvector. The install story is now a single `/plugin install` command. `START-HERE.md` rewritten to reflect the leaner install. All stale refs swept from manifests, config example, `.gitignore`, design docs.

## [2.4.0] — 2026-07-06

### Added

- **`tracking_dir` config field (BILL-132).** Optional top-level key in `.project-conf.toml` that decouples per-ticket tracking files from the global `~/.claude/ticket-active/` directory. Three path shapes: absent or `~/.claude/ticket-active` → default behavior (no change); relative path (no leading `/` or `~/`) → resolved from the main worktree root via `dirname "$(git rev-parse --git-common-dir)"`, so worktree sessions and main-checkout sessions share the same tracking files; absolute path (starts with `/` or `~/`) → used as-is. All seven ticket-lifecycle skills (`:start`, `:plan`, `:update`, `:pr`, `:merge`, `:archive`, `:document`) read this field and resolve it to `$TRACKING_DIR` before constructing any ticket path. Backward-compatible — omitting `tracking_dir` is identical to today.

## [2.3.0] — 2026-07-05

### Added

- **`pr-repo` config field (BILL-130).** Optional field in `.project-conf.toml` that decouples the GitHub `owner/repo` used for PRs from the `key` field used for ticket lookup. When set, all five PR-touching skills (`:pr`, `:merge`, `:start`, `:document`, `:archive`) use `pr-repo` as `$OWNER/$REPO` instead of parsing from `key`. When absent, existing behavior is unchanged (backward-compatible). Required for JIRA/Linear projects (where `key` is a bare project key like `"PLTF"`) that push PRs to a GitHub repo. Example: `pr-repo = "iansmith/lyos"` paired with `system = "jira"`, `key = "PLTF"`.

## [2.2.0] — 2026-06-10

### Added

- **`/slopstop:search` skill — semantic ticket search and code-graph navigation.** Queries the local RAG service with a natural-language prompt and surfaces ranked ticket chunks. Two modes: `--tickets` (default, semantic search over the indexed corpus) and `--graph` (code-graph traversal — callers, implementors, blast radius of a symbol). Wraps the `search_tickets`, `get_callers`, `get_implementors`, and `get_blast_radius` MCP tools. Requires the rag container to be running.
- **`/slopstop:create-gh` skill — create GitHub issues from Claude Code.** Opens a new issue and assigns it the canonical `$PREFIX-N` ticket key (BILL-N = GitHub issue #N), so all lifecycle skills resolve the issue number without a mapping file. Handles key collisions with an alphabetic suffix (`BILL-Na`, `BILL-Nb`, …). GitHub-only; does not create a branch or transition the ticket — call `:start BILL-N` afterward.
- **`/slopstop:gh-init` skill — one-command GitHub project bootstrap.** Creates the required status labels (`status:in-progress` and optionally `status:in-review`), writes `.project-conf.toml` with `system`, `key`, `prefix`, and `[status_labels]`, and optionally installs the nightly harvest scheduler. `--workflow 3|4` and `--prefix PREFIX` flags skip the interactive questions. Idempotent — safe to re-run.
- **`/slopstop:update-ticket` skill — mid-flight ticket sync.** Pushes the current `task_plan.md` and `progress.md` state to the ticket while work is in progress, without closing the local lifecycle. Useful before handing off to a reviewer or resuming a ticket in a new session.
- **Adversary gap-finder in `/slopstop:plan` (Step 0f).** After the red-test phase, a parallel adversary agent attempts to find gaps in the proposed tests — scenarios the tests don't cover, boundary cases not expressed, integration paths not exercised. Findings are appended to `task_plan.md` under `## Adversary Findings` before the implementation plan is drafted. Configurable via `[autonomous] adversary = true/false`.
- **Slop-detection gate in `/slopstop:pr` (Step 2d).** Before opening the PR, a scan checks the diff for AI-generated slop patterns — boilerplate docstrings that restate the function signature, placeholder comments, over-specified type annotations on trivial code, and other markers. Gate is non-blocking by default; findings are surfaced as warnings. Configurable via `on_slop_findings` in the autonomous config.
- **GitHub GraphQL harvester (BILL-32).** Full GitHub Issues corpus sync for the ticket-rag service. Supports incremental sync (`sync_recent`) and full resync (`sync_all`) via the GitHub GraphQL API. Rate-limit handling is derived from GitHub's published limits; checkpoint/resume on interruption.
- **JIRA harvester (BILL-38).** JQL-based JIRA corpus sync with generator pagination, checkpoint/resume, and a `ComplexityBudget` leaky-bucket rate limiter. Keyed on `JIRA_API_TOKEN`.
- **Harvest scheduler (BILL-97, BILL-100).** `slopstop-schedule-harvest` installs a crontab entry for nightly corpus refresh. `gh-init` now asks whether to configure it (Step 10); the schedule is written to `[hooks] harvest_schedule` in `.project-conf.toml`. `design/cold-start.md` updated with examples.
- **SCIP code knowledge graph pipeline (BILL-54–59).** Indexes Go, Python, and TypeScript repos via `scip-go`, `scip-python`, and `scip-typescript` into an Apache AGE graph co-located with pgvector. Nodes: function definitions, modules, files. Edges: `CALLS`, `TOUCHES` (commit provenance), `IMPLEMENTS`. `slopstop-ingest` and `slopstop-install-hooks` binaries manage indexing; a PostToolUse hook design (`design/hooks-post-commit.md`) covers auto-reindex on commit (hook installation in BILL-96). MCP tools: `get_callers`, `get_implementors`, `get_blast_radius`, `get_code_context`, `get_ticket_code`.
- **Cyclomatic complexity on function-definition nodes (BILL-90 partial).** `lizard` is run at ingest time; CC scores are stored as a property on each function node. The `:pr` CC gate continues to run `lizard` on-demand; the graph now also persists the historical CC for graph-query-based gates (BILL-84, BILL-89 pending).
- **Autonomous mode.** Add `[autonomous] enabled = true` to `.project-conf.toml` to suppress interactive prompts across all skills. Individual behaviors (`adversary`, `on_slop_findings`, `archive_immediately`, etc.) are configurable sub-keys. Designed for CI / benchmark use.
- **CodeRabbit vs Claude review backend (BILL-61).** `/slopstop:pr` now reads `[review] backend = "coderabbit"|"claude"` from `.project-conf.toml`. The `"claude"` path runs an inline `/code-review` pass and posts findings as PR comments without polling an external bot.
- **`pr-remote` and `origin-remote` config (BILL-76).** Multi-remote repos (e.g. fork + upstream) can declare `[git] pr_remote = "upstream"` and `origin_remote = "fork"` in `.project-conf.toml`. `:start`, `:pr`, and `:merge` thread these values through so pushes and PR creation always target the right remote.
- **`slopstop-example` companion tutorial repo.** `github.com/iansmith/slopstop-example` — a forkable example project that walks a new user through the full slopstop lifecycle on a CLI calendar program. Covers all lifecycle commands, the CC gate (intentional complexity trap in the date-parser part), and both installation paths (CLI marketplace and Desktop curl script).
- **Skills refactored to spine + `references/` pattern (BILL-85, BILL-91).** Each skill's `SKILL.md` is now a lean spine (≤ 350 lines); verbose sections are extracted to `references/*.md` and read on demand. Context window cost per invocation drops significantly on complex skills (`:pr`, `:plan`, `:merge`). Behavior is unchanged; the extracted files ship alongside `SKILL.md` in the plugin and the Desktop installer.

### Changed

- **`:merge` now runs `:update` + `:document` before closing.** Step 4 (formerly "Advance ticket state") is preceded by a `:document` delegation that pushes the current task plan and DoD-confirmation comment to the ticket. This ensures the ticket always has up-to-date documentation at the moment the PR merges, regardless of whether the user ran `:document` manually. The `:update` step also fires (syncing `progress.md` to the ticket) before state transition.
- **`:archive` simplified to file-lifecycle only.** The documentation push logic (previously inlined as Steps 4a–c) is no longer in `:archive` — it was moved to `:document` in v2.1.0 and `:archive` now delegates to it; with `:merge` also delegating to `:document`, `:archive` at terminal time is typically a no-op push (idempotent skip) plus the local tracking move. `:archive` remains the correct command to close the local lifecycle; the documentation state is just already current by then.

### Fixed

- **`plugin.json` license field corrected to `CC-BY-SA-4.0`.** The source license was changed to CC BY-SA 4.0 in a prior commit but `plugin.json` still declared `"license": "MIT"`. Fixed.

### Notes

- The three new skills (`:search`, `:create-gh`, `:gh-init`) and the renamed `:update-ticket` are included in the Desktop installer (`install-for-claude-desktop.sh`). Desktop users should re-run the installer after upgrading.
- BILL-96 (PostToolUse hook wiring for auto-reindex) is still open; the design is complete but `bin/post-commit-reindex.sh` and the `gh-init` hook step are not yet shipped. This does not affect the core workflow skills.

## [2.1.0] — 2026-06-03

### Added

- **GitHub Issues as a first-class ticket system.** `system = "github"` in `.project-conf.toml` is now fully supported across all lifecycle skills (`:start`, `:document`, `:archive`, `:merge`). Workflow state is label-based: a `[status_labels]` table declares the in-progress and (optional) in-review labels. Two workflow shapes are supported — 3-state (`Todo → In Progress → Done`) and 4-state (`Todo → In Progress → In Review → Done`). See `design/cold-start.md` §7 for setup.
- **`.project-conf.toml` replaces `.project-prefix`.** The configuration file is now a TOML file at the repo root with `system`, `key`, and `prefix` fields. All skills read this file; the old single-line `.project-prefix` format is superseded. See `design/project-conf-toml.md` for the full schema.
- **`:merge` migrated to MCP-preferred + `gh` CLI fallback for all PR operations.** Step 1 now detects the GitHub PR backend (canonical `mcp__github__*` → plugin-ns `mcp__plugin_github_github__*` → CLI) and uses `list_pull_requests` + `pull_request_read` for PR resolution, `merge_pull_request` for the merge, and `pull_request_read` for post-merge verification. `gh auth status` pre-flight is now conditionalized to the CLI path only.
- **`design/github-backend-primitives.md` — PR-level MCP primitives.** New section documents all PR-level MCP tools with exact parameter names, the `owner:branch` format for `list_pull_requests`, the remote-branch deletion gap for `merge_pull_request` (no `delete_branch` parameter), the `create_pull_request` 403 limitation on the Anthropic plugin's PAT scope, and the CodeRabbit in-place-edit trap with the three-condition completion gate.
- **`gh auth status` conditionalized.** Pre-flight auth checks in `:merge` and `:doc-sync` now run only when `$GH_BACKEND = "CLI"`. When using the GitHub MCP, no `gh` binary is required for auth.
- **`START-HERE.md` at repo root.** A copy of `design/cold-start.md` placed at the repo root for immediate discoverability when new users land on the repo.
- **`/slopstop:doc-sync` documented in README.** The design-doc mirroring skill is now listed in the commands section alongside the lifecycle skills.
- **Workflow shape section in README and cold-start.** A new section explains the 3-state vs 4-state requirement for JIRA/Linear projects and the options for teams with longer workflows.
- **CodeRabbit polling: in-place-edit trap documented.** `design/github-backend-primitives.md` §CodeRabbit polling now explicitly documents the incremental re-review behavior (walkthrough edited in place, not a new comment) and the three-condition completion gate (`walkthrough marker ∧ HEAD_SHA in body ∧ not "currently processing"`). The `:pr` skill's existing polling loop already implemented this correctly; the design doc now matches.

### Changed

- **README rewritten** for accuracy: `.project-prefix` → `.project-conf.toml` throughout; GitHub Issues added; `gh` CLI status updated to optional (required only for CodeRabbit polling and `gh pr create` MCP-403 fallback); GitHub MCP namespaces corrected; `doc-sync` command added; storage layout updated; compatibility section lists all three GitHub backend variants.

### Known gaps (deferred to follow-up ticket)

- **`:pr` skill not yet migrated to MCP-preferred.** `gh pr create`, `gh repo view --json defaultBranchRef`, and the open-PR pre-flight check still use `gh` CLI. The design for the migration is in `design/github-backend-primitives.md`; implementation is deferred. `create_pull_request` via MCP requires special handling (403 on Anthropic plugin PAT scope → must fall back to CLI rather than stopping).

## [2.0.0] — 2026-05-29

### Rebranded — `ticket-plugin` → `slopstop`

- **The project, plugin, and marketplace are renamed from `ticket-plugin` to `slopstop`.** The GitHub repo moves from `iansmith/ticket-plugin` to `iansmith/slopstop`; the plugin manifest `name`, the marketplace `name`, and the marketplace `source.repo` all become `slopstop`. The `BILL` ticket prefix is unchanged.
- **Command names change.** CLI (namespaced) commands go from `/ticket-plugin:<verb>` to `/slopstop:<verb>` (e.g. `/slopstop:start`, `/slopstop:plan`). Claude Desktop (un-namespaced) commands go from `/ticket-<verb>` to `/slopstop-<verb>` (e.g. `/slopstop-start`), and the desktop installer now writes `slopstop-*.md` files into `~/.claude/commands/`.
- **Migration for existing users.** Marketplace installs need to re-point at the new repo: `/plugin marketplace remove ticket-plugin`, then `/plugin marketplace add iansmith/slopstop` and `/plugin install slopstop@slopstop`. GitHub redirects the old `iansmith/ticket-plugin` URLs (best-effort) so existing clones and `raw.githubusercontent.com` install URLs keep working, but everyone should move to the new slug. Desktop users re-run the installer and remove the old `~/.claude/commands/ticket-*.md` files.
- **Docker image renamed.** The RAG-service container image is now tagged **`slopstop-rag`** (was `ticket-plugin/rag`). `make rag-build` produces `slopstop-rag:latest` and `slopstop-rag:<git-sha>`; on a pull or in `docker images` it shows as `slopstop-rag`. On a registry push it would publish as `<namespace>/slopstop-rag`.
- **Unchanged on purpose.** The `BILL` ticket prefix; the runtime state directories `~/.claude/ticket-active/` and `~/.claude/ticket-archive/` (concept-named, shared across every project that uses the plugin); the domain terms `ticket-rag`, `ticket_chunks`, `ticket-doc-sync`; the `rag-service` Python package name.
- **Why:** rebrand to a distinct product name. Per the release checklist in `.claude/rules/repo-conventions.md`, a plugin rename / changed install-command shape is a **MAJOR** bump, so this ships as `2.0.0`. The feature work previously earmarked for `1.3.0` (never tagged) is folded into this release — the entries below are listed under their new `/slopstop:` command names.

### Added

- **Client-readable Definition of Done.** `/slopstop:plan` Step 2a now drafts a `## Definition of Done` section in `task_plan.md` above the technical Plan. The DoD uses plain language and observable outcomes (not test names or code symbols), aimed at the non-engineer who filed the ticket. Items describe *what the client will observe* and include a `How to verify:` line a non-engineer could execute. The DoD ends up at the top of the ticket description on archive — it's the first thing the client sees when reading the closed ticket.
- **DoD-confirmation comment on archive.** `/slopstop:archive` now posts a separate timestamped comment to the ticket after updating the description. The comment walks each DoD item from `task_plan.md` and confirms it with evidence (Phase 0 red tests that turned green, commits implementing the work, the merged PR, manual verification notes captured in `progress.md`). Each item is marked ✅ if evidence supports it, ⚠️ with a plain-language reason if it doesn't. Never fakes a confirmation — surfaces the gap honestly when evidence is missing. The result: a ticket on close has scope agreement at the top of the description (the DoD), engineering artifacts below (the plan, original description), a timestamped sign-off comment (the DoD confirmation), and an investigation comment (findings). Skipped entirely if `task_plan.md` has no DoD section.
- **`/slopstop:start` now creates the feature branch.** Previously fresh-start was strictly hands-off git ("Does NOT touch git. The user manages branches"); the user had to `git switch -c <name>` themselves before running `:plan` or `:pr`, both of which only validated they weren't on `main`. Branch naming was ad-hoc — typically whatever Linear's `gitBranchName` suggested (e.g. `ianster/lou-142-css-text-decor-regression`), which neither encodes the change type nor reads cleanly in `git log`. Fresh-start now: (1) infers a Conventional-Commits-style type prefix (`fix`/`feat`/`chore`/`docs`/`refactor`/`perf`/`test`/`ci`/`build`/`deploy`/`revert`) from the ticket's labels and title via a small heuristic table; (2) asks the user for the type, showing the heuristic suggestion when one exists, with `<custom>` (any string that passes `git check-ref-format`) and `skip` (opt out of branch creation entirely) always available; (3) determines the base ref — if cwd is on the repo's default branch, branches off `origin/<default>` cleanly; if cwd is on a non-default branch, warns explicitly and asks whether to base off `origin/<default>` (typical) or off the current branch (intentional stacking on a feature branch); (4) reuses an existing local or remote branch of the same name if found, rather than failing; (5) records the outcome in `progress.md` and the start-line summary. The result: every PR's branch reads `<type>/<TICKET-ID>` from the first commit. No rename-and-force-push later in the lifecycle. `skip` preserves the old hands-off-git behavior verbatim for sessions that don't want git side effects.
- **New `/slopstop:document` skill.** Pure remote-sync command that pushes the local task plan + DoD-confirmation comment + findings comment to the ticket on Linear/JIRA, **idempotently and safely**. Per-artifact classification against the ticket's current managed state (recognized by content signatures: the `## Original description (preserved)` marker in the description body, the `## Definition of Done — Confirmation` comment title, the `## Findings (from local tracking)` comment title): `new` artifacts are pushed; `unchanged` artifacts are silently skipped (running `:document` twice on unchanged local state is a clean no-op); `divergent` artifacts trigger an **all-or-nothing safety stop** — the skill prints a per-artifact diff and refuses to push any of the three. `--force` overrides the stop and pushes anyway (with a warning in the summary about stale comments left behind if the MCP can't edit-in-place). `--dry-run` shows what would happen without making remote calls. Comparison uses loose-normalize (collapse whitespace + strip the dynamic DoD timestamp), tolerating Linear/JIRA's markdown re-rendering. Does NOT change ticket state, does NOT touch local tracking, does NOT clear `CURRENT-<PREFIX>` — pure sync, callable at any point in a ticket's life. **The headline use case is the `In Review` workflow gate** for teams where the reviewer of `In Review` reads the *ticket* (not just the PR) alongside their PR review — to understand what's being shipped, what the agreed scope was, what the DoD criteria are. Without `:document`, the ticket may still hold only the original problem statement when that reviewer opens it. The natural sequence becomes `:merge` (code shipped, ticket → `In Review`, no docs pushed) → `:document` (now the reviewer has something to review against) → reviewer advances the ticket to a terminal state → `:archive` (close the local lifecycle; `:archive`'s inlined `:document` is typically a no-op at this point because docs are already current).
- **Linear harvester for the ticket-rag service (BILL-37).** New `rag_service/harvesters/` package. Builds the harvester-agnostic ingestion spine `_common.py` (to be reused by the GitHub harvester, BILL-32): normalized `HarvestedTicket`/`HarvestedComment`/`ChunkRow`, code-fence stripping with `code_refs`/`ticket_refs` extraction, logical chunking with a seq-band scheme (description chunks `0..0xFFF`, comments from `0x1000`; oversized descriptions split on paragraph boundaries with single-unit overlap, code fences never split mid-block), the full-resync `write_ticket` (DELETE-then-INSERT scoped by `source`/`ticket_id`/`provenance`), and two rate limiters — `RateLimiter` (request count) and `ComplexityBudget` (a leaky-bucket point budget). `linear.py` adds the `LinearClient` protocol + `LinearGraphQLClient` over httpx (`sync_ticket` / `sync_recent`), prefix→team resolution, and a `click` CLI keyed on `LINEAR_API_KEY`. Rate-limit handling is derived against Linear's **real published limits** ([linear.app/developers/rate-limiting](https://linear.app/developers/rate-limiting)): 2,500 requests/hr AND 3,000,000 complexity-points/hr, a 10,000-point single-query cap (batch size 40), reconciliation against the `X-RateLimit-Complexity-Remaining` response header, and HTTP-400 `RATELIMITED` detection with exponential backoff. This also corrects `design/ticket-rag.md`'s prior Linear rate-limit figures — the earlier "1,500 req/hr; 30 batches/hr" was wrong on both the number and the binding dimension (complexity points, not request count, bind the batched `sync_recent` path). Unit tests use a `FakeLinearClient` + `httpx.MockTransport` (no live API, no postgres, no model weights); the Docker integration gate `verify-bill37.sh` has an always-on structural tier and a live "dogfood" tier gated on `LINEAR_API_KEY`.

### Changed

- **`/slopstop:merge` no longer archives local tracking or pushes to the ticket.** Previously `:merge` inlined `/slopstop:archive`'s body as its final step — pushing the task plan to the ticket description, posting the DoD-confirmation + findings comments, moving the local tracking dir to `~/.claude/ticket-archive/`, and clearing `CURRENT-<PREFIX>`. Now `:merge` stops after merging the PR + advancing the ticket one state + cleaning up the branch. `~/.claude/ticket-active/<TICKET>/` stays put, `CURRENT-<PREFIX>` still points at the ticket, and `/slopstop:archive` is the user's separate, explicit follow-up. **Why:** `:merge` advances the ticket by one workflow state (e.g. In Progress → In Review), which on most teams is *not* terminal — QA / review still has to verify. Pushing the task plan as the description while QA is mid-flight is premature, and moving the local tracking dir out of `ticket-active/` while the dev is still on call for QA fallout loses the per-ticket context. The two operations are now properly separable: `:merge` ships the code, `:archive` ships the record once the work is truly done.
- **`:merge`'s Step 7 (renamed from "Confirm" to "Confirm and recommend next step") classifies the post-transition state and tells the user when to run `/slopstop:archive`.** Five branches: (A) ✅ advanced into a terminal Done-type state — recommend `:archive` now; (B) ⚠️ advanced into an intermediate state (e.g. "In Review") — warn explicitly that `:archive` should wait until QA/review reaches a terminal state; (C) ✅ ticket was already terminal before the merge — recommend `:archive` now; (D) ⏸ no forward transition was available on the workflow — neutral note ("when ready, transition manually first"); (E) ⏸ user picked `merge-only` — same neutral note. Terminal-state classification: JIRA `statusCategory.key === "done"`, Linear `state.type === "completed"`. Uses the data Step 2 already fetched; no new ticket-system call.
- **`merge-only` in Step 3 now also skips the branch-cleanup step.** Previously `merge-only` meant "do `gh pr merge` only" but the SKILL.md's description and the rest of the flow were slightly inconsistent about whether non-origin-remote propagation and local-branch deletion happened on that path. Now `merge-only` is unambiguous: only `gh pr merge` runs; nothing else is touched — ticket state, non-origin remotes, local branch, and local tracking all stay where they were.
- **`/slopstop:archive` refactored to delegate the documentation push to `/slopstop:document`.** Step 4's three sub-steps (4a description update, 4b DoD-confirmation comment, 4c findings comment) — ~70 lines of inline push logic — are replaced by a single delegation paragraph. The full push logic, evidence-gathering format, and divergence detection now live in `skills/document/SKILL.md`; `:archive` calls into it from Step 4 and adds the terminal-state gate (Step 2) + local-tracking move (Step 5). Notable behavior addition: `:archive` now inherits `:document`'s idempotent skip-when-current and divergence-stop safety. If managed documentation on the ticket differs from what would be pushed (someone hand-edited, another session pushed an alternative version), `:archive` stops cleanly without moving the local tracking dir — the user runs `/slopstop:document --force` separately to overwrite (after eyeballing the diff), then re-runs `:archive`. `:archive` itself does NOT support `--force`; the friction is intentional, since archive is the irreversible end of the local lifecycle.

### Fixed

- **`/slopstop:pr` poll loop false-negative on zero-findings CodeRabbit runs.** Step 6's break condition was `inline_count > 0 OR review_count > 0`. CodeRabbit's zero-findings path posts neither — it updates the issue-comment walkthrough with a completion marker — so the loop ran the full 15 iterations on every clean PR. Now the loop also breaks when an issue-comment from `coderabbitai[bot]` contains one of `"Summary by CodeRabbit"`, `"No actionable comments"`, or `"Actionable comments posted:"` — those are markers CodeRabbit writes only on a completed review run, not on the initial "I'm reviewing this…" acknowledgement, so the early-trigger failure mode is avoided. Step 7 grows a 7-pre / 7d-clean fast path that short-circuits the verify-and-classify loop when there's nothing to classify and prints a clean ✅ verdict instead.

### Notes

- `plugin.json` is bumped to `2.0.0` for this release. The previously-planned `1.3.0` was never tagged; its changes ship here under the new name.
- **Breaking change for anyone scripting around `:merge`'s side effects.** Prior to this change, `:merge` guaranteed the local tracking dir was moved to `~/.claude/ticket-archive/` and the ticket description was updated by the time it returned. Scripts or muscle-memory that assumed those side effects need to add an explicit `/slopstop:archive` call (at the point in the workflow where the ticket actually reaches a terminal state). Hence the minor version bump rather than a patch.
- **Behavior change for `:start` users on workflows that already manage branches manually.** Fresh-start now prompts for a branch type and (when cwd is on a non-default branch) for a base ref. The `skip` choice in the type prompt reproduces the old hands-off-git behavior exactly, so existing scripts can opt out by piping `skip` to the prompt. Sessions that don't want any new prompts at all are not currently supported via a flag — if that becomes a pain point, a `--no-branch` flag could be added in a future release.

## [1.2.0] — 2026-05-19

### Changed

- **`/ticket-plugin:merge` no longer auto-transitions tickets to Done.** The skill now advances the ticket by **one state** in the workflow, respecting intermediate states like "In Review" or "Awaiting QA" that many teams put between In Progress and Done. The previous behavior (jump straight to a Done-category state) skipped those gates, which is wrong for most real teams. This is a behavior change to the default flow — hence the minor version bump rather than a patch.
- The Step 3 confirmation prompt now shows the **specific computed next state** (e.g. `"In Progress → In Review"`) rather than the vague `"to a terminal Done state"`. If the proposed target isn't what the user expected, they can say `no` and handle the transition manually.
- Computation logic in Step 2 (was: in Step 5):
  - **JIRA:** `getTransitionsForJiraIssue` → exclude negative-completion names (`won't do`, `cancel`, `reject`, `abandon`, `invalid`, `duplicate`) → prefer transitions that stay in the **current** `statusCategory.key` (sideways "In Progress" → "In Review" preferred over the category jump to "Done") → within those, prefer name match `/review|qa|verify|test|pending|ready|merged|shipped/i`. Only falls back to a category-advancing transition (and then preferred-Done picking) when no same-category target exists.
  - **Linear:** `list_issue_statuses` → filter out `type === "canceled"` and negative names → prefer states with the **same** `type` and a higher `position` (the immediate next slot in the same bucket) → if none, advance type to `completed` with the lowest position. Same name preferences as JIRA.
- The semantics also clean up a related asymmetry: `/ticket-plugin:archive` continues to refuse non-terminal tickets, but `/ticket-plugin:merge` (which inlines parts of `:archive`'s push + local-mv logic, NOT the terminal gate) may legitimately leave the ticket in a non-terminal state on the ticket system while still archiving the local tracking dir. The local archive captures "dev's work is done"; the ticket's final state is whatever the team's workflow + QA process produces.

### Also changed

- Moved the repo-maintainer release checklist from `CLAUDE.md` at the root to `.claude/rules/repo-conventions.md`. The plugin validator warns about `CLAUDE.md` at a plugin root (it assumes the file is trying to ship context to plugin users, which doesn't work). Our use case is the opposite — repo conventions for maintainers — and `.claude/rules/` is the right home for that. Claude Code auto-loads both `CLAUDE.md` and `.claude/rules/*.md` at session start, so the behavior is identical; only the file location changed.

### Notes

- If your team's workflow happens to have no intermediate state between In Progress and Done, advance-one IS Done — because that's what your workflow's "next" actually is. The skill doesn't enforce intermediate states; it just doesn't assume them.
- README updated: the workflow diagram, the `:merge` command description, the `:merge` vs `:archive` distinction, and the fictional scenario walkthrough all reflect the new advance-one semantics.

## [1.1.2] — 2026-05-19

### Fixed

- `marketplace.json`'s `plugins[0].source` was set to `"."` (bare-dot relative path), which `claude plugin validate` rejects with `plugins.0.source: Invalid input`. The schema requires either a subdirectory path starting with `./` (e.g. `"./plugins/foo"`) or an object form with a recognized `source` type. Since this repo IS the plugin (no subdirectory), switched to the `github` object form pointing at the same repo:
  ```json
  "source": {
    "source": "github",
    "repo": "iansmith/ticket-plugin"
  }
  ```
  Users adding the marketplace via `/plugin marketplace add iansmith/ticket-plugin` now resolve the plugin from the same repo (default branch). v1.1.0 and v1.1.1 had an unusable `marketplace.json` for the self-hosted install path described in README — this fix unbreaks it.

### Added

- `CLAUDE.md` at the repo root with a release checklist (validate, bump version, update CHANGELOG, never force-move tags), plugin format reference, authoritative docs links, distribution-path table, and repo workflow conventions. Travels with the repo so future Claude sessions, contributors, and Anthropic reviewers see it.

## [1.1.1] — 2026-05-19

### Changed

- `plugin.json` polish for marketplace submission. Added five optional manifest fields recommended by Anthropic's plugin schema: `$schema` (JSON schema URL for editor autocomplete), `displayName` (human-readable name shown in `/plugin` picker — set to `"Ticket Plugin"`), `repository` (source URL — separate slot in the manager UI from `homepage`), `license` (declared as `"MIT"`, matching the LICENSE file), and `keywords` (`["linear", "jira", "ticketing", "productivity", "tdd", "code-review", "agents"]` for discoverability). Mirrored the polished description into `marketplace.json` so self-hosted-marketplace consumers see the same text.
- No functional changes. Skill behavior, slash command set, install path, and tracking-file format are identical to v1.1.0.

## [1.1.0] — 2026-05-16

### Added

- `/ticket-plugin:plan [constraint]` — investigate the codebase against the ticket's outcome (scoped literally by the optional textual constraint), then write a thorough, parallelism-aware plan into `task_plan.md`. **Phase 0 — red tests first**: identifies the project's test command (auto-detects from `Taskfile.yml` / `Makefile` / `package.json` / `Cargo.toml` / `go.mod` / `pyproject.toml`, or asks once and caches the answer in `task_plan.md`), then writes failing tests for the **expected** behavior from the ticket description (not for the current implementation). Runs them; expects RED. If they unexpectedly pass on the current code, surfaces this and offers `revise / continue / abort` — the bug may already be fixed or the tests aren't exercising the right behavior. Commits the red tests as a separate `[$TICKET] Phase 0: red tests` commit, anchoring the rest of the plan's `Done when` criteria to "test X turns green". Then proceeds with investigation (uses the `Explore` subagent), drafts the plan with detailed work items (files, dependencies, parallel-safety, concrete sub-steps, test-anchored Done-when), and an explicit parallelism analysis. When 2+ items are parallel-safe, optionally fan them out across subagents in `Agent(isolation: "worktree")` worktrees with a strict per-agent prompt (worktree-only constraint, fork from known base SHA, frequent small commits). Monitors via the `Monitor` tool on a 15-minute cadence; auto-stops hard-stuck agents (≥60 min without commits AND ≥3 repeating errors in recent output) — single-condition signals flag but don't auto-stop. After all agents finish, offers auto-merge with confirmation in dependency order (stops cleanly on first conflict; user picks subset). Plan is always written to disk before agents launch, so any later abort still leaves the user with a usable plan.
- `/ticket-plugin:pr` — open a pull request for the active ticket's branch with pre-commit simplify + tests + CodeRabbit polling. Runs Claude Code's `simplify` skill on uncommitted changes (surfaces any changes for user approval), then **runs the project's tests** using the same test-command discovery logic as `/ticket-plugin:plan` (read from `task_plan.md` if cached, else auto-detect, else ask once). Test failures refuse the commit by default with a `fix / commit anyway / abort` prompt; `--no-test` overrides. On green: generates a ticket-anchored commit message, pushes, opens the PR via GitHub MCP or `gh` CLI, triggers CodeRabbit if the PR's base isn't the repo default (`@coderabbitai review`), polls for substantive CodeRabbit feedback every 60 seconds for up to 15 minutes, and categorizes inline comments into 🔴 should-fix / 🟡 could-fix / ⚪ skip with reasoning. Stops after presenting — never auto-applies CodeRabbit suggestions.
- `/ticket-plugin:merge` — end-to-end "ship it" command that combines the four steps you'd otherwise do by hand at the end of a ticket: merges the PR via `gh pr merge` (default strategy: squash), transitions the ticket to a Done-category state on Linear/JIRA, propagates the merged-onto branch to all configured remotes, deletes the local branch (after `gh pr view` confirms `state: MERGED` — squash and rebase strategies work, not just merge-commit), and inlines the body of `/ticket-plugin:archive` to push the final task plan + findings comment and archive locally.
- Confirmation contract: `/ticket-plugin:merge` prompts exactly once before any destructive remote action and offers `yes` / `no` / `merge-only` (merge the PR only, leave ticket + local tracking untouched).
- Safety gates: refuses on dirty working tree, unpushed commits, no upstream, draft PR, merge conflicts, mismatched `headRefName`, or no open PR for the current branch. Soft warnings (BLOCKED / BEHIND / failing checks / no review approval) are surfaced in the confirmation prompt but allow the user to proceed.
- Multi-remote propagation: after `gh pr merge`, the merged-onto branch is pulled locally and then pushed to every remote besides `origin` (mirrors, upstream forks, etc.). Best-effort — a failed push to a non-origin remote warns but doesn't abort.
- Positive-completion heuristic for both ticket-system transitions, applied symmetrically:
  - **JIRA:** filters `done`-category transitions to exclude `Won't Do`, `Canceled`, `Rejected`, `Abandoned`, `Invalid`, `Duplicate` so the ticket lands on a real Done (not a terminal-but-negative state) even if the workflow has many done-category options.
  - **Linear:** filters `type === "completed"` states (which already excludes Linear's `canceled` type) and *also* gates by name against the same negative-completion regex, since teams sometimes misconfigure workflow types.
  - In both cases the selection order is: exact `Done` name match → partial positive-completion words (`done|merged|shipped|complete|fixed|closed|resolved`) → first remaining. If nothing remains after exclusion, the command warns and continues without transitioning (the merge already happened; the user can fix the workflow manually).
- Optional `--pr <N>` and `--strategy <squash|merge|rebase>` arguments on `:merge`.
- Optional `--base <branch>`, `--no-simplify`, and `--no-poll` arguments on `:pr`.

### `:plan` specifics

- **Phase 0 is mandatory** unless the user explicitly says `skip` when asked for the test command. The Step-2 plan's `Done when` criteria are anchored to "named red test turns green" rather than prose assertions — without Phase 0, work items lose their objective verification.
- **Test command is shared between `:plan` Phase 0 and `:pr`'s pre-commit gate** via a `**Test command:**` line cached at the top of `task_plan.md`. Setting it once works for both skills going forward.
- **Three explicit confirmation gates**: clean-tree-before-fanout (Step 4 — offers `commit` / `stash` / `abort`), launch-agents (Step 6), auto-merge (Step 9). The user can abort at any of them, and the plan is on disk by then.
- **Argument scope is literal**: `/ticket-plugin:plan focus on the database layer` excludes everything outside the database layer from BOTH the investigation and the resulting plan, even if the ticket text implies it. The constraint is recorded at the top of the Plan section so a future reader knows what was deliberately left out.
- **Investigation offloads to `Explore` subagent** when available (keeps the orchestrator's context clean); falls back to inline `Grep`/`Glob`/`Read` if Explore is unavailable.
- **Per-agent prompts include**: their slice of the plan verbatim, the relevant findings, hard constraints (worktree-only, fork from `$BASE_SHA`, no `/ticket-plugin` invocations, no pushes), a 3–10 commit cadence target with `[$TICKET]` prefix, completion-on-done (no scope creep), and instructions to commit-and-stop on a real dead end.
- **Monitor heuristics**: status line per agent per tick shows commit count, minutes since last commit, and warning flags. Auto-stop requires BOTH ≥60 min no commits AND ≥3 repeating error patterns in recent task output. Single-condition signals are surfaced as `[warn: ...]` flags without action — the user decides.
- **Auto-merge runs in dependency order** built from the plan's `Depends on` graph: `git merge --no-ff <agent-branch>` for each, stopping cleanly at the first conflict (which the user resolves manually before continuing). Never uses `--force`, never bypasses hooks.
- **Soft cap of 4 parallel agents** with a `merge`/`proceed`/`abort` prompt above that. Monitoring more than 4 agents in parallel is hard for a human to track meaningfully.

### `:pr` specifics

- **Pre-commit test gate** (Step 2 — between simplify and commit): identifies the project's test command using the same logic as `/ticket-plugin:plan` Phase 0 (read from `task_plan.md` cached value, else auto-detect, else ask once). Test failures refuse the commit by default with a `fix / commit anyway / abort` prompt. `--no-test` bypasses the gate entirely. When the user picks `commit anyway`, the commit body gets a `Note: <N> test(s) failing at commit time` line so the failing state is visible in the git log.
- **GitHub backend probing**: prefers a `mcp__github__*` MCP if installed, otherwise falls back to the `gh` CLI. For the CLI path, resolves the binary by checking `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `$PATH` — first hit wins.
- **CodeRabbit trigger**: posts `@coderabbitai review` as a PR comment if and only if the PR's base branch isn't the repo's default (CodeRabbit auto-runs on default-branch PRs; the comment is required to trigger it on stacked PRs targeting non-trunk branches).
- **Polling contract**: ignores CodeRabbit's "walkthrough"/acknowledgement comments. Substantive signal is non-zero inline review comments at `pulls/{N}/comments` OR a finalized review (`state ∈ {CHANGES_REQUESTED, APPROVED}`) at `pulls/{N}/reviews`. 15-minute timeout returns gracefully without analysis.
- **Categorization is grounded in mandatory verification** (Step 6): before classifying any inline comment, the skill reads the actual code CodeRabbit is commenting on and verifies CodeRabbit's premise against the source (e.g. greps for "unused" symbols, checks type signatures for "nullable" claims, confirms async-ness for "missing await" claims, checks neighboring files for "use idiom Y" claims). A false premise short-circuits to ⚪ Skip — the skill never classifies a comment as Should/Could when CodeRabbit's underlying claim about the code is wrong.
- **Classification follows an ordered decision tree** (not parallel bucket descriptions): (1) fixes bug/security/data-loss/runtime-crash → 🔴 Should; (2) contradicts established codebase pattern → ⚪ Skip (codebase wins); (3) clear positive-ROI improvement → 🟡 Could; (4) pure stylistic nit with no functional benefit → ⚪ Skip; (5) otherwise → 🟡 Could (default to optional, not ignore).
- **Output quotes CodeRabbit's actual words** for each item so the user can sanity-check the classification against the source comment, plus a short "Verdict" and "Why" (the Why field surfaces any verification the skill did).
- **Never auto-applies suggestions** — Step 6 stops at presentation; user explicitly opts in to apply.

### Notes

- Does NOT use `gh pr merge --admin` or any other branch-protection-bypass mechanism. If the PR is blocked, the user resolves the blocker themselves.
- Neither `:pr` nor `:merge` uses `git push --force`, `git commit --no-verify`, or `git reset --hard`. None of these have a place in either flow.
- Failure handling for `:merge`: pre-flight or merge-call failures stop with no state changed. Ticket-system and archive failures after the merge are surfaced but don't roll back the merge (it's already irreversible) — the user can re-run `/ticket-plugin:archive` later to recover.
- Failure handling for `:pr`: pre-flight, simplify-abort, commit-hook, and PR-creation failures all stop cleanly. CodeRabbit poll timeout is not a failure — the skill prints a notice and continues to the summary without analysis.

## [1.0.0] — 2026-05-16

### Added

- Initial public release.
- Four slash commands invoked under the `ticket-plugin` plugin namespace:
  - `/ticket-plugin:start <KEY>` — fresh-start or resume work on a ticket. Fresh-start fetches the ticket, transitions it to **In Progress**, and seeds `task_plan.md`, `findings.md`, `progress.md`. Resume reads the tracking files and prints a summary.
  - `/ticket-plugin:update` — mid-session checkpoint to `progress.md`. The ticket stays active. Local-only.
  - `/ticket-plugin:pause` — snapshot state and clear the active-ticket pointer. Local-only.
  - `/ticket-plugin:archive` — push the final task plan back to the ticket as its description, post `findings.md` as a comment, and archive the local folder. Refuses unless the ticket is already in a terminal state on the ticket system.
- Auto-detection of ticket system (JIRA via Atlassian MCP, or Linear via Linear MCP). If both are configured in the same session, the skill asks rather than guessing.
- Per-project `.project-prefix` discipline: a single-line file in cwd names the ticket prefix (`MAZ`, `PLTF`, `LOU`, etc.) for that project. Skills only operate on tickets matching the cwd's prefix.
- Per-prefix `CURRENT-<PREFIX>` pointer (`~/.claude/ticket-active/CURRENT-MAZ`, etc.) lets parallel sessions on different projects work without interference.
- Tracking files live at `~/.claude/ticket-active/<TICKET>/` while active and move to `~/.claude/ticket-archive/<TICKET>/` on archive. Independent of any git repo.

### Also included

- `install-for-claude-desktop.sh` — bash installer for Claude Desktop users, since Claude Desktop doesn't yet support `/plugin install`. Drops the four commands into `~/.claude/commands/` as `/ticket-start`, `/ticket-pause`, `/ticket-update`, `/ticket-archive` (un-namespaced — Claude Desktop loads them as standalone slash commands). The installer strips the SKILL.md YAML frontmatter and rewrites cross-references from `/ticket-plugin:<name>` to `/ticket-<name>` to match the standalone invocation form.
- `PRIVACY.md` — explicit statement that the plugin collects nothing about the user or their usage, with a transparency note about what other tools (Anthropic's Claude API, the Linear / Atlassian MCPs) the slash-command invocations naturally hit.
- README "Why this exists" section that names the three concrete use cases: per-ticket context isolation, parallel project work via `.project-prefix`, and durable record back to the ticket on archive.

### Notes for downstream consumers

- This plugin requires either the official Anthropic Linear or Atlassian plugin (from the `anthropics/claude-plugins-official` marketplace) to be installed. It is a wrapper around those MCPs and has no built-in API client of its own.
- Skills follow the modern `skills/<name>/SKILL.md` layout (with `disable-model-invocation: true` — these are explicit slash commands, not model-invoked auto-skills).
