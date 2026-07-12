# `.project-conf.toml` — Design Document

**Status:** Draft, 2026-05-24.

## Summary

The `ticket-*` skills currently identify their project via a single-word file `.project-prefix` at the working-directory root, containing `MAZ`, `PLTF`, etc. As multi-ticket and multi-backend (Linear / JIRA / GitHub Issues) features land, that file needs to carry structured information. This document defines `.project-conf.toml` — a TOML file at the same path that replaces `.project-prefix`.

## Goals

- Plugin-wide single source of truth for project-level configuration.
- TOML format for human readability and Python-native parsing (`tomllib` in 3.11+).
- Namespaced sections so future features can land their config under a `[<feature>]` table without rev-ing the schema.
- No auto-migration in skill code. The two existing legacy projects (mazzy/MAZ on Linear, lyos/PLTF on JIRA) are migrated by hand as one-off operations.

## Non-goals

- Per-user / per-machine config. `.project-conf.toml` is the *project's* config; user preferences live elsewhere if they exist.
- Schema validation in the first cut. Skills tolerate unknown keys; missing required keys produce a clear error.
- Hierarchical / inherited config (e.g. project-level + skill-level overlay). Single flat file.
- Auto-walk up the directory tree. The file must be in the current working directory (same behavior as `.project-prefix`).

## Format

Three flavors, one per backend.

### Linear
```toml
system = "linear"
key    = "MAZ"
```

### JIRA
```toml
system = "jira"
key    = "PLTF"
```

### GitHub
```toml
system = "github"
key    = "iansmith/slopstop"
prefix = "BILL"                     # short identifier used in branch names + filesystem paths

[status_labels]
in_progress = "status:in-progress"
in_review   = "status:in-review"   # only present in the 4-state workflow; omit for 3-state
```

`prefix` is **required** for `system = "github"` because `key` (`owner/repo`) contains a slash and is too long for branch/path use. For Linear/JIRA, `key` already plays this role (`MAZ`, `LOU`, `PLTF`), so `prefix` is omitted.

`[status_labels]` is **required** for GitHub (no native state machine; states are encoded as labels). For Linear / JIRA, states are first-class and the section is omitted.

### Reserved namespaces

Optional sections that consumers may use:

```toml
[exp]
label         = "experiment"              # applied to :exp-created tickets
branch_prefix = "exp"                     # default

[branch_prefixes]
feature = "feat"                          # default
fix     = "fix"                           # default
exp     = "exp"                           # default; mirrors [exp].branch_prefix
```

All optional. First-cut implementations may ignore `[branch_prefixes]` and hardcode defaults.

## Required vs. optional keys

| Key | Required? | Notes |
|---|---|---|
| `system` | yes | `"linear"` / `"jira"` / `"github"` |
| `key`    | yes | system-specific identifier (Linear team key, JIRA project key, GH `owner/repo`) |
| `prefix` | required for `system = "github"`; omitted for Linear/JIRA | short token (3-6 chars), filesystem/branch-safe, used in `$PREFIX-N` ticket IDs (e.g. `BILL-2`). For Linear/JIRA, `key` already plays this role. |
| `pr-repo` | no | GitHub `owner/repo` for PR operations. Overrides `key` for `$OWNER`/`$REPO` resolution. Necessary when `key` is not in `owner/repo` form — without it, GitHub PR/issue operations on JIRA/Linear projects cannot resolve the target repo. Example: `pr-repo = "iansmith/lyos"`. When absent, `$OWNER`/`$REPO` are parsed from `key`. |
| `pr-remote` | no | Remote to push feature branches to (default `"origin"`). Use when feature branches live on a fork or secondary remote (e.g. `"mycopy"`). |
| `origin-remote` | no | Remote to fetch/sync the base branch from (default `"origin"`). Use when the authoritative base is not `origin` (e.g. Bitbucket-primary projects). |
| `base-branch` | no | PR target branch (default: repo default branch). Overrides the repo's default branch as the merge target. |
| `tracking_dir` | no | Base directory for per-ticket tracking files. Default `~/.claude/ticket-active` (global). Set to a relative path like `.claude/ticket-active` for project-local isolation; relative paths are resolved from the main worktree root. See `project-conf-options.md` for full semantics. |
| `cc_warn_threshold` | no | Cyclomatic complexity 🟡 warning threshold (default 10). Used by `:pr`'s CC gate. |
| `cc_reject_threshold` | no | Cyclomatic complexity 🔴 hard-stop threshold (default 15). Used by `:pr`'s CC gate. |
| `[status_labels].in_progress` | required for `system = "github"` | else N/A |
| `[status_labels].in_review` | required for `system = "github"` with 4-state workflow | absent for 3-state |
| `[pr_review].*` | no | review backend and behavior; defaults if absent |
| `[workflow].*` | no | interactive-prompt behavior; defaults if absent |
| `[tiers].*` | no | model per process tier (huge/large/medium/small); defaults fable/opus/sonnet/haiku if absent |
| `[fleet.agents].*` | no | fleet-agent launch parameters; defaults if absent |
| `[fleet.monitoring].*` | no | orchestrator kill-trigger thresholds; defaults if absent |
| `[fleet.budget].*` | no | attempt/version/escalation caps (3/3/1 defaults) if absent |
| `[fleet.router].*` | no | metering router; disabled if absent |
| `[autonomous].*` | no | non-interactive mode; disabled if absent |
| `[exp].*`  | no | `:exp` defaults if absent |
| `[branch_prefixes].*` | no | hardcoded defaults if absent |

