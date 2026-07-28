# CONFIG.md — slopstop configuration reference

This file documents every configuration option across all slopstop config files. For installation walkthroughs, see `README.md`. For first-time setup, see `SETUP-GUIDE.md`.

---

## Configuration files at a glance

| File | Scope | Committed? | Purpose |
|---|---|---|---|
| `.project-conf.toml` | Per project | ✅ Yes | Ticket system, workflow shape, PR review, model tiers + fleet orchestration, autonomous mode |
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

### Top-level optional keys — `pr-repo`, `base-branch`

```toml
pr-repo     = "owner/repo"   # GitHub owner/repo for API calls, if different from `key`
base-branch = "develop"      # PR target branch, if not the repo's default branch
```

| Key | Default | Description |
|---|---|---|
| `pr-repo` | `key` | `owner/repo` used for GitHub API calls (PR create/list, issue comment/label/close) when it differs from `key` — e.g. `key` names a personal fork you push to, but issues/PRs live in the upstream repo. Read by `:pr`, `:merge`, `:start`, `:document`. |
| `base-branch` | the repo's default branch | Overrides the PR target branch `:pr` opens against. Same effect as passing `--base` on every invocation. |

---

### Top-level optional keys — `tracking_dir`, `archive_dir`, and the `scratch/` layout

**Both keys are overrides, not settings you need.** Create a `.slopstop/` directory at the
main worktree root and both paths resolve to it — no config at all:

```toml
# Nothing needed. With .slopstop/ present:
#   tracking_dir -> .slopstop/ticket-active
#   archive_dir  -> .slopstop/ticket-archive
```

| Key | Default | Description |
|---|---|---|
| `tracking_dir` | resolved (see ladder) | **Override.** Where per-ticket tracking dirs (`task_plan.md`, `findings.md`, `progress.md`) live while a ticket is active. Read by `:start`, `:plan`, `:update`, `:pr`, `:merge`, `:archive`. |
| `archive_dir` | resolved (see ladder) | **Override.** Where `:archive` moves a ticket's tracking dir at end of life. |

**Resolution ladder — first match wins, and both paths resolve together.**

| | Condition | `tracking_dir` | `archive_dir` |
|---|---|---|---|
| **Tier 1** | the key is set | that value, **verbatim** | that value, **verbatim** |
| **Tier 2** | key unset, `.slopstop/` exists | `.slopstop/ticket-active` | `.slopstop/ticket-archive` |
| **Tier 3** | key unset, no `.slopstop/` | `~/.claude/ticket-active` | `~/.claude/ticket-archive` |

Tier 1 is per-key, so setting one still lets the other fall to tier 2. **Tier 2 needs only the directory** — its presence implies both subdirectories, and neither needs to exist yet. Tier 1 beats tier 2, so an explicit `tracking_dir = ".slopstop"` still means exactly `.slopstop` (tickets at `.slopstop/<TICKET>`) and existing state is never stranded.

The canonical definition — including the layout-mismatch report — is `skills/start/references/tracking-dir-resolution.md`, which every skill reads. It is one file precisely because twelve skills used to re-derive this and disagreed.

**Path rules (all tiers).** Relative paths (no leading `/` or `~/`) resolve from the **main worktree root** (`dirname "$(git rev-parse --git-common-dir)"`) — *not* from the cwd. That is deliberate: every linked worktree resolves to the same directory, so worktree sessions and the main checkout share one tracking dir and no symlinking is needed. Absolute paths (leading `/` or `~/`) are used as-is.

**A layout mismatch is reported, never fixed.** If ticket dirs exist under a different tier's layout than the one resolved, the skill says so and continues — it never moves, merges, or deletes anything. Adopting stray state is your call: a wrong guess silently destroys the only record of in-flight work.

> **Do not put either directory inside `~/.claude/`.** It is a protected path: an agent's `Write` tool refuses it *even when the session was launched with a matching `--add-dir`*. Tier 3 therefore works for interactive sessions but silently fails for the headless fleet agents `/slopstop:run` launches — an agent that cannot write its tracking dir will invent a local one and carry on. The fix is to **create `.slopstop/`**, which moves you to tier 2. Note it is a *directory*, not a key: the old advice here was "set `tracking_dir` to a project-local path (e.g. `.slopstop/ticket-active`)", and a session that already had a `.slopstop` configured read that as instructions to append `ticket-active` to it — inventing a second, divergent tree. That is the bug tier 2 exists to remove.

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

