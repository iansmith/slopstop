---
description: Mirror the design/ directory to the project's ticket-system documentation store (GitHub wiki, Linear Docs). One-way push; design/ files unchanged; orphan pages pruned. Reads .project-conf.toml for the backend. Use /slopstop:doc-sync.
disable-model-invocation: true
---

# /slopstop:doc-sync

Mirror `design/*.md` to the project's documentation store. One-way push — `design/` is the source of truth; the doc-store copy is overwritten on each sync.

> **Note for Claude agents:** Do NOT invoke this skill in the same turn as `Edit`/`Write` on `design/` files. Finish all edits first, then run the sync as a separate turn.

## Project scope

Read `.project-conf.toml` from cwd. Extract:

- `system` → `$SYSTEM` ∈ {`linear`, `jira`, `github`}
- `key`    → `$KEY`

If `.project-conf.toml` is missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init or create the file manually."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill runs unmodified — no interactive prompts. `[autonomous]` config keys have no effect on this skill.

## Arguments

None. Operates on the current `design/` directory.

## Pre-flight

- Verify `design/` exists in cwd. If not, stop with `"No design/ directory found in cwd."`
- **Dirty-design check (informational).** Run `git status --porcelain -- design/`. If non-empty, print: `"Note: design/ has uncommitted changes. The sync will push working-tree state."` Do not block — continue.
- Per-system pre-flight (below).

## Frontmatter parsing (all backends)

For each `design/*.md` (top-level only; skip subdirectories, non-`.md` files):

- Parse optional YAML frontmatter (`---` … `---`). Extract `title` and `slug`; default both to `<filename without .md>`.
- Strip frontmatter from the body before pushing.

## system = "github"

Clone the wiki repo, write converted docs, prune orphans, commit and push.

→ Read `~/.claude/commands/slopstop-doc-sync-refs/doc-sync-github.md`

## system = "linear"

Via Linear MCP, list existing docs, upsert each `design/` file, prune orphans.

→ Read `~/.claude/commands/slopstop-doc-sync-refs/doc-sync-linear.md`

## system = "jira"

Stop with `"Confluence sync not yet supported."`

## Rules

- **One-way only.** Never read from the doc store back into `design/`.
- **Committed `design/` files are never modified.** Only the temp clone (GH) or upstream docs (Linear) change.
- **Frontmatter is stripped** before push.
- **Orphan pruning is mandatory.** Pages without a `design/` counterpart get deleted.
- **Idempotent.** Re-running with no source changes produces no commit (GH) or no upstream writes (Linear).
- **Partial state on failure is acceptable.** Re-running after a fix completes the sync.
