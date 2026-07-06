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

## `[autonomous]` — fully non-interactive mode

```toml
[autonomous]
enabled = false   # default
```

### `enabled`

When `true`, all skills run without interactive prompts. Each skill has per-decision config keys (e.g. `on_test_gaps`, `on_parallel_agents`) that control what happens at each decision point. See each skill's Autonomous behavior section for the full list.

Designed for CI pipelines or trusted solo-dev setups where interruptions are unwanted.

---

## `[hooks]` — lifecycle event config

```toml
[hooks]
text_harvest_on_merge = true   # default
```

### `text_harvest_on_merge`

When `true` (default), `:archive` re-harvests the now-closed ticket into the RAG `ticket_chunks` table so `:search` returns the final description rather than the stale `:start`-time snapshot. When `false`, the harvest step is skipped entirely.

This is a fire-and-forget POST to the RAG service. If the service is down, `:archive` skips and warns — the harvest failure is never fatal.

---

## `[rag]` — RAG service configuration

```toml
[rag]
endpoint     = "http://127.0.0.1:7777"   # default
corpus_scope = "linear"                  # default = value of top-level `system`
repo         = ""                        # default; used for SCIP code graph queries
```

### `endpoint`

URL of the running RAG service. `:search` and `:know` POST queries here. If the section is absent, the default `http://127.0.0.1:7777` is used.

### `corpus_scope`

Filters semantic search to tickets from a specific system. Defaults to the project's `system` value. Override when a Linear project's tickets were harvested under a different key or when you want cross-system search.

### `repo`

Repo identifier used by `:search`'s SCIP code graph subcommands (`--callers`, `--implementors`, `--blast-radius`, `--ticket-code`). Must match the repo string used when indexing with the SCIP harvester. Empty string disables code graph queries.

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
