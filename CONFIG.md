# CONFIG.md — slopstop configuration reference

This file documents every configuration option across all slopstop config files. For installation walkthroughs, see `README.md`. For first-time setup, see `design/cold-start.md`.

---

## Configuration files at a glance

| File | Scope | Committed? | Purpose |
|---|---|---|---|
| `.project-conf.toml` | Per project | ✅ Yes | Ticket system, workflow shape, PR review, model tiers + fleet orchestration, code graph, autonomous mode |
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

### Top-level optional keys — `tracking_dir`, `archive_dir`, and the `scratch/` layout

```toml
tracking_dir = ".slopstop/ticket-active"    # v3 recommended
archive_dir  = ".slopstop/ticket-archive"   # v3 recommended
```

| Key | Default | Description |
|---|---|---|
| `tracking_dir` | `~/.claude/ticket-active` | Where per-ticket tracking dirs (`task_plan.md`, `findings.md`, `progress.md`) live while a ticket is active. Read by `:start`, `:plan`, `:update`, `:pr`, `:merge`, `:archive`. |
| `archive_dir` | `~/.claude/ticket-archive` | Where `:archive` moves a ticket's tracking dir at end of life. |

**Path resolution (both keys, same rules).** Relative paths (no leading `/` or `~/`) resolve from the **main worktree root** (`dirname "$(git rev-parse --git-common-dir)"`) — *not* from the cwd. That is deliberate: every linked worktree resolves to the same directory, so worktree sessions and the main checkout share one tracking dir and no symlinking is needed. Absolute paths (leading `/` or `~/`) are used as-is.

> **Do not put either directory inside `~/.claude/`.** It is a protected path: an agent's `Write` tool refuses it *even when the session was launched with a matching `--add-dir`*. The historical defaults (`~/.claude/ticket-active`, `~/.claude/ticket-archive`) therefore work for interactive sessions but silently fail for the headless fleet agents `/slopstop:run` launches — an agent that cannot write its tracking dir will invent a local one and carry on. Set both keys to a project-local path.

**Consequence for `/slopstop:run`.** Because a relative path resolves against the *main* worktree root, the resolved tracking dir lies outside every agent's worktree. The orchestrator must launch each agent with `--add-dir <resolved tracking dir>`; see `skills/run/SKILL.md` Step 4.

**The `.slopstop/` layout** (v3 recommended):

- `.slopstop/ticket-active/<TICKET>/` — tracking for tickets in flight.
- `.slopstop/ticket-archive/<TICKET>/` — tracking for finished tickets.

Add `.slopstop/` to `.gitignore`. It is transient working state, not source; without the ignore, the first `:pr` stages every tracking dir into the PR.

**The `scratch/` layout** (seeded by `:gh-init`/`:design`; full spec: `design/slopstop-process.md` §4):

- `scratch/runs/<run-id>/` — per-run interchange: run state, PRD, feature charter, fleet-state file, verdicts, umbrella + final reports. Written by the stage skills; cleaned only after the human accepts at G-final.

`scratch/` is gitignored (the seeding appends the entry idempotently), so nothing in it is ever committed or shared.

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

### `[tiers]` — model tiers for the four-tier process

Assigns a model to each tier of the slopstop process (see `design/slopstop-process.md`). Stage skills hard-stop when the session model doesn't match their declared tier; subagent tiers (adversaries, reviewers, fleet agents) are set explicitly from this table.

Each tier is a nested table with `provider` and `model` fields, and an optional `version` field to pin a specific model version.

```toml
[tiers.huge]
provider = "anthropic"
model    = "fable"
# version  = ""  # optional: pin to a specific model version

[tiers.large]
provider = "anthropic"
model    = "opus"

[tiers.medium]
provider = "anthropic"
model    = "sonnet"

[tiers.small]
provider = "anthropic"
model    = "haiku"
```

The four tiers descend `huge > large > medium > small`; each stage runs one tier down from the last, and the tier **above** a producer checks its work.

