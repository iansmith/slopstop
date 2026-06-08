---
description: Create a new GitHub issue and assign it a BILL ticket key that matches the GitHub issue number — so BILL-N always equals GitHub issue #N. Accepts a title (required) plus optional body and labels. Rewrites the issue title to the canonical "BILL-N: <title>" form after creation. Handles key collisions (a BILL-N already exists in active/archive tracking or in another issue title) with an alphabetic suffix (BILL-Na, BILL-Nb, …). GitHub-only — stops early if system != 'github'. Does NOT transition the ticket or create a branch — call /slopstop:start BILL-N afterward to do that.
disable-model-invocation: true
---

# /slopstop:create-gh

Create a GitHub issue and assign it the BILL ticket key that equals the GitHub issue number. (`BILL-N = GitHub issue #N` so digit-stripping in `:start`, `:pr`, `:merge` resolves the issue number without a mapping file.)

## Project scope

Read `.project-conf.toml` from cwd.

- Extract `$PREFIX` (`prefix` field), `$OWNER` and `$REPO` (split `key` on `/`).
- Verify `system = "github"`. If not: stop with `"This skill is GitHub-only. system='<value>' in .project-conf.toml."`.

If `.project-conf.toml` is missing: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init or create the file manually."`.

## Autonomous mode

When `.project-conf.toml` has `[autonomous] enabled = true`, this skill runs unmodified — no interactive prompts to skip.

## Arguments

`$ARGUMENTS` is parsed for `--title "<text>"`, `--body "<text>"`, `--labels "<name>,..."`. If no flags, treat the entire string as the title. Prompt `"Issue title?"` if title is empty; prompt `"Description? (Enter to skip)"` if body is absent. Labels are never prompted.

## Step 1 — Detect GitHub backend

Detect the GitHub backend (plugin MCP → CLI). This skill uses `issue_write`, which is plugin-namespace-only; canonical `mcp__github__` is not supported. Save as `$GH_BACKEND` and `$GH_MCP_NS` (or `$GH` for CLI).

→ Read `~/.claude/commands/slopstop-create-gh-refs/create-gh-backend-detect.md`

## Step 2 — Create the GitHub issue

**MCP path:**
```text
${GH_MCP_NS}issue_write(method="create", owner=$OWNER, repo=$REPO, title=$TITLE, body=$BODY, labels=$LABELS)
```
Extract `$N` from the returned `number` field.

**CLI path:** `$GH issue create --title "$TITLE" [--body "$BODY"] [--label "$LABELS"] --repo "$OWNER/$REPO"` — parse `$N` from the last path segment of the returned URL.

On any failure, stop with the error verbatim. **Issue creation is the point of no return** — once Step 2 succeeds proceed through all remaining steps even on partial failures (print warnings, always output URL and key).

## Step 3 — Assign the BILL key

Compute `$KEY = "$PREFIX-$N"`. Run the conflict check: `$KEY` is in use if the active/archive dir exists OR a GitHub issue has `$KEY:` in its title. If conflict, try `$KEY = ${N}a … ${N}z` (re-check each). If `${N}z` taken, stop.

→ Read `~/.claude/commands/slopstop-create-gh-refs/create-gh-conflict-check.md` for the full per-check detail and suffix loop.

## Step 4 — Rewrite the issue title

Update the issue title to `"$KEY: $TITLE"`.

**MCP path:** `${GH_MCP_NS}issue_write(method="update", owner=$OWNER, repo=$REPO, issue_number=$N, title="$KEY: $TITLE")`

**CLI path:** `$GH issue edit $N --title "$KEY: $TITLE" --repo "$OWNER/$REPO"`

On failure, print a warning and continue.

## Step 5 — Output

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

- **GitHub-only.** Stop at Project scope if `system != "github"`.
- **No git operations.** Call `/slopstop:start $KEY` afterward.
- **No ticket transition.** The issue is created in its default state; `:start` handles that.
- **Suffixed keys (`BILL-Na`)** are valid for tracking dirs and branch names, but the `$PREFIX-\d+` branch parser in other skills won't match them automatically — always pass both key and issue number (`BILL-65a #65`) when calling `:start` on a suffixed ticket.
