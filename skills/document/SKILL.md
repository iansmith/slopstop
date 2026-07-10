---
description: Sync the active ticket's local tracking documentation (task plan, DoD-confirmation evidence, findings) to the ticket on Linear/JIRA. Use /slopstop:document to push or refresh the description + DoD-confirmation comment + findings comment WITHOUT ending the local lifecycle (no archive, no local-dir move, no state change). Idempotent — running it twice on unchanged local state is a clean no-op. Safe by default — if the ticket already has managed documentation that differs from what would be pushed (e.g., someone hand-edited the description), stops with a per-artifact diff explanation and refuses to push anything. --force overrides the divergence check. --dry-run shows what would happen without doing it. Auto-detects ticket system.
disable-model-invocation: true
---

# /slopstop:document

Sync the active ticket's local documentation to the ticket on Linear/JIRA. Pure remote sync — does NOT touch local tracking, does NOT change ticket state, does NOT archive.

| Local source | Ticket target |
|---|---|
| `task_plan.md` (whole body) | Ticket **description**, with prior original description preserved as `## Original description (preserved)` appendix |
| `task_plan.md`'s `## Definition of Done` section + evidence | Separate **comment** titled `## Definition of Done — Confirmation` |
| `findings.md` (if non-template) | Separate **comment** titled `## Findings (from local tracking)` |

Per-artifact safety: if the ticket has a managed version that differs from expected, stop with a diff report and refuse to push **any** artifact (all-or-nothing). `--force` overrides.

`progress.md` is intentionally NOT pushed — per-session diary is too noisy for the durable record.

## When to use

→ Read `~/.claude/commands/slopstop-document-refs/document-lifecycle.md`

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Extract `$PREFIX` (`prefix` field), `system` (`linear` | `jira` | `github`), and `key` (for reference). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Only operate on `$PREFIX-\d+` tickets. If `.project-conf.toml` is missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`

Also read `tracking_dir` (optional): resolve to `$TRACKING_DIR`. If absent or equal to `~/.claude/ticket-active`, default to `~/.claude/ticket-active`. If a relative path (no leading `/` or `~/`), resolve from `dirname "$(git rev-parse --git-common-dir)"`. Absolute paths (starting with `/` or `~/`) are used as-is. **Guard:** if the resolved path lies under `~/.claude/`, warn `"tracking_dir resolves under ~/.claude, a protected path — headless agents cannot write there even with a matching --add-dir. Set a project-local path (e.g. \".slopstop/ticket-active\")."` and continue. The legacy default works interactively; it silently breaks fleet agents.

Also read `archive_dir` (optional): resolve to `$ARCHIVE_DIR` by the same rules; absent defaults to `~/.claude/ticket-archive`.

For the **GitHub backend**, also read `pr-repo` (optional): `$OWNER` and `$REPO` = `pr-repo` if present, else parse from `key` (e.g. `"iansmith/slopstop"` → `$OWNER=iansmith`, `$REPO=slopstop`).

## Autonomous mode

No interactive prompts — this skill runs unmodified under `[autonomous] enabled = true`. `[autonomous]` config keys have no effect here.

## Arguments

- Optional `$ARGUMENTS`: ticket key like `MAZ-26`. Must match `^$PREFIX-\d+$`. If empty, fall back to active ticket from `git branch --show-current`.
- Optional `--force`: push even when ticket has a managed divergent version. Surfaces a brief warning in Step 7 for each overridden artifact.
- Optional `--dry-run`: compute Steps 1–4, print per-artifact verdict + diffs, then stop. No remote calls.

If `$ARGUMENTS` is empty AND no `$PREFIX-N` in current branch: stop with `"No active $PREFIX ticket to document; pass a ticket key or check out a feature branch encoding the ticket ID."`.

Verify `$TRACKING_DIR/$TICKET/` exists (or `$ARCHIVE_DIR/$TICKET/`). If neither: `"No local tracking found for $TICKET."` and stop.

## Step 1 — Detect ticket system

Run three ToolSearches in parallel:

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__editJiraIssue,mcp__atlassian__addCommentToJiraIssue,mcp__atlassian__getAccessibleAtlassianResources", max_results=8)
ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__save_comment,mcp__linear-server__list_comments", max_results=8)
ToolSearch(query="select:mcp__github__get_issue,mcp__github__add_issue_comment,mcp__github__update_issue,mcp__github__list_issue_comments", max_results=8)
```

Set `$SYSTEM` from `.project-conf.toml`'s `system` field:

- **JIRA** — JIRA ToolSearch must be non-empty. Empty → stop: `"system='jira' in .project-conf.toml but no Atlassian MCP found."`
- **Linear** — Linear ToolSearch must be non-empty. Empty → stop: `"system='linear' in .project-conf.toml but no Linear MCP found."`
- **GitHub** — resolve `$GH_BACKEND`: canonical ToolSearch non-empty → `MCP` with `$GH_MCP_NS = "mcp__github__"`. Else run fallback ToolSearch for `mcp__plugin_github_github__*`; if non-empty → `MCP` with `$GH_MCP_NS = "mcp__plugin_github_github__"`. Both empty → `$GH_BACKEND = "CLI"`: find `gh` binary, save as `$GH`, verify auth. If no `gh`: stop with `"Neither GitHub MCP nor 'gh' CLI found."`.

