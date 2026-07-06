# Conflict Check

`$KEY` is already in use if ANY of the following are true:

1. `$TRACKING_DIR/$KEY/` exists and is non-empty.
2. `~/.claude/ticket-archive/$KEY/` exists and is non-empty.
3. A GitHub issue with `$KEY:` or `[$KEY]` in its title exists:
   - **MCP path:** `${GH_MCP_NS}search_issues(owner=$OWNER, repo=$REPO, query="$KEY in:title")` (or equivalent list call filtered by title).
   - **CLI path:** `$GH issue list --search "$KEY" --json number,title --repo "$OWNER/$REPO"`, filter results for exact `$KEY:` / `[$KEY]` prefix.

## Suffix loop

If a conflict is detected, append an alphabetic suffix: try `$KEY = "$PREFIX-${N}a"`, then `${N}b` … `${N}z`, re-running all three conflict checks at each step. Use the first suffix that passes all checks.

If `${N}z` is also taken (extremely unlikely), stop with:
`"Key collision: all suffixes $PREFIX-${N}a through $PREFIX-${N}z are in use. Resolve manually."`
The issue remains open; record its URL for the user.

If a suffix was assigned, note it in the Step 5 output.
