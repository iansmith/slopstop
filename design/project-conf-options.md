# `.project-conf.toml` — complete option reference

Every option the skills read from `.project-conf.toml`, what it does, which skills consume it, and what the default is when absent. Use `design/project-conf-toml.md` for the design rationale; this file is the flat reference you reach for when configuring a project.

---

## Top-level required keys

| Key | Type | Required? | Skills |
|---|---|---|---|
| `system` | string | always | all |
| `key` | string | always | all |
| `prefix` | string | when `system = "github"` | all |

### `system`

`"linear"` / `"jira"` / `"github"`.

Sets the ticket backend. Every skill branches on this to pick the right MCP tools or `gh` CLI calls.

### `key`

The project identifier in the ticket system's native format:

- **Linear:** team key, e.g. `"MAZ"`
- **JIRA:** project key, e.g. `"PLTF"`
- **GitHub:** `"owner/repo"`, e.g. `"iansmith/slopstop"`

For GitHub projects, `key` doubles as the default PR target repo (unless overridden by `pr-repo`). For Linear/JIRA, `key` has no GitHub meaning unless `pr-repo` is also set.

### `prefix`

Short filesystem- and branch-safe token used in `$PREFIX-N` ticket IDs and directory names: `"BILL"`, `"MAZ"`, `"PLTF"`.

Required for `system = "github"` because `key` contains a slash. For Linear/JIRA, `key` already plays this role and `prefix` is omitted.

---

## Top-level optional keys

### `pr-repo`

```toml
pr-repo = "owner/repo"   # e.g. "iansmith/mycopy"
```

Overrides `key` when resolving `$OWNER`/`$REPO` for GitHub PR and issue operations. When absent, `$OWNER`/`$REPO` are parsed from `key`.

Two situations where you need this:

1. **JIRA or Linear project with GitHub PRs.** `key` is `"PLTF"` or `"MAZ"` — not a GitHub path. Set `pr-repo = "owner/repo"` so `:pr`, `:merge`, `:archive`, and `:document` know where to open and fetch PRs.

2. **GitHub project targeting a fork.** `key = "upstream/repo"` (the canonical project), but your PRs go to `"yourfork/repo"`. Set `pr-repo = "yourfork/repo"`.

Read by: `:pr`, `:merge`, `:archive`, `:document`, `:start` (GitHub issue fetch).

### `pr-remote`

```toml
pr-remote = "origin"    # default
```

The git remote that feature branches are pushed to. `:pr` uses this in `git push $PR_REMOTE $BRANCH`.

Change this when you push to a fork or a secondary remote while the canonical PR lives elsewhere. See **Fork-PR pattern** below.

Read by: `:pr`, `:start` (branch existence check).

### `origin-remote`

```toml
origin-remote = "origin"   # default
```

The git remote that owns the canonical base branch. Used by `:merge` when fetching, pulling, and syncing `$baseRefName` after merge. Also used by `:start` to determine the base ref for new branches.

When `pr-remote` and `origin-remote` are the same remote (the common case), there is no functional difference between them. They diverge in the fork-PR pattern.

Read by: `:pr`, `:merge`, `:start`.

### `base-branch`

```toml
base-branch = "exp/fable-5-solo"
```

Overrides the PR target branch. When absent, `:pr` targets the repo's default branch (usually `master` or `main`). When present, this branch is used as the middle fallback between an explicit `--base` argument and the default branch.

Resolution order: `--base` CLI argument → `base-branch` in config → repo default branch.

Useful when all work on a project should merge into a long-lived feature branch rather than `master`.

Read by: `:pr`.

### `cc_warn_threshold`

```toml
cc_warn_threshold = 10   # default
```

Cyclomatic complexity threshold above which `:pr`'s pre-commit CC gate emits a 🟡 warning in the PR body. Does not block the PR.

Read by: `:pr` (Step 0c CC gate).

### `cc_reject_threshold`

```toml
cc_reject_threshold = 15   # default
```