Configures what `/slopstop:pr` does after opening the pull request. Three backends are equally supported: `"coderabbit"`, `"greptile"`, and `"claude"`. Omit the entire block to use CodeRabbit (if installed on the repo) with no extra config.

```toml
[pr_review]
backend         = "claude"    # "coderabbit" (default) | "greptile" | "claude"
effort          = "high"      # low | medium | high | max | ultra  (Claude only; default: "high")
fix             = false       # true: auto-commit fixable findings after code-review  (Claude only; default: false)
coderabbit_fix  = true        # true: auto-apply 🔴/🟡 CodeRabbit findings in the fix-and-iterate loop (CodeRabbit only; default: true)
greptile_fix    = true        # true: auto-apply 🔴/🟡 Greptile findings in the fix-and-iterate loop (Greptile only; default: true)
```

| Key | Type | Default | Description |
|---|---|---|---|
| `backend` | string | `"coderabbit"` | Which review backend `:pr` uses. `"coderabbit"`: trigger and poll for CodeRabbit feedback (requires CodeRabbit installed on the repo). `"greptile"`: trigger and poll for Greptile feedback (requires Greptile installed on the repo). `"claude"`: invoke `/code-review` at the configured effort level. **Interactive sessions only:** `:pr --inline` — the mandatory form for fleet agents launched by `:run` — always uses the claude backend regardless of this value, and logs the override. The bot backends are interactive-only: their poll outlives a headless `claude -p` one-shot. |
| `effort` | string | `"high"` | Effort level passed to `/code-review`. Claude backend only. One of `low` / `medium` / `high` / `max` / `ultra`. |
| `fix` | bool | `false` | If `true`, fixable findings from `/code-review` are auto-committed and pushed after the review completes — self-contained, works the same in every mode. Claude backend only. **Note:** `[autonomous] on_red_findings` (default `"fix-and-retry"`) is only consulted when `fix = false` — it's never reached when `fix = true`, so the two never conflict. Explicitly setting both is a harmless no-op that `:pr` warns about once (see `pr/SKILL.md` Pre-flight), not an error. |
| `coderabbit_fix` | bool | `true` | If `false`, CodeRabbit findings are presented only — never auto-applied. CodeRabbit backend only. |
| `greptile_fix` | bool | `true` | If `false`, Greptile findings are presented only — never auto-applied. Greptile backend only. |

When `[pr_review]` is absent AND CodeRabbit is not installed on the repo, no review step runs. Pass `--no-poll` to skip the review step explicitly.

All three backends post comments directly onto the PR (CodeRabbit/Greptile via their bots; Claude via `/code-review --comment`) — none of them is terminal/chat-only. `:pr` Step 7f posts a comment on the ticket linking back to the PR/review after any of them runs (see `skills/pr/SKILL.md`).

---

### `[design]` — the authoritative specification

**Optional.** Names the document(s) `/slopstop:design` treats as the source of truth for a run. When set, every decision in the PRD is classified against it (`SPEC` / `DERIVED` / `UNDERDETERMINED`), and the ticket-tree adversary's **check F** re-reads it to verify each quoted excerpt still says what the decision claims.

```toml
[design]
spec = "SPEC.md"                          # a single document
# spec = ["SPEC.md", "docs/api-contract.md"]   # or an array of them
```

| Key | Type | Default | Description |
|---|---|---|---|
| `spec` | string \| array of strings | _(unset)_ | Path(s), relative to the repo root, of the authoritative specification. A single path may be given as a bare string; several as an array of strings. Overridden per-run by `:design --spec <path>` (repeatable). |

**Resolution order** — `:design --spec` (repeatable, wins) → `[design] spec` → a conventional path (`SPEC.md`, `docs/spec*.md`), which `:design` **proposes and asks about** rather than adopting silently. If none resolves, the PRD records `SPEC: none — greenfield` and every decision defaults to `UNDERDETERMINED` unless it derives from the grill transcript.