| Tier | Key | Type | Default | Description |
|---|---|---|---|---|
| `huge` | `provider` | string | `"anthropic"` | Provider for the huge tier (`:design`, huge-tier checks: ticket-tree adversary, rewrite delta checks, final-report adversary). |
| `huge` | `model` | string | `"fable"` | Model for the huge tier. |
| `huge` | `version` | string | _(none)_ | Optional: pin to a specific model version. |
| `large` | `provider` | string | `"anthropic"` | Provider for the large tier (`:tickets`, failure-driven rewrites, umbrella/integration drift checks). |
| `large` | `model` | string | `"opus"` | Model for the large tier. |
| `large` | `version` | string | _(none)_ | Optional: pin to a specific model version. |
| `medium` | `provider` | string | `"anthropic"` | Provider for the medium tier (`:run` orchestrator, per-ticket reviewer/adversary subagents). |
| `medium` | `model` | string | `"sonnet"` | Model for the medium tier. |
| `medium` | `version` | string | _(none)_ | Optional: pin to a specific model version. |
| `small` | `provider` | string | `"anthropic"` | Provider for the small tier (fleet implementation agents, see `[fleet.agents]`). |
| `small` | `model` | string | `"haiku"` | Model for the small tier. |
| `small` | `version` | string | _(none)_ | Optional: pin to a specific model version. |

**Resolution rule (applies to this table and every `[fleet.*]` table below):** all keys and tables are optional — a missing key within a tier resolves to its documented default, and a missing `[tiers]` table never errors. Skills read this config defensively. Every artifact a tier produces carries a provenance header naming the model that produced it, so substituting cheaper models here is visible, if inadvisable.

The legacy flat string form under `[tiers]` (e.g., `huge = "fable"`) is rejected with a loud error — the nested table structure is required.

---

### `[stage_tiers]` — process structure (stage → tier)

**Optional.** Decouples *process structure* from *model deployment*. `[tiers]` (above) maps each tier to a model; `[stage_tiers]` maps each stage and check-point to a **tier name**. Resolution is two hops — **stage → tier → model** (e.g. `stage_tiers.design = "huge"` → `tiers.huge = "fable"`). Re-tiering a stage — moving `:tickets` up a tier, bumping a checker — is a one-line edit here, with no skill rewrite.

```toml
[stage_tiers]
design              = "huge"     # :design tier gate
tickets             = "large"    # :tickets tier gate
run                 = "medium"   # :run orchestrator tier gate
ticket_adversary    = "huge"     # checks the large tier's ticket tree
rewrite_delta_check = "huge"     # checks a large-tier rewrite before relaunch
drift_check         = "large"    # checks the integrated code at umbrella completion
handoff_verifier    = "medium"   # checks the small tier's per-leaf implementation
report_adversary    = "huge"     # checks the final report
```

