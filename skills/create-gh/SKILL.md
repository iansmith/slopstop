---
description: Create a new GitHub issue and assign it a BILL ticket key that matches the GitHub issue number — so BILL-N always equals GitHub issue #N. Accepts a title (required) plus optional body and labels. Rewrites the issue title to the canonical "BILL-N: <title>" form after creation. Handles key collisions (a BILL-N already exists in active/archive tracking or in another issue title) with an alphabetic suffix (BILL-Na, BILL-Nb, …). GitHub-only — stops early if system != 'github'. Does NOT transition the ticket or create a branch — call /slopstop:start BILL-N afterward to do that.
disable-model-invocation: true
---

# /slopstop:create-gh

Create a GitHub issue and assign it the BILL ticket key that equals the GitHub issue number.

**Design goal:** every ticket created through this skill has `BILL-N = GitHub issue #N`, so the digit-stripping logic in `:start`, `:pr`, `:merge`, and other downstream skills resolves the issue number correctly without a mapping file.

## Project scope

Read `.project-conf.toml` from cwd.

- Extract `$PREFIX` from the `prefix` field (e.g. `BILL`).
- Extract `$OWNER` and `$REPO` by splitting the `key` field on `/` (e.g. `iansmith/slopstop` → `$OWNER=iansmith`, `$REPO=slopstop`).
- Verify `system = "github"`. If not, stop: `"This skill is GitHub-only. system='<value>' in .project-conf.toml."`.

If `.project-conf.toml` is missing in cwd: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init or create the file manually."`.

## Arguments

`$ARGUMENTS` is parsed for:

- `--title "<text>"` — issue title (explicit flag form)
- `--body "<text>"` — issue body / description (optional)
- `--labels "<name>,<name>,..."` — comma-separated label names that already exist on the repo (optional)

If none of those flags are present, treat the entire `$ARGUMENTS` string as the title (unquoted positional form: `/slopstop:create-gh Add AGE graph schema endpoint`).

If the title is empty after parsing, ask: `"Issue title?"` — required; re-ask if blank.

If body is absent: ask `"Description? (Enter to skip)"` — empty answer is fine, creates the issue with no body.

Labels are never prompted for — they are optional and omitted if not provided.

## Step 1 — Detect GitHub backend

Run two ToolSearches in parallel:

```text
ToolSearch(query="select:mcp__plugin_github_github__issue_write,mcp__plugin_github_github__issue_read", max_results=4)
ToolSearch(query="select:mcp__github__create_issue,mcp__github__update_issue", max_results=4)
```

Resolution order:
1. Canonical `mcp__github__` search non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__github__"`.
2. Plugin search non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
3. Both empty → `$GH_BACKEND = "CLI"`. Locate `gh` binary by trying `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`. Save as `$GH`. If none resolve: stop with `"Neither GitHub MCP nor 'gh' CLI found."`. Verify auth: `$GH auth status` must succeed.

## Step 2 — Create the GitHub issue

**MCP path:**
```text
${GH_MCP_NS}issue_write(
  method="create",
  owner=$OWNER,
  repo=$REPO,
  title=$TITLE,
  body=$BODY,          # omit if empty
  labels=$LABELS       # omit if empty
)
```
Extract `$N` from the returned `number` field.

**CLI path:**
```bash
$GH issue create \
  --title "$TITLE" \
  [--body "$BODY"] \
  [--label "$LABELS"] \
  --repo "$OWNER/$REPO"
```
Parse `$N` from the last path segment of the returned issue URL.

On any failure, stop with the error verbatim. Do not proceed.

**Issue creation is the point of no return.** Once Step 2 succeeds the issue exists on GitHub. Proceed through the remaining steps even if they encounter partial failures — print warnings but always output the URL and assigned key at the end.

## Step 3 — Assign the BILL key

Compute `$KEY = "$PREFIX-$N"`.

**Conflict check** — `$KEY` is already in use if ANY of the following are true:

1. `~/.claude/ticket-active/$KEY/` exists and is non-empty.
2. `~/.claude/ticket-archive/$KEY/` exists and is non-empty.
3. A GitHub issue with `$KEY:` or `[$KEY]` in its title exists. Check by searching recent issues:
   - **MCP path:** `${GH_MCP_NS}search_issues(owner=$OWNER, repo=$REPO, query="$KEY in:title")` (or equivalent list call filtered by title).
   - **CLI path:** `$GH issue list --search "$KEY" --json number,title --repo "$OWNER/$REPO"`, filter results for exact `$KEY:` / `[$KEY]` prefix.

If a conflict is detected, append an alphabetic suffix: try `$KEY = "$PREFIX-${N}a"`, then `${N}b` … `${N}z`, re-running all three conflict checks at each step. Use the first suffix that passes all checks.

If `${N}z` is also taken (extremely unlikely), stop with:
`"Key collision: all suffixes $PREFIX-${N}a through $PREFIX-${N}z are in use. Resolve manually."`
The issue remains open; record its URL for the user.

If a suffix was assigned, note it in the output (Step 5).

## Step 4 — Rewrite the issue title

Update the GitHub issue title to canonical form: `"$KEY: $TITLE"` (e.g. `"BILL-65: Add AGE graph schema endpoint"`).

**MCP path:**
```text
${GH_MCP_NS}issue_write(
  method="update",
  owner=$OWNER,
  repo=$REPO,
  issue_number=$N,
  title="$KEY: $TITLE"
)
```

**CLI path:** `$GH issue edit $N --title "$KEY: $TITLE" --repo "$OWNER/$REPO"`

On failure, print a warning but continue — the issue and key assignment are valid regardless.

## Step 5 — Output

Print:

```text
Created $KEY (#$N) — https://github.com/$OWNER/$REPO/issues/$N

To start work:  /slopstop:start $KEY
```

If a suffix was used, also print:
```text
Note: $PREFIX-$N was already in use — key assigned as $KEY.
Suffixed keys may need the '#N' override when passed to :start: /slopstop:start $KEY #$N
```

## Rules

- **GitHub-only.** JIRA and Linear assign their own keys — this skill has no role there. Stop at the Project scope step if `system != "github"`.
- **No git operations.** This skill does not create branches, commit, or push. Call `/slopstop:start $KEY` afterward.
- **No ticket transition.** The issue is created in its default state (no `status:in-progress` label). `:start` handles that.
- **Suffixed keys (`BILL-Na`) are valid** for tracking dirs and branch names, but the `$PREFIX-\d+` branch parser in other skills won't match them automatically. Always pass both key and issue number (`BILL-65a #65`) when calling `:start` on a suffixed ticket.
- **Never use `--force` git ops, `git reset --hard`, or `git push --force`** — this skill has no git involvement at all.