See `design/github-backend-primitives.md` for full primitives.

## Step 2 — Fetch current ticket state

**JIRA:** Get cloudId via `mcp__atlassian__getAccessibleAtlassianResources`. Call `mcp__atlassian__getJiraIssue($TICKET, cloudId, fields=["status","description","summary"])`. Get comments via Atlassian comment-list tool (or comment-expanding field on the same call).

**Linear:** `mcp__linear-server__get_issue($TICKET)` + `mcp__linear-server__list_comments(issueId=$TICKET)`.

**GitHub MCP:** description via `${GH_MCP_NS}get_issue(owner=$OWNER, repo=$REPO, issueNumber=$N)` (read `body`). Comments via `${GH_MCP_NS}list_issue_comments(...)`.

**GitHub CLI:** description via `$GH issue view $N --json body`. Comments via `$GH api repos/$OWNER/$REPO/issues/$N/comments`.

Whitespace-trim all bodies on the way in (GitHub normalizes `\r\n` to `\n`; trimming prevents spurious divergence verdicts).

Store `$REMOTE_DESC` (description body) and `$REMOTE_COMMENTS` (list of `{id, body, created_at, updated_at, author}`).

## Step 3 — Compute desired state from local files

Read `$TRACKING_DIR/$TICKET/{task_plan,findings}.md` (or `$ARCHIVE_DIR/$TICKET/` copy).

### 3a. Description

If `$REMOTE_DESC` contains `## Original description (preserved)`: split on `---\n\n## Original description (preserved)\n\n`, preserve the suffix verbatim, set `$EXPECTED_DESC = <task_plan.md body> + "\n\n---\n\n## Original description (preserved)\n\n" + preserved_original`.

If not: set `$EXPECTED_DESC = <task_plan.md body> + "\n\n---\n\n## Original description (preserved)\n\n" + $REMOTE_DESC`.

### 3b. DoD-confirmation comment

If `task_plan.md` has no `## Definition of Done` section → `$EXPECTED_DOD = null` (skip).

Otherwise build the comment body per the template.
→ Read `~/.claude/commands/slopstop-document-refs/document-dod-assembly.md`

### 3c. Findings comment

If `findings.md` is template-empty (no `## ` headings, no prose past the scaffold) → `$EXPECTED_FINDINGS = null`.

Otherwise: `$EXPECTED_FINDINGS = "## Findings (from local tracking)\n\n" + <findings.md body>`.

## Step 4 — Classify each artifact

Each artifact (`description`, `dod`, `findings`) is categorized as `new`, `unchanged`, `divergent`, or `skip`. Divergent → Step 5 stops unless `--force`.
→ Read `~/.claude/commands/slopstop-document-refs/document-artifact-classification.md`

## Step 5 — Safety check

If any artifact is `divergent` AND `--force` is NOT set, STOP:

```
STOP — ticket $TICKET has managed documentation that differs from what would be pushed.

<for each divergent artifact:>
  ── <artifact name> ──────────────────────────────
  Local (expected):
    <first ~12 lines of $EXPECTED_<artifact>, with … if truncated>
  Remote (actual):
    <first ~12 lines of actual_managed_<artifact>, with … if truncated>

Likely causes: someone edited the ticket after a prior push; local files updated since last push; different session pushed an alternative version.

To proceed: run --force to overwrite (after reviewing the diff above), or reconcile manually then re-run. --dry-run shows the diff without pushing.

No remote calls made. Local tracking unchanged.
```

## Step 6 — Push (skip if `--dry-run`)

For each artifact in category `new`, or (with `--force`) `divergent`: push via the system-specific backend.
→ Read `~/.claude/commands/slopstop-document-refs/document-push-backends.md`

`unchanged` and `skip` artifacts: silently skip.

## Step 7 — Confirm

```
Documented $TICKET (<state name> on $SYSTEM).

Description:   <"updated (new)" | "updated (--force overrode divergent)" | "already current — skipped" | "skipped (nothing to push)">
DoD comment:   <"posted (new)" | "posted (--force overrode divergent; old comment left on ticket)" | "already current — skipped" | "skipped (no DoD section)">
Findings:      <"posted (new)" | "posted (--force overrode divergent; old comment left on ticket)" | "already current — skipped" | "skipped (findings.md template-empty)">

<if --force pushed new versions and MCP couldn't edit-in-place:>
Note: prior managed comments are still on the ticket. Delete them manually on $SYSTEM:
  - <link/id of stale DoD comment>
  - <link/id of stale findings comment>
```

For `--dry-run`: replace verbs with conditional form ("would update" / "would post" / etc.) and end with `(dry-run — no remote calls made)`.

## Rules

- **Does NOT change ticket state. Does NOT touch local tracking.**
- **Idempotent.** Same local + remote state → second run is a clean no-op.
- **Safe by default.** Divergence → refuse-and-explain. `--force` is the explicit escape hatch.
- **All-or-nothing on push.** Any `divergent` without `--force` → none of the artifacts are pushed.
- **`progress.md` is never pushed.**
- Ticket-system detection or fetch fails → error and stop. Divergence without `--force` → print report, exit cleanly (not an error). Push fails mid-loop → report which succeeded/failed; don't roll back; user re-runs.