Cyclomatic complexity threshold above which `:pr` hard-stops and refuses to create the PR. In autonomous mode, requires a `benchmark-continue` override (recorded to `pipeline.json`).

Read by: `:pr` (Step 0c CC gate).

### `tracking_dir`

```toml
tracking_dir = "~/.claude/ticket-active"   # default (global, shared across all projects)
# or, for project-local isolation:
tracking_dir = ".claude/ticket-active"     # relative to main worktree root
```

Base directory for per-ticket tracking files (`task_plan.md`, `findings.md`, `progress.md`, `progress.md`).

**Default behavior (absent or `~/.claude/ticket-active`):** tracking files are stored globally in `~/.claude/ticket-active/$TICKET/`. All projects on the machine share this directory; isolation is by ticket prefix (`BILL-*` vs `MAZ-*`).

**Project-local alternative (`.claude/ticket-active`):** a relative path is resolved from the main worktree root (`dirname "$(git rev-parse --git-common-dir)"`), so worktree sessions (`~/project/wt-KEY-N/`) and main-checkout sessions share the same tracking files. This is the right choice when:
- multiple users or machines work on the same project (gitignore `.claude/ticket-active/` individually)
- you want per-project isolation without relying on ticket-prefix uniqueness
- you're running multiple independent projects whose ticket prefixes collide

If using a relative path, add `.claude/ticket-active/` to the project's `.gitignore`.

An absolute path (starting with `/` or `~/`) is used as-is.

Read by: all ticket-lifecycle skills (`:start`, `:plan`, `:update`, `:pr`, `:merge`, `:archive`, `:document`).

---

## `[status_labels]` — GitHub workflow states

Only relevant for `system = "github"`. For Linear/JIRA, states are first-class in the ticket system and this section is omitted.

```toml
[status_labels]
in_progress = "status:in-progress"
# in_review = "status:in-review"   # uncomment for 4-state workflow
```

### `in_progress`

Required for `system = "github"`. The GitHub label name that signals "In Progress". `:start` applies this label when beginning a ticket; `:merge` reads it to know the current workflow state.

### `in_review`

Optional. When present, enables the 4-state workflow (`Todo → In Progress → In Review → Done`). `:merge` applies this label instead of closing the issue directly. When absent, the workflow is 3-state and `:merge` closes the issue and removes the `in_progress` label.

---

## `[pr_review]` — review backend configuration

```toml
[pr_review]
backend         = "coderabbit"   # default
effort          = "high"         # Claude backend only
fix             = false          # Claude backend only
coderabbit_fix  = true           # CodeRabbit backend only
```

### `backend`

`"coderabbit"` (default) or `"claude"`.

Selects the review backend that `:pr` uses after opening the PR.

- **`"coderabbit"`** — polls for a CodeRabbit walkthrough comment, verifies findings against the actual code, and applies 🔴/🟡 fixes automatically (see `coderabbit_fix`).
- **`"claude"`** — invokes `/code-review` at the configured `effort` level, posts findings as inline PR comments.

### `effort`

Claude backend only. `"low"` | `"medium"` | `"high"` (default) | `"xhigh"` | `"max"`.

Controls how many finder agents and verify passes `/code-review` runs. Higher effort catches more but takes longer.

### `fix`

Claude backend only. `true` | `false` (default).

When `true`, `:pr` automatically applies Claude's confirmed findings, commits the fixes, and pushes before completing.

### `coderabbit_fix`

CodeRabbit backend only. `true` (default) | `false`.

When `true` (default), `:pr` automatically applies 🔴 and 🟡 CodeRabbit findings in a fix-and-iterate loop. When `false`, findings are presented for human judgment only and the loop is skipped.

---

## `[workflow]` — interactive-prompt behavior

```toml
[workflow]
skip_confirm = false   # default
```

### `skip_confirm`

When `true`, skips the interactive confirmation prompt in `:merge` (Step 3) and `:archive` (Step 2), proceeding as if the user answered `yes`. Logs the auto-confirmed plan in place of the prompt.