## Lookup behavior

Skills read `.project-conf.toml` from the current working directory first. If absent, they fall back to the main worktree root (`dirname "$(git rev-parse --git-common-dir)"`). This means sessions running inside a git worktree (e.g. `~/project/wt-KEY-N/`) automatically find the config in the parent checkout without any extra setup.

If the file is missing from both locations:

```
"No .project-conf.toml in cwd or main worktree.
 Run /slopstop:gh-init (for GitHub) or create the file manually."
```

Skills do **not** walk further up the directory tree beyond the main worktree root.

### Reading

```python
import tomllib
with open(".project-conf.toml", "rb") as f:
    conf = tomllib.load(f)

system = conf["system"]                # required
key    = conf["key"]                   # required
labels = conf.get("status_labels", {})
rag    = conf.get("rag", {})
exp    = conf.get("exp", {})
```

Skills only consume the namespaces they need. Unknown keys are tolerated.

## Companion file: `state.toml`

Per-ticket runtime state lives in a separate file inside each ticket directory:

```
~/.claude/ticket-active/$TICKET/state.toml
```

Its schema and write rules are fully defined in [multi-ticket.md](multi-ticket.md); this doc points at it only for cross-reference.

The two files are deliberately separate:

| File | Scope | Lifetime | Where |
|---|---|---|---|
| `.project-conf.toml` | Project | Long-lived, slow-changing | Project cwd |
| `state.toml` | Per ticket | Runtime, transient | `~/.claude/ticket-active/$TICKET/` |

### Why no separate `state.toml` design doc

A standalone design doc for `state.toml` was considered and rejected for this slice:

- The schema is small (≤6 fields: `state`, `blocked_on`, `blocked_since`, `parent`, plus reservations).
- Its write rules are tightly coupled to the multi-ticket design — *when* `state.toml` is written or cleared is a per-skill decision in `:start`, `:pause`, `:block`, `:archive`, which are all defined in [multi-ticket.md](multi-ticket.md).
- A separate doc would consist mostly of cross-references back to multi-ticket.md.

If `state.toml` grows non-trivial behavior independent of the skills that write it (e.g. an external watcher, schema versioning, migration tooling), a separate doc would become warranted. Until then, it lives inline.

## Migration

No auto-migration code. For each existing legacy project, perform a one-off manual migration:

1. Identify the correct `system` and `key`:
   - mazzy/MAZ → `system = "linear"`, `key = "MAZ"`.
   - lyos/PLTF → `system = "jira"`, `key = "PLTF"`.
2. Write `.project-conf.toml` in the new format.
3. Delete `.project-prefix`.

The skills' new code expects the new format only. **No fallback to single-word reads** — if a project hasn't been migrated, the skill prints the missing-file error and stops. This forces the migration to happen explicitly and prevents quiet drift.

## Versioning

No explicit schema version field in the first cut. If the format ever needs incompatible evolution, add a `schema_version = N` key at the top and have skills branch on it. The TOML structure tolerates additions without breaking existing readers, so most evolution will be additive.

## Prerequisites

None. This file's format is consumed by the new code in every other prerequisite (skill restructure, multi-ticket, `ticket-gh-init`). It's the lowest-level config primitive.

## Adjacent docs

- [multi-ticket.md](multi-ticket.md) — defines `state.toml` schema and the workflow that consumes `[status_labels]`.
- [ticket-gh-init.md](ticket-gh-init.md) — the skill that writes `.project-conf.toml` for new GitHub-backed projects.
