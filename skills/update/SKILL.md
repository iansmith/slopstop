---
description: Mid-session checkpoint to the active ticket's progress.md. Use /slopstop:update to snapshot what's been done so far during the same ticket session. The ticket stays active. Local-only — never calls JIRA or Linear.
disable-model-invocation: true
---

# /slopstop:update

Snapshot mid-session progress to the active ticket's tracking files. The ticket stays active (the branch doesn't change). Local-only — never calls JIRA or Linear.

## Project scope (every ticket skill follows this rule)

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Extract `$PREFIX` (`prefix` field) and `system` (`linear` | `jira` | `github`). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Also note the `key` field for reference (Linear team key, JIRA project key, or GitHub `owner/repo`).

**Only operate on `$PREFIX`'s tickets. The branch-IS-selection parser only matches `$PREFIX-\d+`, so a branch encoding a different project's prefix correctly fails the no-match check.**

Also read `tracking_dir` (optional): resolve to `$TRACKING_DIR`. If absent or equal to `~/.claude/ticket-active`, default to `~/.claude/ticket-active`. If a relative path (no leading `/` or `~/`), resolve from `dirname "$(git rev-parse --git-common-dir)"`. Absolute paths (starting with `/` or `~/`) are used as-is. **Guard:** if the resolved path lies under `~/.claude/`, warn `"tracking_dir resolves under ~/.claude, a protected path — headless agents cannot write there even with a matching --add-dir. Set a project-local path (e.g. \".slopstop/ticket-active\")."` and continue. The legacy default works interactively; it silently breaks fleet agents.

If `.project-conf.toml` is missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill runs unmodified — there are no interactive prompts to skip. `[autonomous]` config keys have no effect on this skill.

## Arguments

Optional `$ARGUMENTS`: a ticket key like `BILL-51`. Must match `^$PREFIX-\d+$`. If supplied, use it directly. If empty, fall back to the active ticket parsed from `git branch --show-current`.

Explicit ticket keys are useful when updating a paused ticket that no longer matches the current branch (e.g. after a context switch).

If `$ARGUMENTS` doesn't match `^$PREFIX-\d+$`: refuse with `"$ARGUMENTS doesn't match this project's prefix ($PREFIX)."`

## Pre-flight

- **Resolve active ticket.**
  - If `$ARGUMENTS` matches `^$PREFIX-\d+$`: use it as `$TICKET`.
  - Else parse `$TICKET` from `git branch --show-current`:
    - Find the first match of `$PREFIX-\d+` in `$BRANCH` (case-insensitive on `$PREFIX`; canonical-case the result).
    - No match → stop with `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or pass a ticket key as the argument."`
    - Match → `$TICKET` (e.g. `MAZ-43`, `BILL-2`).
- **In-flight check.** Verify `$TRACKING_DIR/$TICKET/` exists. If not: stop with `"$TICKET is not in-flight. Run :start $TICKET first."`

## Capture (run git calls in parallel)

- `$BRANCH` = `git branch --show-current`
- `$DIRTY` = `git status --porcelain` (note count of modified files)
- `$HEAD` = `git log -1 --format="%h %s"`
- `$PWD` = `pwd`
- `$TS` = `date -u +"%Y-%m-%d %H:%M UTC"`

## Append to `progress.md`

```markdown

## Update $TS

**Branch:** $BRANCH (HEAD: $HEAD)
**cwd:** $PWD
**Working tree:** clean | dirty: N files modified

### Completed since last snapshot
<bullets, one line each, of meaningful work done since the last pause/update entry>

### Current state
<one sentence: what is true right now — just finished, or actively in progress>

### Next step
<single concrete next action, in case context is lost from here>
```

Fill every section from conversation context. Don't ask the user.

## Also update (only if changed this session)

- `task_plan.md` — if phases were started, completed, invalidated, or newly scoped. Edit Plan checkboxes/notes. Skip cosmetic rewrites.
- `findings.md` — if new investigation results uncovered. Add a `## <topic>` section. Don't duplicate `task_plan.md` or `progress.md`.

## Confirm

```
Updated tracking for $TICKET.
Wrote: <files actually modified>
Ticket is still active.
```

## Rules

- Do NOT touch git.
- Do NOT call JIRA or Linear.
- Do NOT touch the auto-memory system (`~/.claude/projects/.../memory/`). Different system.