Useful for projects where the confirmation adds no value — e.g. solo dev working fast, or a CI-adjacent pipeline. Does NOT disable autonomous mode's per-step config; that's `[autonomous].enabled`.

---

## `[tiers]` — model tiers for the four-tier process

```toml
[tiers.huge]
provider = "anthropic"  # default
model    = "fable"      # default

[tiers.large]
provider = "anthropic"  # default
model    = "opus"       # default

[tiers.medium]
provider = "anthropic"  # default
model    = "sonnet"     # default

[tiers.small]
provider = "anthropic"  # default
model    = "haiku"      # default
```

Consumed by the stage skills (`:design` on `huge`; `:tickets` on `large`; `:run` on
`medium`) and every tier-pinned check the process spawns (ticket-tree adversary, rewrite
delta checks, final-report adversary on `huge`; umbrella/integration drift checks on
`large`; handoff reviewers on `medium`). Stage skills
hard-stop on a session-model mismatch. Missing keys resolve to the defaults; a
missing table never errors — the resolution rule for this and every `[fleet.*]`
table below. Full semantics: `CONFIG.md` (the source of truth for keys and defaults)
and `design/slopstop-process.md` §1.

---

## `[stage_tiers]` — process structure (stage → tier)

```toml
[stage_tiers]
design              = "huge"     # default
tickets             = "large"    # default
run                 = "medium"   # default
ticket_adversary    = "huge"     # default
rewrite_delta_check = "huge"     # default
drift_check         = "large"    # default
handoff_verifier    = "medium"   # default
report_adversary    = "huge"     # default
```

Decouples process structure from model deployment. `[tiers]` maps tier → model;
`[stage_tiers]` maps each stage and check → a tier, resolved in two hops
(stage → tier → model). Moving a stage or check to a different tier is a one-line edit
here — no skill rewrite. Missing keys resolve to the defaults above (the settled
"checker one tier above the doer" ladder); a missing table never errors. Fleet
implementation defaults to the model **resolved from `[tiers].small`** (override via
`[fleet.agents].model`); escalation defaults to the model **resolved from
`[tiers].medium`** (override via `[fleet.agents].escalation_model`). Full semantics:
`CONFIG.md`.

---

## `[fleet.agents]` — fleet implementation agents

```toml
[fleet.agents]
# model / escalation_model are optional overrides; absent, they derive from the tiers.
# model            = "haiku"    # override; default resolved from [tiers].small
effort           = "medium"   # default
adversary_effort = "high"     # default
# escalation_model = "sonnet"   # override; default resolved from [tiers].medium
```

Consumed by `:run` when launching worktree agents. `model` and `escalation_model`
**default from the tier ladder**: absent, `model` is the model resolved from
`[tiers].small` and `escalation_model` the model resolved from `[tiers].medium`, each
honoring the tier's optional version pin (family + version → a model id; unpinned →
the family alias). Setting either here is an override that wins for fleet launches.
`effort` is the launch effort; `adversary_effort` applies to an agent's own subagent
spawns (inline runs use the launch effort); `escalation_model` drives the
capability-escalated final attempt.

---

## `[fleet.monitoring]` — orchestrator kill triggers

```toml
[fleet.monitoring]
poll_interval_min     = 5       # default
quiet_investigate_min = 15      # default
silence_kill_min      = 30      # default
loop_kill_reports     = 3       # default
filemap_violation     = "kill"  # default; "warn" while evaluating small models
```

Consumed by `:run`'s monitoring loop (Step 5). Quiet investigates; silence (both
signal channels dead) kills; loops kill; file-map violations kill instantly and
mechanically — or log-only in `"warn"` mode.

---

## `[fleet.budget]` — attempt and escalation caps

```toml
[fleet.budget]
max_attempts_per_version = 3   # default
max_ticket_versions      = 3   # default
max_tier_escalations     = 1   # default
```

Consumed by `:run`'s failure handling (Step 7). Hard caps: exhaustion escalates to
the human at G4; only G4 can exceed them.

---