| Key | Type | Default | Runs at this tier |
|---|---|---|---|
| `design` | string | `"huge"` | `/slopstop:design` tier gate |
| `tickets` | string | `"large"` | `/slopstop:tickets` tier gate |
| `run` | string | `"medium"` | `/slopstop:run` orchestrator tier gate |
| `ticket_adversary` | string | `"huge"` | the ticket-tree adversary (checks the large tier's tree) |
| `rewrite_delta_check` | string | `"huge"` | the mandatory pre-relaunch delta check on a rewrite |
| `drift_check` | string | `"large"` | the umbrella-completion drift check |
| `handoff_verifier` | string | `"medium"` | the two per-leaf handoff verifiers (requirements adversary + code review) |
| `report_adversary` | string | `"huge"` | the final-report omission adversary |

Same **resolution rule** as `[tiers]`: a missing key resolves to its documented default (the values above — the "checker one tier above the doer" ladder); a missing `[stage_tiers]` table never errors. Fleet implementation stays `small` via `[fleet.agents].model`; the 3rd-try escalation stays `[fleet.agents].escalation_model`.

---

### `[fleet.agents]` — fleet implementation agents

Model, effort, and permission settings for the worktree agents `/slopstop:run` launches, one per leaf ticket.

```toml
[fleet.agents]
model            = "haiku"    # implementation-tier model
effort           = "medium"   # reasoning effort for implementation attempts
adversary_effort = "high"     # effort for an agent's own same-size adversary subagents
escalation_model = "sonnet"   # model for the capability-escalated final attempt

# Base tool grant every fleet agent needs, regardless of ticket. `:run` passes these
# to `claude -p --allowedTools` and appends the ticket's own build/test commands.
allowed_tools    = ["Bash(gh:*)", "Bash(git:*)"]
```

| Key | Type | Default | Description |
|---|---|---|---|
| `model` | string | `"haiku"` | Model for fleet implementation agents. Should match `[tiers].small`; if the two ever disagree, **this key wins** for fleet launches — `[tiers].small` is the tier declaration, this is the launch parameter. |
| `effort` | string | `"medium"` | Effort for implementation attempts. `"low"` is tempting for cost but under-thinks red-test authoring — the step where vacuous tests poison everything downstream. |
| `adversary_effort` | string | `"high"` | Effort for the agent's *own* same-size adversary/review subagents — the ones its inner `:plan`/`:pr` steps spawn. Distinct from the orchestrator's medium-tier handoff review, which is governed by `[tiers].medium`, not this key. Caveat: fleet agents run those steps `--inline` (no subagent spawn), where the adversary necessarily runs at the agent's own launch `effort` — this key applies only where a spawn is possible. |
| `escalation_model` | string | `"sonnet"` | When two attempts fail on capability (not ticket quality), the orchestrator may run the final attempt on this model instead. Recorded in the run ledger; max uses per ticket set by `[fleet.budget].max_tier_escalations`. |
| `allowed_tools` | array | `["Bash(gh:*)", "Bash(git:*)"]` | Base `--allowedTools` grant for every fleet agent. `--permission-mode auto` gates `Bash`, so without this an agent cannot read its ticket, transition it, comment, or push — the whole base process is denied and the agent looks merely "quiet" to monitoring. `:run` appends the ticket's own build/test commands (`Bash(go:*)`, `Bash(python3:*)`, …) from its **Test expectations** section. Widen this list rather than reaching for `bypassPermissions`: a fleet agent should not hold a blanket shell grant. |

---

### `[fleet.monitoring]` — orchestrator poll loop and kill triggers

Thresholds for `/slopstop:run`'s autonomous monitoring. The orchestrator polls each agent's ticket comments and worktree, and kills agents that are stuck or out of bounds — kills consume an attempt and appear in the run report, never as human interrupts.

```toml
[fleet.monitoring]
poll_interval_min     = 5
quiet_investigate_min = 15
silence_kill_min      = 30
loop_kill_reports     = 3
filemap_violation     = "kill"   # "kill" | "warn"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `poll_interval_min` | int | `5` | Minutes between orchestrator monitoring passes. |
| `quiet_investigate_min` | int | `15` | No new ticket comment for this long → peek the worktree (`git status`, file mtimes) before judging. Activity without comments is a nudge, not a kill. |
| `silence_kill_min` | int | `30` | No comments AND no worktree activity for this long → kill and relaunch with findings. |
| `loop_kill_reports` | int | `3` | The same failure reported this many consecutive times with no new approach → kill. |
| `filemap_violation` | string | `"kill"` | Agent writes outside its ticket's file map: `"kill"` terminates instantly (mechanical check, no model judgment). `"warn"` logs the violation and lets the agent continue — **use `"warn"` while evaluating small models or testing the process**, then flip to `"kill"` once thresholds are tuned. |

---

### `[fleet.budget]` — attempt and escalation caps

Bounds autonomous spend per ticket. Exhausting the attempt/version caps escalates to the human (G4) with the failure ledger — more attempts beyond those caps are always a human decision. (Tier escalation itself is autonomous; its cap simply removes that option from the orchestrator's menu once spent.)

```toml
[fleet.budget]
max_attempts_per_version = 3
max_ticket_versions      = 3
max_tier_escalations     = 1
```

| Key | Type | Default | Description |
|---|---|---|---|
| `max_attempts_per_version` | int | `3` | Implementation attempts per ticket version. A rewrite creates a new version with a fresh budget (same preserved worktree). |
| `max_ticket_versions` | int | `3` | V1 plus two failure-driven rewrites. Every rewrite passes a huge-tier delta check before relaunch. |
| `max_tier_escalations` | int | `1` | At most one `escalation_model` attempt per ticket. |

---

### `[fleet.router]` — metering router (optional infrastructure)

Routes agent API traffic through a local metering proxy so runs get per-run-id spend reporting. Entirely optional: with `enabled = false` (the default) agents talk to the API directly and reports say "cost tracking disabled" — no router, Docker, or extra setup needed.

```toml
[fleet.router]
enabled = false
# host = "127.0.0.1"
# port = 8484
```

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | `true`: `:design` health-checks the router at run start via `GET /spend?prefix=$PREFIX&run=$RUN_ID` (prefix-required probe), and `:run` health-checks it at *each agent launch*, pointing agents at it (`ANTHROPIC_BASE_URL`) with requests tagged by run-id and ticket-id via `X-Slopstop-Run` and `X-Slopstop-Ticket` headers. If the router is unreachable at an agent's launch, that agent falls back to direct API access and reports note "cost tracking unavailable" — a dead router never blocks a run. |
| `host` / `port` | string / int | `"127.0.0.1"` / `8484` | Where the router listens. |

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

# :merge — PR merge strategy. Use "merge". See the merge-policy note below.
merge_strategy = "merge"           # merge | squash | rebase

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
| `merge_strategy` | `"merge"` | `:merge` | PR merge strategy. Overrides the `--strategy` flag default. **Keep this at `"merge"`** — see the merge-policy note below. |
| `merge_target_state` | `"auto"` | `:merge` | Ticket state after merge. `"auto"` uses the advance-one-state algorithm. `"done"` forces terminal state. `"skip"` skips the ticket-system transition entirely. |
| `archive_immediately` | `false` | `:merge` | If `true` and the post-merge state is terminal, chains into `:archive` without prompting. If the state is intermediate, logs a skip message. |
| `metrics_emit_path` | absent | All | Directory to write `<TICKET>/pipeline.json` after each command completes. Used for benchmark metric collection. |
| `cc_warn_threshold` | `10` | `:pr` | 🟡 CC-elevated boundary for the CC gate (Step 0c). Functions with `cc_warn_threshold < CC ≤ cc_reject_threshold` are flagged 🟡. |
| `cc_reject_threshold` | `15` | `:pr` | 🔴 hard-gate threshold for the CC gate. Functions with CC > this value are violations. |

#### Merge policy — always a real merge commit

`:merge` defaults to `--strategy merge`, and `merge_strategy` should stay `"merge"`.

A squash collapses a branch's commits into one. That is exactly the history `git bisect` needs in order to be useful: bisect can only land on commits that exist, so squashing a ten-commit branch turns ten bisectable steps into one, and the first-bad-commit it reports is a whole feature rather than the line that broke. Rebase has the same effect on merge provenance — it discards the branch point, so you can no longer see what was developed in parallel with what.

A real merge commit keeps every individual commit reachable *and* records the branch topology. `git bisect` walks the individual commits; `git log --first-parent` still gives the clean one-line-per-PR view that squashing is usually reached for. You get both.

`squash` and `rebase` remain available via `--strategy` for the rare PR whose history is genuinely noise (a long fix-typo chain, say). They are the exception, chosen per PR — never the project default.
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