The PRD header records each resolved spec's path **and its `sha256`**. Check F compares that hash when it re-reads the document: a mismatch means the spec changed after the PRD was written, which silently invalidates every `SPEC`-classified decision, and is a finding in its own right.

Same resolution rule as every other table: a missing key or missing table never errors.

---

### `[workflow]` — cross-mode behavior shortcuts

`skip_confirm` reduces friction in interactive sessions without enabling full autonomous mode. `skip_archive` is not mode-scoped at all — it applies identically whether or not `[autonomous] enabled = true`.

```toml
[workflow]
skip_confirm = true    # true | false (default: false)
skip_archive = false   # true | false (default: false)
```

| Key | Type | Default | Description |
|---|---|---|---|
| `skip_confirm` | bool | `false` | If `true`, skips the interactive confirmation prompts in `:merge`, `:archive`, and `:start` (when a branch-type heuristic suggestion is available). Auto-proceeds as `yes` and logs the plan. Has no effect when `[autonomous] enabled = true` (autonomous mode already skips confirmations). |
| `skip_archive` | bool | `false` | If `true`, `:merge` skips its `:document` push (description/DoD/findings) and its Step 10 archive chain (tracking-dir move) entirely — for every merge, not just terminal-state ones. Instead it posts a single comment with the merge commit id when the ticket transitions state. `$TRACKING_DIR/$TICKET/` is left in place indefinitely. Same effect in interactive and autonomous mode. |

**When to use `skip_confirm`:** personal projects where you always say yes and the confirmation adds friction without value. Not recommended for team repos where multiple people might need to review what's about to happen.

**When to use `skip_archive`:** projects that don't want the full plan/DoD/findings pushed to every ticket — e.g. tickets tracked lightly, or where the commit history itself is the record. Most projects should leave this `false`: `:archive`'s documentation push is what turns a ticket into a durable record of what was actually done, not just a title and a merged PR diff.

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

`version` is optional on every tier — an omitted `version` resolves to any version of the family named by `model`, rather than pinning to a specific one.