## `[fleet.router]` — metering router

```toml
[fleet.router]
enabled = false   # default — zero-infrastructure path
# host = "127.0.0.1"
# port = 8484
```

Consumed by `:design` (run-start health check, status only) and `:run` (health check
at each agent launch; healthy → agents launched with `ANTHROPIC_BASE_URL` pointed at
the router). Unreachable → agents fall back to direct API access; a dead router
degrades cost reporting, never a run.

---

## `[autonomous]` — fully non-interactive mode

```toml
[autonomous]
enabled = false   # default
```

### `enabled`

When `true`, most skills run without interactive prompts. **Exception: `:merge` requires the `--autonomous` flag to be passed on the command line** — `enabled = true` alone does not suppress `:merge`'s Step 3 confirm prompt. Each skill has per-decision config keys (e.g. `on_test_gaps`, `on_parallel_agents`) that control what happens at each decision point. See each skill's Autonomous behavior section for the full list.

Designed for CI pipelines or trusted solo-dev setups where interruptions are unwanted.

---

## `[exp]` — experiment branches

```toml
[exp]
label         = "experiment"   # default
branch_prefix = "exp"          # default
```

### `label`

Label applied to tickets created by `:exp`. Default `"experiment"`.

### `branch_prefix`

Branch prefix for experiment branches. Default `"exp"`, producing branches like `exp/MAZ-42`. Must be a valid `git check-ref-format` component.

---

## `[branch_prefixes]` — branch type overrides

```toml
[branch_prefixes]
feature = "feat"   # default
fix     = "fix"    # default
exp     = "exp"    # default; mirrors [exp].branch_prefix
```

Overrides the branch-type tokens that `:start` uses when creating branches. If absent, the defaults above apply. Setting `feature = "feature"` (for example) would produce `feature/KEY-N` instead of `feat/KEY-N`.

---

## Pattern: fork-PR / single shared repo

The `pr-remote`, `origin-remote`, `pr-repo`, and `base-branch` keys combine to support a common multi-workstream pattern where feature branches from multiple project directories all target a single shared GitHub repository.

**Why you need this:**

Consider a JIRA project (`system = "jira"`, `key = "PLTF"`) implemented across two git repos — `mobile-v2` and `server-v2`. Both need to open PRs against a shared GitHub repo (`iansmith/mycopy`) on a long-lived experiment branch. The canonical upstream (`iansmith/lyos`) is not yet publicly accessible, so a fork acts as the PR target.

**Example configs:**

`mobile-v2/.project-conf.toml`:
```toml
system = "jira"
key    = "PLTF"

pr-repo       = "iansmith/mycopy"      # GitHub repo that receives PRs
pr-remote     = "mycopy"              # git remote to push feature branches to
origin-remote = "mycopy"             # git remote that owns the base branch
base-branch   = "exp/fable-5-solo"   # PRs target this branch, not master
```

`server-v2/.project-conf.toml`:
```toml
system = "jira"
key    = "PLTF"

pr-repo       = "iansmith/mycopy"
pr-remote     = "server-mycopy"       # different remote name, same repo
origin-remote = "server-mycopy"
base-branch   = "exp/fable-5-solo"
```

**How the skills use it:**

- `:start` creates branches off `$ORIGIN_REMOTE/$DEFAULT_BRANCH` (or `base-branch` if set, via `:pr`). It fetches from `origin-remote`.
- `:pr` pushes the feature branch to `pr-remote`, then opens the PR against `pr-repo` at `base-branch`.
- `:merge` merges the PR on `pr-repo`, propagates `base-branch` to non-`origin-remote` remotes, and deletes the local branch.
- `:archive` posts the re-harvest to `pr-repo` (for GitHub; JIRA uses `key` directly).

The two remotes (`pr-remote` and `origin-remote`) can be different names pointing at the same underlying GitHub repo — that is the normal case. They only need to diverge when the push target and the canonical base genuinely live in different places (e.g. a Bitbucket mirror for reads, a GitHub fork for PRs).