`url` is deliberately absent from this schema. Tiers name a provider and a model family for skills to route work to; gating never dials an endpoint directly, so there is no URL for a tier to carry.

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
| `tickets` | string | `"large"` | `/slopstop:tickets` tier gate — also `/slopstop:single-ticket`'s authoring tier (no dedicated key; it does the same caliber of per-leaf work, just for one existing ticket) |
| `run` | string | `"medium"` | `/slopstop:run` orchestrator tier gate |
| `ticket_adversary` | string | `"huge"` | the ticket-tree adversary (checks the large tier's tree) — also `/slopstop:single-ticket`'s adversary tier |
| `rewrite_delta_check` | string | `"huge"` | the mandatory pre-relaunch delta check on a rewrite |
| `drift_check` | string | `"large"` | the umbrella-completion drift check |
| `handoff_verifier` | string | `"medium"` | the two per-leaf handoff verifiers (requirements adversary + code review) |
| `report_adversary` | string | `"huge"` | the final-report omission adversary |

Same **resolution rule** as `[tiers]`: a missing key resolves to its documented default (the values above — the "checker one tier above the doer" ladder); a missing `[stage_tiers]` table never errors. Fleet implementation defaults to the model resolved from `[tiers].small` (override via `[fleet.agents].model`); the 3rd-try escalation defaults to the model resolved from `[tiers].medium` (override via `[fleet.agents].escalation_model`).

---

### `[fleet.agents]` — fleet implementation agents

Model, effort, and permission settings for the worktree agents `/slopstop:run` launches, one per leaf ticket.

**Model defaults derive from the tier ladder — you don't repeat it here.** When `model` is absent, the fleet implementation model is **resolved from `[tiers].small`**; when `escalation_model` is absent, the capability-escalation model is **resolved from `[tiers].medium`**. Resolution honors the tier's optional version pin: the tier's `model` family plus its `version` compose into a model id (`sonnet` + `version = "5"` → `claude-sonnet-5`), while an **unpinned** tier resolves to the bare family alias (e.g. `haiku`). Setting `model` / `escalation_model` here is an **override** that wins over the tier-derived default — no project needs to set them to get the small/medium tier models.

```toml
[fleet.agents]
# model and escalation_model are OPTIONAL overrides. When absent they derive from the
# tier ladder — model <- [tiers].small, escalation_model <- [tiers].medium — honoring
# each tier's version pin. Uncomment only to pin a fleet model off the tier ladder.
# model            = "haiku"    # override: fleet implementation model
# escalation_model = "sonnet"   # override: capability-escalated final-attempt model
effort           = "medium"   # reasoning effort for implementation attempts
adversary_effort = "high"     # effort for an agent's own same-size adversary subagents

# Base tool grant every fleet agent needs, regardless of ticket. `:run` passes these
# to `claude -p --allowedTools` and appends the ticket's own build/test commands.
allowed_tools    = ["Bash(gh:*)", "Bash(git:*)"]
```

| Key | Type | Default | Description |
|---|---|---|---|
| `model` | string | resolved from `[tiers].small` | Fleet implementation model. Absent → the model **resolved from `[tiers].small`** (see the note above); set → an **override** that wins for fleet launches. |
| `effort` | string | `"medium"` | Effort for implementation attempts. `"low"` is tempting for cost but under-thinks red-test authoring — the step where vacuous tests poison everything downstream. |
| `adversary_effort` | string | `"high"` | Effort for the agent's *own* same-size adversary/review subagents — the ones its inner `:plan`/`:pr` steps spawn. Distinct from the orchestrator's medium-tier handoff review, which is governed by `[tiers].medium`, not this key. Caveat: fleet agents run those steps `--inline` (no subagent spawn), where the adversary necessarily runs at the agent's own launch `effort` — this key applies only where a spawn is possible. |
| `escalation_model` | string | resolved from `[tiers].medium` | Model for the capability-escalated final attempt (when two attempts fail on capability, not ticket quality). Absent → the model **resolved from `[tiers].medium`** (see the note above); set → an **override** that wins. Recorded in the run ledger; max uses per ticket set by `[fleet.budget].max_tier_escalations`. |
| `allowed_tools` | array | `["Bash(gh:*)", "Bash(git:*)"]` | Base `--allowedTools` grant for every fleet agent. The launch's `--permission-mode acceptEdits` covers the agent's file edits but not `Bash`, so without this an agent cannot read its ticket, transition it, comment, or push — the whole base process is denied and the agent looks merely "quiet" to monitoring. `:run` appends the ticket's own build/test commands (`Bash(go:*)`, `Bash(python3:*)`, …) from its **Test expectations** section. Widen this list rather than reaching for `bypassPermissions`: a fleet agent should not hold a blanket shell grant. |

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

Bounds autonomous spend per ticket. Exhausting the attempt/version caps escalates to the human (G-failure) with the failure ledger — more attempts beyond those caps are always a human decision. (Tier escalation itself is autonomous; its cap simply removes that option from the orchestrator's menu once spent.)

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

### `[autonomous]` — non-interactive mode

Designed for benchmark harnesses (SlopCodeBench), overnight runs, and CI pipelines where no human is present. All interactive confirmation prompts are replaced by config-driven decisions. **Requires `enabled = true` to activate** — a partial block with some keys set but `enabled` absent or `false` has no effect.

**Policy: autonomous mode runs to completion unless it hits a serious or repeated problem — it never silently stalls on "ask."** Every key below now defaults to a non-stalling value, so `enabled = true` alone (no other keys) is a working, non-stalling config. `"ask"` remains available on every key for the rare case where a human actually is monitoring a nominally-autonomous run.

```toml
[autonomous]
enabled = true

# :start — skip branch-type selection prompt (optional — unset uses the label/title
# heuristic automatically; only needed to override the heuristic or when no ticket
# signal exists at all)
branch_type = "feat"               # fix | feat | chore | docs | refactor | perf | test | ci | build | deploy | revert | <custom>

# :plan — what to do when Phase 0 tests already pass (ticket may be stale) (default shown)
on_phase0_tests_pass = "continue"  # continue (default) | ask | abort

# :plan — what to do when the plan recommends parallel agents (default shown)
on_parallel_agents = "proceed"     # proceed (default) | ask | serial | abort

# :plan — what to do when the adversary agent finds gap tests (default shown)
on_test_gaps = "add-all"           # add-all (default) | ask | skip

# :pr — what to do when simplify modifies the working tree (default shown)
on_simplify_changes = "accept"     # accept (default) | ask | reject

# :merge — what to do when a Definition-of-Done item is not met (default shown)
on_dod_not_met = "abort"           # abort (default) | warn

# :pr — what to do when pre-commit tests fail (default shown)
on_test_failure = "abort"          # abort (default) | ask | commit-anyway | benchmark-continue

# :pr — what to do with 🔴 and 🟡 review findings (Claude backend only) (default shown)
on_red_findings = "fix-and-retry"  # fix-and-retry (default) | ask | skip

# :pr — what to do when slop detection finds violations (defaults shown)
on_slop_findings  = "skip"         # skip (default) | ask | hard-stop   (Step 2e — judgment)
on_redtest_tamper = "hard-stop"    # hard-stop (default) | warn          (Step 2d — mechanical; no "skip")
on_vacuity_findings = "hard-stop"  # hard-stop (default) | warn          (Step 2f — mechanical; no "skip")

# :merge — PR merge strategy. Use "merge". See the merge-policy note below.
merge_strategy = "merge"           # merge | squash | rebase

# :merge — ticket target state after merge
merge_target_state = "auto"        # auto | done | skip

# All skills — emit pipeline.json to this dir after each command (for metric collection)
metrics_emit_path = "~/.claude/ticket-active"
```

#### Key reference

| Key | Default | Skill | Description |
|---|---|---|---|
| `enabled` | `false` | All | Master switch. Must be `true` for any other key in this section to take effect. |
| `branch_type` | (unset) | `:start`, `:run` | Conventional Commits prefix used for branch names. If set, skips the interactive type-selection prompt — must pass `git check-ref-format`, or `:start` hard-stops with a config error (never silently falls back to asking). If unset, `:start` uses the label/title heuristic suggestion automatically; if the heuristic finds no signal either, `:start` hard-stops rather than stalling on a prompt. **Optional for fleet runs, not required:** `:run` creates each agent's worktree branch before the agent starts, so it resolves `<TYPE>` the same way per leaf — this value when set, else the same heuristic. A leaf with no signal skips *that leaf's* launch, not the run. |
| `on_phase0_tests_pass` | `"continue"` | `:plan` | What to do when Phase 0 red tests unexpectedly pass (possible stale ticket). `"abort"` stops; `"ask"` stalls a headless run — set it explicitly only when a human is monitoring. |
| `on_parallel_agents` | `"proceed"` | `:plan` | What to do when ≥2 work items are parallel-safe. `"serial"` runs them sequentially, `"abort"` stops, `"ask"` stalls a headless run. |
| `on_test_gaps` | `"add-all"` | `:plan` | Whether to add adversary-found gap tests. `"skip"` bypasses them; `"ask"` stalls a headless run. |
| `on_simplify_changes` | `"accept"` | `:pr` | What to do when the simplify pass modifies the working tree. `"reject"` stops; `"ask"` stalls a headless run. |
| `on_test_failure` | `"abort"` | `:pr` | What to do on pre-commit test failure. `"commit-anyway"` notes the failure in the commit body and proceeds; `"benchmark-continue"` does the same but also writes a structured override record to `pipeline.json` and adds a prominent `⚠️ BENCHMARK OVERRIDE` note — it also governs the Step 0 pre-PR test gate and bypasses the CC gate, unlike `"commit-anyway"` which only covers the pre-commit test step. A CC **measurement failure** is bypassed too, under its own `pre_pr_cc_gate_measurement_failure` step, so a bypassed broken gate is never mistaken for a clean one. `"ask"` stalls a headless run. |
| `on_red_findings` | `"fix-and-retry"` | `:pr` | What to do with 🔴 and 🟡 code-review findings (verified-real findings should be fixed, not just flagged — see the fix-and-retry loop's convergence guard for the retry cap). `"skip"` logs and moves on without applying; `"ask"` stalls a headless run. Claude backend only. |
| `on_slop_findings` | `"skip"` | `:pr` | What to do with **Step 2e** slop-detection (judgment) violations. `"hard-stop"` refuses any override; `"ask"` stalls a headless run. Does **not** affect Step 2d. |
| `on_redtest_tamper` | `"hard-stop"` | `:pr` | What to do when the **Step 2d** red-test tamper gate (mechanical) fires. Deliberately separate from `on_slop_findings`, and deliberately has **no `"skip"`**: `on_slop_findings` defaults to `"skip"` itself (it polices a judgment call, not a mechanical fact), so a shared knob would silently disable the anti-tampering gate for exactly the agents it exists to police. `"warn"` logs and continues — use only while evaluating a new model tier; `:run`'s tamper check remains the external backstop. |
| `on_vacuity_findings` | `"hard-stop"` | `:pr` | What to do when the **Step 2f** vacuity gate (mechanical) finds a 🔴 changed test that passes cleanly against the base implementation. Same reasoning as `on_redtest_tamper`, and deliberately **no `"skip"`** for the identical reason. `"warn"` logs and continues — use only while evaluating a new model tier. Does not affect ⚪ inconclusive or backfill-declared findings, which never block regardless of this setting. |
| `merge_strategy` | `"merge"` | `:merge` | PR merge strategy. Overrides the `--strategy` flag default. **Keep this at `"merge"`** — see the merge-policy note below. |
| `on_dod_not_met` | `"abort"` | `:merge` | What to do when the Step 1 Definition-of-Done gate finds an item that is not `met`. `"abort"` refuses the merge; `"warn"` logs every offending item with its verdict and evidence, then proceeds. Governs **both** `not-met` and `unverifiable` — the name predates the second verdict. No effect interactively: `enabled` is a master switch, so an interactive run has no override by construction. |
| `merge_target_state` | `"auto"` | `:merge` | Ticket state after merge. `"auto"` uses the advance-one-state algorithm. `"done"` forces terminal state. `"skip"` skips the ticket-system transition entirely. |
| `metrics_emit_path` | absent | All | Directory to write `<TICKET>/pipeline.json` after each command completes. Used for benchmark metric collection. |
| `cc_warn_threshold` | `5` | `:pr` | 🟡 CC-elevated boundary for the CC gate (Step 0c). **Inclusive lower bound**: functions with `cc_warn_threshold <= CC < cc_reject_threshold` are flagged 🟡 — 5–9 at the defaults. |
| `cc_reject_threshold` | `10` | `:pr` | 🔴 hard-gate threshold for the CC gate. **Inclusive**: functions with `CC >= this value` are violations — 10 or above at the defaults. |
| `cc_exempt_pre_existing` | `false` | `:pr` | Exempts a 🔴 CC violation this branch's diff did not touch (by line-range overlap, not by function name) from the hard-gate. Still printed, under its own heading. `false`: every violation blocks, touched or not — the behavior before this key existed. |

#### Merge policy — always a real merge commit

`:merge` defaults to `--strategy merge`, and `merge_strategy` should stay `"merge"`.

A squash collapses a branch's commits into one. That is exactly the history `git bisect` needs in order to be useful: bisect can only land on commits that exist, so squashing a ten-commit branch turns ten bisectable steps into one, and the first-bad-commit it reports is a whole feature rather than the line that broke. Rebase has the same effect on merge provenance — it discards the branch point, so you can no longer see what was developed in parallel with what.

A real merge commit keeps every individual commit reachable *and* records the branch topology. `git bisect` walks the individual commits; `git log --first-parent` still gives the clean one-line-per-PR view that squashing is usually reached for. You get both.

`squash` and `rebase` remain available via `--strategy` for the rare PR whose history is genuinely noise (a long fix-typo chain, say). They are the exception, chosen per PR — never the project default.
| `file_nloc_warn_threshold` | `400` | `:pr` | 🟡 file-size warning in the CC gate. Files whose lizard NLOC sum exceeds this threshold are flagged 🟡. Set `0` to disable. |

Every key above defaults to a non-stalling value (see the policy note at the top of this section) — a partial `[autonomous]` block with only some keys filled in is safe, and `enabled = true` alone is already a working config. Set a key to `"ask"` explicitly only for the rare case where a human is actually monitoring an otherwise-autonomous run.

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

MCPs required by the skills (Linear, GitHub, JIRA) are installed as plugins via `/plugin install`, not declared in `.mcp.json`. See `SETUP-GUIDE.md §3` for the install commands.

If your project needs project-specific MCP servers (e.g. a custom internal tool), declare them here as additional entries under `mcpServers`.
